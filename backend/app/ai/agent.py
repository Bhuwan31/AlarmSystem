"""AI analyst (scheduled, 24/7) and AI assistant (chat) with read-only tools.

Providers: Claude (Anthropic API, used when ANTHROPIC_API_KEY is set), Google Gemini (free tier, GEMINI_API_KEY) or
any OpenAI-compatible API (AI_BASE_URL + AI_API_KEY). Same tools, prompts and safety boundary for all.

Safety boundary (SR-02, SR-11): the model can only READ the system and RECORD advisory findings.
It cannot create, approve or cancel warnings, trigger sirens or change configuration. Findings are
shown to operators, who may turn one into a normal warning proposal that still needs human approval.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

import anthropic
from anthropic import beta_async_tool

from app import weather_month as weather_month_mod
from app.ai import data, openai_compat, proposals
from app.config import get_settings
from app.db import audit, pool

log = logging.getLogger(__name__)
FALLBACK_BETA = "server-side-fallback-2026-07-01"

Severity = Literal["NORMAL", "WATCH", "WARNING", "CRITICAL"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Hazard = Literal["flood", "heavy_rain", "heat", "wind", "cold", "data_gap", "other"]


def _j(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def _anthropic_key() -> bool:
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def provider() -> str:
    """anthropic | gemini | openai_compat. 'auto' uses Claude when its key is set, otherwise Gemini."""
    p = get_settings().ai_provider.lower()
    if p != "auto":
        return p
    return "gemini" if get_settings().gemini_api_key and not _anthropic_key() else "anthropic"


def configured() -> bool:
    s = get_settings()
    return {"anthropic": _anthropic_key(), "gemini": bool(s.gemini_api_key),
            "openai_compat": bool(s.ai_base_url and s.ai_api_key)}.get(provider(), False)


def model() -> str:
    return get_settings().ai_model or {"anthropic": "claude-opus-5-5", "gemini": "gemini-flash-latest"}.get(provider(), "")


def fallback_model() -> str | None:
    """Lighter model used when the main one is overloaded. AI_FALLBACK_MODEL=off disables it."""
    v = get_settings().ai_fallback_model.strip()
    if v.lower() in ("off", "none", "false", "0"):
        return None
    return v or {"gemini": "gemini-flash-lite-latest"}.get(provider())


def interval_s() -> int:
    """Scheduled analysis interval. Gemini's free tier caps requests per day, so it runs less often by default."""
    return get_settings().ai_interval_s or (10800 if provider() == "gemini" else 1800)


_compat: openai_compat.Client | None = None


def compat_client() -> openai_compat.Client:
    global _compat
    if _compat is None:
        s = get_settings()
        if provider() == "gemini":
            _compat = openai_compat.Client(openai_compat.GEMINI_BASE_URL, s.gemini_api_key)
        else:
            _compat = openai_compat.Client(s.ai_base_url, s.ai_api_key)
    return _compat


_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(max_retries=3, timeout=180)
    return _client


# --------------------------------------------------------------------------------------------
# Read-only tools shared by the analyst and the assistant
# --------------------------------------------------------------------------------------------

@beta_async_tool
async def national_overview() -> str:
    """Snapshot of the whole deployment: river risk counts, rivers closest to warning level, heaviest
    rain in the last 24 h, Nepal weather summary, open warnings and data-source health. Call this first."""
    return _j(await data.national_overview())


@beta_async_tool
async def list_river_stations(min_index: float = 0.0, basin: str | None = None, level: str | None = None, limit: int = 40) -> str:
    """List live river gauges with water level, thresholds, trend and the rules engine's risk level.

    Args:
        min_index: Only stations whose warning_index (1.0 = at warning level) is at least this value.
        basin: Optional river basin name filter, e.g. "Koshi", "West Rapti".
        level: Optional risk level filter: NORMAL, WATCH, WARNING, CRITICAL or UNKNOWN.
        limit: Maximum number of stations to return (default 40).
    """
    return _j(await data.list_river_stations(min_index, basin, level, min(limit, 80)))


