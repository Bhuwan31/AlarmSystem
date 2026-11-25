"""AI writer for messages that go to residents' phones. It writes; people edit and decide to send.

One short request without tools, to the same provider as the analyst (Claude, Gemini or an OpenAI-compatible API),
with the busy-model fallback. If no AI is configured or the call fails, callers fall back to the fixed templates, so a
warning can always be sent."""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.ai import agent, openai_compat
from app.config import get_settings

log = logging.getLogger(__name__)

SYSTEM = """You write emergency text messages for residents in Nepal, sent to their phones by an early-warning system.
Rules:
- Use ONLY the facts given. Never invent numbers, places, times, shelters, casualties or official orders.
- Say what is happening, where, how serious it is, and exactly what people should do now. Most important first.
- Plain words a farmer or schoolchild understands. No technical terms like "threshold", "gauge" or "model".
- English: 2-4 short sentences (max 320 characters). Then the same message in natural Nepali (Devanagari).
- Match the level: WATCH = get ready; WARNING = act now to protect people, animals and valuables, be ready to leave;
  CRITICAL = leave for high ground or a shelter immediately.
- Do not add a validity time or a sender line; the system adds them.
Reply with JSON only: {"title": "<max 60 characters, starts with the level word, e.g. FLOOD WARNING – Babai at Chepang>",
"english": "...", "nepali": "..."}"""


def available() -> bool:
    return agent.configured()


async def _complete(user: str, max_tokens: int = 900) -> tuple[str, str]:
    """Returns (text, model). Raises on failure."""
    if agent.provider() == "anthropic":
        resp = await agent.client().messages.create(model=agent.model(), max_tokens=max_tokens, system=SYSTEM,
                                                    messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if b.type == "text"), agent.model()
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], "max_tokens": max_tokens}
    models = [agent.model()] + ([agent.fallback_model()] if agent.fallback_model() else [])
    last: Exception | None = None
    for i, m in enumerate(models):
        try:
            resp = await agent.compat_client().complete({**body, "model": m}, attempts=2 if i < len(models) - 1 else 4)   # switch to the lighter model quickly
            return resp["choices"][0]["message"].get("content") or "", m
        except openai_compat.ProviderError as e:
            last = e
            if e.status not in openai_compat.BUSY:
                raise
            log.warning("AI writer: %s busy (%s), trying the next model", m, e.status)
    raise last or RuntimeError("no AI model available")


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0) if m else text)
    title, en, ne = (str(data.get(k) or "").strip() for k in ("title", "english", "nepali"))
    if len(en) < 20:
        raise ValueError("AI reply had no usable English message")
    return {"title": title[:120] or None, "message": (en + ("\n" + ne if ne else ""))[:2000]}


async def write(facts: dict) -> dict:
    """facts → {"title", "message", "model"}. Raises if the AI is unavailable or replies badly."""
    if not available():
        raise RuntimeError("AI is not configured (no API key)")
    text, used = await _complete("Facts:\n" + json.dumps(facts, ensure_ascii=False, default=str, indent=1))
    out = _parse(text)
    out["model"] = used
    return out


# ---------------------------------------------------------------------------------------------------------------------
# facts for a river warning
# ---------------------------------------------------------------------------------------------------------------------
async def warning_facts(conn, w) -> dict:
    st = await conn.fetchrow("""select name, basin, district, watch_level, warning_level, danger_level from stations where id = $1""", w["station_id"])
    tz = await conn.fetchval("select timezone from deployment_profile where id = 1") or "Asia/Kathmandu"
    lvl = await conn.fetch(
        """select value, observed_at from observations where station_id = $1 and variable = 'water_level_m' and quality <> 'BAD'
           and observed_at > now() - interval '6 hours' order by observed_at desc limit 40""", w["station_id"])
    ra = await conn.fetchrow("select reasons, inputs from risk_assessments where station_id = $1 order by computed_at desc limit 1", w["station_id"])
    facts = {"level": w["level"], "place": st["name"], "river_basin": st["basin"], "district": st["district"],
             "why_the_system_raised_it": list(w["reasons"] or [])[:5]}
    if lvl:
        now_v = lvl[0]["value"]
        facts["water_level_now_m"] = round(now_v, 2)
        older = [r for r in lvl if r["observed_at"] <= lvl[0]["observed_at"] - timedelta(hours=2)]
        if older:
            facts["change_last_2h_m"] = round(now_v - older[0]["value"], 2)
        for k, name in (("watch_level", "watch_level_m"), ("warning_level", "warning_level_m"), ("danger_level", "danger_level_m")):
            if st[k] is not None:
                facts[name] = st[k]
    inputs = (ra["inputs"] if ra else None) or {}
    for k in ("rain_24h_mm", "forecast_rain_24h_mm"):
        if inputs.get(k) is not None:
            facts[k] = inputs[k]
    if w["valid_until"]:
        facts["valid_until_local"] = w["valid_until"].astimezone(ZoneInfo(tz)).strftime("%d %b %H:%M")
    return facts


async def draft_for_warning(conn, w, actor: str = "ai_writer") -> dict:
    """Write and store the resident message for one warning. Falls back to the template on any AI problem."""
    from app.warnings.templates import TEMPLATES
    try:
        out = await write(await warning_facts(conn, w))
        title, message, source, model = out["title"], out["message"], "ai", out["model"]
    except Exception as e:  # noqa: BLE001 — a warning must always have a sendable message
        log.warning("AI message for warning %s failed (%s); using the template", w["id"], e)
        st = await conn.fetchval("select name from stations where id = $1", w["station_id"])
        title = {"WATCH": "FLOOD WATCH", "WARNING": "FLOOD WARNING", "CRITICAL": "EVACUATE NOW"}.get(w["level"], w["level"]) + f" — {st}"
        message = TEMPLATES[w["level"]]["en"].format(place=st) + "\n" + TEMPLATES[w["level"]]["ne"].format(place=st)
        source, model = "template", None
    await conn.execute(
        """update warnings set resident_title = $2, resident_message = $3, resident_message_source = $4, resident_message_model = $5,
             resident_message_at = now(), updated_at = now() where id = $1""", w["id"], title, message, source, model)
    return {"title": title, "message": message, "source": source, "model": model,
            "at": datetime.now(timezone.utc).isoformat()}
