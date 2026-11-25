"""Independent evidence around a photo's place and time: rain gauges (measured), weather model (modelled), river
gauge risk, official warnings and other reports. Every lookup fails soft to "unavailable" — never to "confirmed"."""
import logging
from datetime import datetime, timedelta, timezone

from app.vision.policy import Evidence

log = logging.getLogger(__name__)
LEVEL_NUM = {"NORMAL": 0, "WATCH": 1, "WARNING": 2, "CRITICAL": 3}
GAUGE_KM, RIVER_KM, OFFICIAL_KM = 15.0, 10.0, 10.0
CONFIRM_24H_MM, CONFIRM_1H_MM = 25.0, 7.0
DRY_24H_MM, DRY_1H_MM = 5.0, 1.0


def correlation(gauge_1h: float | None, gauge_24h: float | None, model_24h: float | None) -> str:
    """confirmed (gauges measured heavy rain) | contradicted (gauges measured little) | inconclusive (gauges in between)
    | supported_by_model (no gauges; weather model shows heavy rain — modelled, not measured) | unavailable."""
    if gauge_1h is not None or gauge_24h is not None:
        g1, g24 = gauge_1h or 0.0, gauge_24h or 0.0
        if g24 >= CONFIRM_24H_MM or g1 >= CONFIRM_1H_MM:
            return "confirmed"
        if g24 < DRY_24H_MM and g1 < DRY_1H_MM:
            return "contradicted"
        return "inconclusive"
    if model_24h is not None and model_24h >= CONFIRM_24H_MM:
        return "supported_by_model"
    return "unavailable"