@beta_async_tool
async def get_station(station_id: int) -> str:
    """Detail for one gauge: thresholds, hourly readings for the last 24 h, recent risk assessments with
    reasons, and open data-quality problems.

    Args:
        station_id: The station id from another tool's output.
    """
    return _j(await data.get_station(station_id))


@beta_async_tool
async def rain_near(lat: float, lon: float, radius_km: float = 30) -> str:
    """Rain gauges near a point with rain in the last hour and last 24 hours.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        radius_km: Search radius in km (default 30).
    """
    return _j(await data.rain_near(lat, lon, min(radius_km, 100)))


@beta_async_tool
async def satellite_rain(min_mm_h: float = 0.5) -> str:
    """Satellite rainfall cells (NASA GPM IMERG / INSAT) from the last 6 hours above a rain rate.

    Args:
        min_mm_h: Minimum rain rate in mm per hour (default 0.5).
    """
    return _j(await data.satellite_rain(min_mm_h))


@beta_async_tool
async def weather_extremes() -> str:
    """Extremes across the national weather grid: hottest next 3 days, highest feels-like temperature,
    coldest, strongest gusts and most rain forecast in the next 24 h, with coordinates."""
    return _j(await data.weather_extremes())


@beta_async_tool
async def weather_at(lat: float, lon: float) -> str:
    """Current weather at one place: temperature, feels-like, humidity, pressure, wind, air flow at heights from
    10 m to about 9 km, 3-day max/min, a 24 h outlook and heat status. Model data from Open-Meteo.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
    """
    return _j(await data.weather_at(lat, lon))


@beta_async_tool
async def area_conditions(lat: float, lon: float, radius_km: float = 25) -> str:
    """Everything about one area: nearby river gauges with risk, rain gauges, warnings nearby, nearest
    shelters and current weather. Best single tool for a question about a specific place.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        radius_km: Radius in km (default 25).
    """
    return _j(await data.area_conditions(lat, lon, min(radius_km, 100)))


@beta_async_tool
async def devices_status() -> str:
    """Status of the project's own field devices (river gauges and sirens): online/offline, battery, signal, last seen."""
    return _j(await data.devices_status())


@beta_async_tool
async def data_quality() -> str:
    """Health of every data source (fresh or stale, last error) and open data-quality problems such as stale or stuck gauges."""
    return _j(await data.data_quality())


@beta_async_tool
async def active_warnings() -> str:
    """Warnings currently ACTIVE or PROPOSED (awaiting human approval), with level and reasons."""
    return _j(await data.active_warnings())


@beta_async_tool
async def geocode(place: str) -> str:
    """Find coordinates for a place name (town, district, river crossing). Returns up to 5 matches.

    Args:
        place: Place name, e.g. "Biratnagar" or "Chisapani, Kailali".
    """
    return _j(await data.geocode(place))


@beta_async_tool
async def weather_month(lat: float, lon: float) -> str:
    """Thirty-day weather for any place in the world: summary of the last 30 days (rain total, rain days, hottest,
    coldest, strongest gust, heat/rain/wind flags), the next 16 days, the same 30 days last year, and every day's values.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
    """
    d = await weather_month_mod.place(lat, lon)
    return _j({k: v for k, v in d.items() if k != "days"} | {"days": [
        {k: x[k] for k in ("date", "tmax_c", "tmin_c", "precip_mm", "gust_max_kmh", "humidity_pct")} for x in d["days"]]})


@beta_async_tool
async def world_weather_month() -> str:
    """Last 30 days and next 7 days for about 60 major cities on every continent, with heat, heavy rain, storm wind,
    cold, snow and dry-spell flags. Use for questions about world-wide conditions."""
    return _j(await weather_month_mod.world())


