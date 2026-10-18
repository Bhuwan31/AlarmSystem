"""Risk assessment job: evaluate every river reach and raise warning proposals (FR-11, FR-12, FR-18)."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import asyncpg

from app.db import audit
from app.risk.engine import ENGINE_VERSION, Reading, RiskInputs, assess
from app.warnings.state_machine import proposal_needed
from app.warnings.templates import render

log = logging.getLogger(__name__)


async def run(conn: asyncpg.Connection) -> dict:
    profile = await conn.fetchrow("select * from deployment_profile where id = 1")
    pol = profile["policies"]
    now = datetime.now(timezone.utc)
    hold = int(pol.get("hold_minutes", 60))

    stations = await conn.fetch(
        """select s.id, s.name, s.source_code, s.watch_level, s.warning_level, s.danger_level, d.staleness_seconds
           from stations s join data_sources d on d.code = s.source_code
           where s.kind in ('river', 'device_river')""")
    readings = defaultdict(list)
    for r in await conn.fetch(
        """select station_id, observed_at, value, quality from observations
           where variable = 'water_level_m' and quality in ('GOOD', 'SUSPECT') and value is not null
             and (not is_simulated or $1)   -- SR-12: simulated data only counts in exercise mode
             and observed_at > now() - interval '12 hours' order by station_id, observed_at desc""",
        bool(pol.get("exercise_mode", True))):
        readings[r["station_id"]].append(Reading(r["observed_at"], r["value"], r["quality"]))

    rain = {r["id"]: r["rain"] for r in await conn.fetch(
        """select s.id, max(o.value) rain from stations s
           join stations g on g.kind in ('rain', 'device_rain') and ST_DWithin(s.geom::geography, g.geom::geography, 20000)
           join lateral (select value from observations where station_id = g.id and variable = 'rain_24h_mm'
                         and quality = 'GOOD' and observed_at > now() - interval '3 hours'
                         order by observed_at desc limit 1) o on true
           where s.kind in ('river', 'device_river') group by s.id""")}

    forecast = {r["id"]: r["v"] for r in await conn.fetch(
        """select s.id, w.rain_24h_forecast_mm v from stations s
           join lateral (select rain_24h_forecast_mm from weather_grid
                         where grid = 'nepal' and received_at = (select max(received_at) from weather_grid where grid = 'nepal')
                         order by ST_SetSRID(ST_MakePoint(lon, lat), 4326) <-> s.geom limit 1) w on true
           where s.kind in ('river', 'device_river')""")}

    satellite = {r["id"]: r["v"] for r in await conn.fetch(
        """select s.id, w.precipitation_mm v from stations s
           join lateral (select precipitation_mm from weather_grid
                         where grid in ('imerg_nepal', 'insat_nepal') and observed_at > now() - interval '6 hours'
                           and abs(lat - ST_Y(s.geom)) <= 0.3 and abs(lon - ST_X(s.geom)) <= 0.3
                         order by observed_at desc limit 1) w on true
           where s.kind in ('river', 'device_river')""")}

    previous, candidates = {}, defaultdict(list)
    for r in await conn.fetch(
        """select station_id, level, inputs->>'candidate_level' cand, computed_at from risk_assessments
           where computed_at > now() - make_interval(mins => $1) order by station_id, computed_at desc""", hold + 15):
        previous.setdefault(r["station_id"], r["level"])
        candidates[r["station_id"]].append((r["computed_at"], r["cand"] or r["level"]))
    for r in await conn.fetch(
        """select distinct on (station_id) station_id, level from risk_assessments
           where station_id <> all($1::bigint[]) order by station_id, computed_at desc""", list(previous.keys())):
        previous.setdefault(r["station_id"], r["level"])

    open_w = defaultdict(dict)
    for r in await conn.fetch("select station_id, status, level, source from warnings where status in ('ACTIVE', 'PROPOSED')"):
        open_w[r["station_id"]][r["status"]] = r
    official = {sid: w["ACTIVE"]["level"] for sid, w in open_w.items()
                if "ACTIVE" in w and w["ACTIVE"]["source"] == "official_import"}

    counts = defaultdict(int)
    proposals = 0
    for s in stations:
        sid = s["id"]
        res = assess(RiskInputs(
            now=now, watch_level=s["watch_level"], warning_level=s["warning_level"], danger_level=s["danger_level"],
            readings=readings.get(sid, []), staleness_s=s["staleness_seconds"],
            observed_rain_24h_mm=rain.get(sid), satellite_rain_mm_h=satellite.get(sid), forecast_rain_24h_mm=forecast.get(sid),
            official_level=official.get(sid), previous_level=previous.get(sid), recent_candidates=candidates.get(sid, []),
            rise_rate_m_per_h=float(pol.get("rise_rate_m_per_h", 0.5)), hold_minutes=hold,
        ))
        counts[res.level] += 1
        latest = readings[sid][0] if readings.get(sid) else None
        await conn.execute(
            """insert into risk_assessments (station_id, level, confidence, reasons, inputs, engine_version)
               values ($1, $2, $3, $4, $5, $6)""",
            sid, res.level, res.confidence, res.reasons,
            {"candidate_level": res.candidate_level, "water_level_m": latest.value if latest else None,
             "observed_at": latest.at.isoformat() if latest else None, "rain_24h_mm": rain.get(sid),
             "satellite_rain_mm_h": satellite.get(sid), "forecast_rain_24h_mm": forecast.get(sid)},
            ENGINE_VERSION)

        active = open_w[sid].get("ACTIVE")
        proposed = open_w[sid].get("PROPOSED")
        level = proposal_needed(res.level, active["level"] if active else None, proposed["level"] if proposed else None)
        if level:
            proposals += await _propose(conn, sid, s["name"], level, res.confidence, res.reasons, profile, proposed is not None)

    await conn.execute("delete from risk_assessments where computed_at < now() - interval '30 days'")
    await _expire(conn)
    return {"assessed": len(stations), "levels": dict(counts), "proposals": proposals}


async def _propose(conn, station_id, name, level, confidence, reasons, profile, replace_open) -> int:
    pol = profile["policies"]
    exercise = bool(pol.get("exercise_mode", True))
    valid_until = datetime.now(timezone.utc) + timedelta(hours=6)
    msg = render(level, name, issuer="pending approval", valid_until=valid_until.strftime("%Y-%m-%d %H:%M UTC"),
                 confidence=confidence, exercise=exercise)
    async with conn.transaction():
        if replace_open:
            await conn.execute("update warnings set status = 'SUPERSEDED', updated_at = now() where station_id = $1 and status = 'PROPOSED'", station_id)
        wid = await conn.fetchval(
            """insert into warnings (station_id, level, status, source, exercise, confidence, message, reasons, proposed_by, valid_until)
               values ($1, $2, 'PROPOSED', 'auto', $3, $4, $5, $6, 'system', $7) returning id""",
            station_id, level, exercise, confidence, msg, reasons, valid_until)
        await audit(conn, "system", "warning.propose", "warning", str(wid), {"station_id": station_id, "level": level, "reasons": reasons})
        if level == "WATCH" and pol.get("auto_publish_watch"):
            await conn.execute("update warnings set status = 'ACTIVE', valid_from = now(), updated_at = now() where id = $1", wid)
            await audit(conn, "system", "warning.auto_publish", "warning", str(wid), {"level": level})
    return 1


async def _expire(conn) -> None:
    rows = await conn.fetch("update warnings set status = 'EXPIRED', updated_at = now() where status = 'ACTIVE' and valid_until < now() returning id")
    for r in rows:
        await audit(conn, "system", "warning.expire", "warning", str(r["id"]), {})