async def gather(conn, obs_id, lat: float, lon: float, when: datetime | None, user_id) -> tuple[dict, dict]:
    """Returns (facts for storage/display, ctx for the agent state). `when` = capture time, or None if unknown."""
    t = when or datetime.now(timezone.utc)
    pt = "ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography"
    facts: dict = {"gauges": None, "model": None, "river": None, "official": None}
    try:
        g = await conn.fetchrow(
            f"""select max(o.value) filter (where o.variable = 'rain_1h_mm') r1, max(o.value) filter (where o.variable = 'rain_24h_mm') r24,
                       count(distinct s.id) n, min(ST_Distance(s.geom::geography, {pt}) / 1000) km
                from stations s join observations o on o.station_id = s.id
                where s.kind in ('rain', 'device_rain') and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)
                  and o.observed_at between $4::timestamptz - interval '3 hours' and $4::timestamptz + interval '1 hour' and o.quality <> 'BAD'""",
            lat, lon, GAUGE_KM, t)
        if g and g["n"]:
            facts["gauges"] = {"rain_1h_mm": g["r1"], "rain_24h_mm": g["r24"], "stations": g["n"], "nearest_km": round(g["km"], 1),
                               "kind": "measured (rain gauges)"}
    except Exception as e:  # noqa: BLE001
        log.warning("gauge lookup failed: %s", e)
    try:
        m = await conn.fetchrow(
            """select precipitation_mm, rain_24h_forecast_mm, observed_at from weather_grid
               where grid = 'nepal' and abs(lat - $1) <= 0.3 and abs(lon - $2) <= 0.3
                 and observed_at between $3::timestamptz - interval '6 hours' and $3::timestamptz + interval '3 hours'
               order by (lat - $1) ^ 2 + (lon - $2) ^ 2, abs(extract(epoch from observed_at - $3::timestamptz)) limit 1""", lat, lon, t)
        if m:
            facts["model"] = {"precipitation_mm": m["precipitation_mm"], "rain_24h_forecast_mm": m["rain_24h_forecast_mm"],
                              "kind": "modelled (Open-Meteo), not measured"}
    except Exception as e:  # noqa: BLE001
        log.warning("model weather lookup failed: %s", e)
    try:
        r = await conn.fetchrow(
            f"""select s.name, ST_Distance(s.geom::geography, {pt}) / 1000 km, ra.level
                from stations s join lateral (select level from risk_assessments where station_id = s.id
                     and computed_at between $4::timestamptz - interval '6 hours' and $4::timestamptz + interval '1 hour' order by computed_at desc limit 1) ra on true
                where s.kind in ('river', 'device_river') and ST_DWithin(s.geom::geography, {pt}, $3 * 1000) and ra.level <> 'UNKNOWN'
                order by 2 limit 1""", lat, lon, RIVER_KM, t)
        if r:
            facts["river"] = {"station": r["name"], "km": round(r["km"], 1), "level": r["level"]}
    except Exception as e:  # noqa: BLE001
        log.warning("river lookup failed: %s", e)
    try:
        w = await conn.fetchrow(
            f"""select w.level, w.source, s.name from warnings w join stations s on s.id = w.station_id
                where w.status = 'ACTIVE' and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)
                order by case w.level when 'CRITICAL' then 0 when 'WARNING' then 1 else 2 end limit 1""", lat, lon, OFFICIAL_KM)
        if w:
            facts["official"] = {"level": w["level"], "source": w["source"], "station": w["name"]}
    except Exception as e:  # noqa: BLE001
        log.warning("official warning lookup failed: %s", e)
    reports, prior = 0, 0
    try:
        reports = await conn.fetchval(
            f"""select count(distinct o.user_id) from visual_observations o join ai_predictions p on p.observation_id = o.id
                where o.id <> $4 and o.duplicate_of is null and o.processing_status = 'done' and p.alert_level <> 'NONE'
                  and o.created_at > now() - interval '6 hours' and o.user_id is distinct from $5
                  and ST_DWithin(o.geom::geography, {pt}, $3 * 1000)""", lat, lon, 2.0, obs_id, user_id) or 0
        prior = await conn.fetchval(
            f"""select max(case alert_level when 'CRITICAL' then 3 when 'WARNING' then 2 else 1 end) from disaster_incidents
                where incident_status in ('PROPOSED', 'ACTIVE') and ST_DWithin(geom::geography, {pt}, $3 * 1000)""", lat, lon, 2.0) or 0
    except Exception as e:  # noqa: BLE001
        log.warning("history lookup failed: %s", e)
    g, m = facts["gauges"] or {}, facts["model"] or {}
    facts["weather_correlation"] = correlation(g.get("rain_1h_mm"), g.get("rain_24h_mm"), m.get("rain_24h_forecast_mm"))
    facts["reports_nearby_6h"] = int(reports)
    facts["prior_level_nearby"] = int(prior)
    ctx = {"gauge_rain_1h": g.get("rain_1h_mm"), "gauge_rain_24h": g.get("rain_24h_mm"),
           "model_rain_24h": m.get("rain_24h_forecast_mm"),
           "river_level": LEVEL_NUM.get(facts["river"]["level"]) if facts["river"] else None,
           "official_level": LEVEL_NUM.get(facts["official"]["level"]) if facts["official"] else None,
           "reports_6h": int(reports) + 1, "prior_level": int(prior), "evidence": int(reports) + 1}
    return facts, ctx


def to_evidence(facts: dict, ctx: dict, obs: dict, age_h: float | None, future_min: float, model_available: bool) -> Evidence:
    return Evidence(
        weather_correlation=facts["weather_correlation"], river_level=ctx["river_level"],
        river_km=facts["river"]["km"] if facts["river"] else None, official_level=ctx["official_level"],
        reports_nearby=facts["reports_nearby_6h"], age_h=age_h, future_min=future_min,
        capture_time_source=obs["capture_time_source"], image_source=obs["image_source"],
        location_source=obs["location_source"], accuracy_m=obs["gps_accuracy"],
        duplicate_of=str(obs["duplicate_of"]) if obs["duplicate_of"] else None, model_available=model_available)


def time_checks(capture: datetime | None, now: datetime | None = None) -> tuple[float | None, float]:
    """(age in hours or None if unknown, minutes in the future)."""
    if capture is None:
        return None, 0.0
    now = now or datetime.now(timezone.utc)
    delta = now - capture
    return max(0.0, delta / timedelta(hours=1)), max(0.0, -delta / timedelta(minutes=1))