READ_TOOLS = [national_overview, list_river_stations, get_station, rain_near, satellite_rain, weather_extremes,
              weather_at, area_conditions, devices_status, data_quality, active_warnings, geocode, weather_month, world_weather_month]


# --------------------------------------------------------------------------------------------
# Analyst: runs on a schedule, records findings
# --------------------------------------------------------------------------------------------

ANALYST_SYSTEM = """You are the duty analyst for AMHEWS, a flood and weather early-warning system. The current deployment is Nepal.
Your job is to review all live inputs - government river and rain gauges, the project's own field devices, satellite rainfall,
weather model grids and data-source health - and report what operators should pay attention to right now.

How to work:
- Start with national_overview, then investigate whatever looks significant: rivers near or above warning level, fast rises,
  heavy rain upstream of a river, heat, strong wind, and gaps in the data. Use get_station, rain_near, area_conditions and
  the other tools to check before concluding. A few focused checks beat many shallow ones.
- Base every statement on tool output. Quote the numbers and their time (e.g. "4.6 m at 10:05 UTC, warning level 4.5 m").
  If data is missing, stale or disabled, say so - missing data is never evidence of safety.
- The rules engine already assigns a risk level to each river. Your value is what rules miss: combining rain, trend and
  upstream conditions, spotting suspicious or stuck readings, and noting where you disagree with the engine and why.
- Record each distinct issue with record_finding (at most 8, most serious first). If nothing needs attention, record no
  findings and say so in the summary. Finish by calling submit_summary exactly once.

Limits:
- You are advisory. You cannot issue, approve or cancel warnings or sound sirens, and you must not claim to have done so.
  Recommend actions for authorised officials instead.
- Severity in a finding is your suggested level; human approvers decide what is published.
- For a WATCH, WARNING or CRITICAL finding about a real hazard to people (not a data gap), also write public_message:
  2-4 plain sentences for residents of that area saying what is happening there, how serious it is and what to do.
  It becomes a draft that an approver edits and decides whether to send; never claim it has been sent.
- Be concise and plain: operators read this under time pressure."""


ANALYST_TASK = "Run the scheduled analysis of the current situation now. Finish with submit_summary."


@dataclass
class RunState:
    findings: list[dict] = field(default_factory=list)
    summary: dict | None = None


def _analyst_tools(state: RunState):
    @beta_async_tool
    async def record_finding(area: str, lat: float, lon: float, severity: Severity, confidence: Confidence, hazard: Hazard,
                             summary: str, evidence: list[str], recommended_action: str, station_ids: list[int],
                             public_message: str = "") -> str:
        """Record one advisory finding for operators. Call once per distinct issue, most serious first.

        Args:
            area: Short place name, e.g. "Bagmati at Khokana" or "Western Terai".
            lat: Latitude of the area centre.
            lon: Longitude of the area centre.
            severity: Suggested level: NORMAL, WATCH, WARNING or CRITICAL.
            confidence: HIGH, MEDIUM or LOW, reflecting data quality and agreement between sources.
            hazard: flood, heavy_rain, heat, wind, cold, data_gap or other.
            summary: One or two sentences: what is happening and why it matters.
            evidence: Facts from tool output with numbers and times.
            recommended_action: What authorised officials should consider doing.
            station_ids: Related station ids (empty list if none).
            public_message: For WATCH or higher public hazards: 2-4 plain sentences for residents of the area (what is
                happening, how serious, what to do). Empty for data gaps or NORMAL. Approvers review it before sending.
        """
        if len(state.findings) >= 8:
            return "Limit of 8 findings reached; include remaining points in the summary."
        state.findings.append({"area": area[:120], "lat": lat, "lon": lon, "severity": severity, "confidence": confidence,
                               "hazard": hazard, "summary": summary[:600], "evidence": [e[:300] for e in evidence[:8]],
                               "recommended_action": recommended_action[:400], "station_ids": station_ids[:10],
                               "public_message": (public_message or "")[:1200]})
        return f"Recorded finding {len(state.findings)}."

    @beta_async_tool
    async def submit_summary(overall_level: Severity, headline: str, summary: str, data_gaps: list[str]) -> str:
        """Finish the analysis. Call exactly once, after recording findings.

        Args:
            overall_level: Highest level that operators should be aware of nationally.
            headline: One line, under 120 characters.
            summary: Three to six sentences for the duty officer.
            data_gaps: Inputs that were missing, stale or disabled and how that limits this analysis.
        """
        state.summary = {"overall_level": overall_level, "headline": headline[:200], "summary": summary[:2000],
                         "data_gaps": [g[:300] for g in data_gaps[:10]]}
        return "Summary submitted. Analysis complete."

    return [record_finding, submit_summary]


def _request_options(effort: str) -> dict:
    """Shared request settings: cache the stable system prompt + tools, and fall back automatically
    if the primary model declines a request."""
    return {
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
        "cache_control": {"type": "ephemeral"},
        "output_config": {"effort": effort},
    }


async def run_analysis(trigger: str = "auto", requested_by: str | None = None) -> str | None:
    """Run one analysis and store it. Returns the run id, or None when the AI is not configured."""
    if not configured():
        return None
    s = get_settings()
    p = pool()
    if await p.fetchval("select count(*) from ai_analyses where status = 'running' and started_at > now() - interval '20 minutes'"):
        log.info("AI analysis already running; skipping")
        return None
    run_id = await p.fetchval("insert into ai_analyses (trigger, requested_by, status, model) values ($1, $2, 'running', $3) returning id",
                              trigger, requested_by, model())
    state = RunState()
    usage = {"input": 0, "output": 0, "tools": 0}
    t0 = time.monotonic()
    try:
        if provider() == "anthropic":
            text = await _claude_analysis(state, usage)
        else:
            out = await openai_compat.run(
                compat_client(), model=model(), system=ANALYST_SYSTEM, history=[{"role": "user", "content": ANALYST_TASK}],
                tools=READ_TOOLS + _analyst_tools(state), max_iterations=s.ai_max_iterations, max_tokens=16000,
                effort=s.ai_effort, stop_after=lambda name: name == "submit_summary",
                fallback_model=fallback_model(), on_fallback=lambda: state.__init__())   # drop partial findings
            usage.update(input=out["input_tokens"], output=out["output_tokens"], tools=len(out["tools_used"]))
            text = out["text"]
            if out["model"] != model():
                await p.execute("update ai_analyses set model = $2 where id = $1", run_id, out["model"])
        if state.summary is None:
            state.summary = {"overall_level": max((f["severity"] for f in state.findings), key=_rank, default="NORMAL"),
                             "headline": "Analysis ended without a summary", "summary": text[:2000] or "No summary returned.",
                             "data_gaps": []}
        await p.execute(
            """update ai_analyses set status = 'done', finished_at = now(), overall_level = $2, headline = $3, summary = $4,
                 findings = $5, data_gaps = $6, tool_calls = $7, input_tokens = $8, output_tokens = $9 where id = $1""",
            run_id, state.summary["overall_level"], state.summary["headline"], state.summary["summary"], state.findings,
            state.summary["data_gaps"], usage["tools"], usage["input"], usage["output"])
        async with p.acquire() as conn:
            await audit(conn, requested_by or "ai_analyst", "ai.analysis", "ai_analysis", str(run_id),
                        {"overall_level": state.summary["overall_level"], "findings": len(state.findings), "seconds": round(time.monotonic() - t0)})
        log.info("AI analysis %s done: %s, %d findings, %d tool calls", run_id, state.summary["overall_level"], len(state.findings), usage["tools"])
        if s.ai_propose_messages:
            try:
                async with p.acquire() as conn, conn.transaction():
                    exercise = await conn.fetchval("select coalesce((policies->>'exercise_mode')::boolean, true) from deployment_profile where id = 1")
                    n = await proposals.propose(conn, run_id, state.findings, exercise if exercise is not None else True)
                if n:
                    log.info("AI analysis %s: %d draft area message(s) waiting for approval", run_id, n)
            except Exception:  # noqa: BLE001 — drafting must never undo a finished analysis
                log.exception("drafting area messages from analysis %s failed", run_id)
    except Exception as e:  # noqa: BLE001 — a failed run must be visible, never crash the scheduler
        log.exception("AI analysis failed")
        await p.execute("update ai_analyses set status = 'failed', finished_at = now(), error = $2, findings = $3 where id = $1",
                        run_id, f"{type(e).__name__}: {e}"[:500], state.findings)
    return str(run_id)


async def _claude_analysis(state: RunState, usage: dict) -> str:
    s = get_settings()
    runner = client().beta.messages.tool_runner(
        model=model(), max_tokens=16000, max_iterations=s.ai_max_iterations, system=ANALYST_SYSTEM,
        tools=READ_TOOLS + _analyst_tools(state), messages=[{"role": "user", "content": ANALYST_TASK}],
        **_request_options(s.ai_effort),
    )
    last = None
    async for message in runner:
        last = message
        usage["input"] += message.usage.input_tokens + (message.usage.cache_read_input_tokens or 0) + (message.usage.cache_creation_input_tokens or 0)
        usage["output"] += message.usage.output_tokens
        usage["tools"] += sum(1 for b in message.content if b.type == "tool_use")
    if last is not None and last.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    return next((b.text for b in (last.content if last else []) if b.type == "text"), "")


def _rank(level: str) -> int:
    return ["NORMAL", "WATCH", "WARNING", "CRITICAL"].index(level) if level in ("NORMAL", "WATCH", "WARNING", "CRITICAL") else -1


# --------------------------------------------------------------------------------------------
# Assistant: answers operators' questions about a place or the situation
# --------------------------------------------------------------------------------------------

ASSISTANT_SYSTEM = """You are the AMHEWS assistant for disaster-management staff. The current deployment is Nepal.
Answer questions about current conditions - rivers, rain, weather, heat, warnings, shelters, devices and data quality -
using the tools. For a named place, use geocode first, then area_conditions. For the past month, trends or places
outside Nepal, use weather_month (any place in the world) or world_weather_month.

- Use only tool output for facts; give numbers with units and the time they were observed. If data is missing, stale or
  not configured, say so plainly.
- Keep answers short and practical, with the most important point first. Reply in the language the user writes in
  (Nepali or English).
- You are advisory: you cannot issue warnings, approve them or sound sirens. If action seems needed, say what authorised
  officials should consider and point to the Warnings page."""


async def chat(history: list[dict]) -> dict:
    s = get_settings()
    if provider() != "anthropic":
        out = await openai_compat.run(compat_client(), model=model(), system=ASSISTANT_SYSTEM, history=history, tools=READ_TOOLS,
                                      max_iterations=12, max_tokens=8000, effort=s.ai_chat_effort, fallback_model=fallback_model())
        return {"answer": out["text"] or "I could not produce an answer from the available data.", "tools_used": out["tools_used"]}
    runner = client().beta.messages.tool_runner(
        model=model(), max_tokens=8000, max_iterations=12, system=ASSISTANT_SYSTEM, tools=READ_TOOLS,
        messages=history, **_request_options(s.ai_chat_effort),
    )
    used: list[str] = []
    last = None
    async for message in runner:
        last = message
        used += [b.name for b in message.content if b.type == "tool_use"]
    if last is None:
        return {"answer": "No response.", "tools_used": used}
    if last.stop_reason == "refusal":
        return {"answer": "I can't help with that request.", "tools_used": used}
    answer = "\n\n".join(b.text for b in last.content if b.type == "text").strip()
    return {"answer": answer or "I could not produce an answer from the available data.", "tools_used": used}
