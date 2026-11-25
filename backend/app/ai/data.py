"""Read-only views of the live system for the AI analyst and assistant.

Every function returns small JSON-serialisable dicts with real numbers and timestamps, so the model
reasons from data, not memory. Nothing here can change warnings, devices or configuration.
"""
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app import weather_point
from app.db import pool

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _val(v):
    if isinstance(v, Decimal):
        v = float(v)
    return round(v, 3) if isinstance(v, float) else _iso(v)


def _row(r) -> dict:
    return {k: _val(v) for k, v in dict(r).items()}


async def national_overview() -> dict:
    p = pool()
    levels = {r["level"]: r["n"] for r in await p.fetch(
        """select level, count(*) n from (select distinct on (station_id) station_id, level from risk_assessments
           order by station_id, computed_at desc) x group by level""")}
    rivers = await list_river_stations(min_index=0.75, limit=15)
    rain = await p.fetch(
        """select s.id, s.name, s.district, s.basin, o.value rain_24h_mm, o.observed_at from stations s
           join lateral (select value, observed_at from observations where station_id = s.id and variable = 'rain_24h_mm'
                         and quality = 'GOOD' order by observed_at desc limit 1) o on true
           where s.kind in ('rain', 'device_rain') and o.observed_at > now() - interval '6 hours' and o.value > 0
           order by o.value desc limit 10""")
    weather = await p.fetchrow(
        """select round(avg(temperature_c)::numeric, 1) t_avg, min(temperature_c) t_min, max(temperature_c) t_max,
                  max(tmax_3d_c) tmax_next3d, max(wind_gust_kmh) gust_max, max(rain_24h_forecast_mm) rain24_forecast_max,
                  max(observed_at) observed_at
           from weather_grid where grid = 'nepal' and received_at = (select max(received_at) from weather_grid where grid = 'nepal')""")
    warns = await p.fetch("select level, status, count(*) n from warnings where status in ('ACTIVE', 'PROPOSED') group by 1, 2")
    profile = await p.fetchrow("select name, policies from deployment_profile where id = 1")
    return {
        "now_utc": datetime.now(timezone.utc).isoformat(), "deployment": profile["name"],
        "exercise_mode": profile["policies"].get("exercise_mode", True),
        "river_risk_counts": levels, "rivers_closest_to_warning": rivers["stations"],
        "heaviest_rain_24h": [_row(r) for r in rain], "weather_nepal": _row(weather) if weather else None,
        "open_warnings": [_row(r) for r in warns], "data_sources": (await data_quality())["sources"],
    }


async def list_river_stations(min_index: float = 0.0, basin: str | None = None, level: str | None = None, limit: int = 40) -> dict:
    from app.api.public import warning_index  # local: public.py imports this module
    rows = await pool().fetch(
        """select s.id, s.name, s.basin, s.district, ST_Y(s.geom) lat, ST_X(s.geom) lon, s.warning_level, s.danger_level,
                  s.meta->>'trend' trend, o.value, o.observed_at, o.quality, ra.level risk_level, ra.confidence, ra.reasons
           from stations s
           left join lateral (select value, observed_at, quality from observations where station_id = s.id
                              and variable = 'water_level_m' order by observed_at desc limit 1) o on true
           left join lateral (select level, confidence, reasons from risk_assessments where station_id = s.id
                              order by computed_at desc limit 1) ra on true
           where s.kind in ('river', 'device_river') and ($1::text is null or s.basin ilike $1) and ($2::text is null or ra.level = $2)""",
        basin, level)
    out = []
    for r in rows:
        idx = warning_index(r["value"], r["warning_level"])
        if (idx or 0) < min_index and not (level and r["risk_level"] == level):
            continue
        d = _row(r)
        d["warning_index"] = idx
        out.append(d)
    out.sort(key=lambda d: -(d["warning_index"] or -1))
    return {"count": len(out), "stations": out[:limit],
            "note": "warning_index 1.0 = at warning level. Some stations report level as height above sea level."}


async def get_station(station_id: int) -> dict:
    p = pool()
    s = await p.fetchrow(
        """select id, kind, name, basin, district, ST_Y(geom) lat, ST_X(geom) lon, watch_level, warning_level, danger_level,
                  meta, source_code from stations where id = $1""", station_id)
    if s is None:
        return {"error": f"no station with id {station_id}"}
    var = "rain_1h_mm" if s["kind"].endswith("rain") else "water_level_m"
    series = await p.fetch(
        """select date_trunc('hour', observed_at) as hour_utc, round(avg(value)::numeric, 3) as value
           from observations where station_id = $1 and variable = $2 and quality in ('GOOD', 'SUSPECT')
             and observed_at > now() - interval '24 hours' group by 1 order by 1""", station_id, var)
    risk = await p.fetch(
        "select level, confidence, reasons, computed_at from risk_assessments where station_id = $1 order by computed_at desc limit 5", station_id)
    events = await p.fetch("select kind, detail, opened_at from data_quality_events where station_id = $1 and closed_at is null", station_id)
    return {"station": _row(s), "variable": var, "hourly_last_24h": [_row(r) for r in series],
            "recent_risk": [_row(r) for r in risk], "open_data_problems": [_row(r) for r in events]}


async def rain_near(lat: float, lon: float, radius_km: float = 30) -> dict:
    rows = await pool().fetch(
        """select s.id, s.name, s.district, round((ST_Distance(s.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) / 1000)::numeric, 1) km,
                  (select value from observations where station_id = s.id and variable = 'rain_1h_mm' order by observed_at desc limit 1) rain_1h_mm,
                  (select value from observations where station_id = s.id and variable = 'rain_24h_mm' order by observed_at desc limit 1) rain_24h_mm,
                  (select max(observed_at) from observations where station_id = s.id) observed_at
           from stations s where s.kind in ('rain', 'device_rain')
             and ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3 * 1000)
           order by km limit 15""", lat, lon, radius_km)
    return {"gauges": [_row(r) for r in rows]}


async def satellite_rain(min_mm_h: float = 0.5) -> dict:
    p = pool()
    rows = await p.fetch(
        """select grid, lat, lon, precipitation_mm mm_per_h, observed_at from weather_grid
           where grid in ('imerg_nepal', 'insat_nepal') and observed_at > now() - interval '6 hours' and precipitation_mm >= $1
           order by precipitation_mm desc limit 30""", min_mm_h)
    sources = await p.fetch("select code, enabled, last_success_at from data_sources where code in ('gpm_imerg', 'insat')")
    return {"cells": [_row(r) for r in rows], "sources": [_row(r) for r in sources],
            "note": "Empty when satellite sources are disabled (credentials not configured) - say so rather than assuming no rain."}


async def weather_extremes() -> dict:
    p = pool()
    base = "from weather_grid where grid = 'nepal' and received_at = (select max(received_at) from weather_grid where grid = 'nepal')"
    async def top(col, desc=True, n=5):
        return [_row(r) for r in await p.fetch(f"select lat, lon, {col} value {base} and {col} is not null order by {col} {'desc' if desc else 'asc'} limit {n}")]
    return {"hottest_next_3_days_c": await top("tmax_3d_c"), "highest_feels_like_now_c": await top("apparent_temp_c"),
            "coldest_now_c": await top("temperature_c", False), "strongest_gusts_kmh": await top("wind_gust_kmh"),
            "most_rain_next_24h_mm": await top("rain_24h_forecast_mm")}


async def weather_at(lat: float, lon: float) -> dict:
    try:
        d = await weather_point.fetch(lat, lon)
    except httpx.HTTPError as e:
        return {"error": f"weather provider unavailable: {e}"}
    return {k: d[k] for k in ("lat", "lon", "elevation_m", "observed_at", "current", "air_flow", "daily", "heat", "source")} | {
        "outlook_24h_every_3h": d["outlook_24h"][::3]}


async def area_conditions(lat: float, lon: float, radius_km: float = 25) -> dict:
    p = pool()
    pt = "ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography"
    rivers = await p.fetch(
        f"""select s.id, s.name, s.basin, round((ST_Distance(s.geom::geography, {pt}) / 1000)::numeric, 1) km, s.warning_level, s.danger_level,
                   (select value from observations where station_id = s.id and variable = 'water_level_m' order by observed_at desc limit 1) level_m,
                   (select level from risk_assessments where station_id = s.id order by computed_at desc limit 1) risk
            from stations s where s.kind in ('river', 'device_river') and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)
            order by km limit 10""", lat, lon, radius_km)
    warns = await p.fetch(
        f"""select w.level, w.status, w.reasons, s.name from warnings w join stations s on s.id = w.station_id
            where w.status in ('ACTIVE', 'PROPOSED') and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)""", lat, lon, radius_km)
    shelters = await p.fetch(
        f"""select name, status, capacity - occupancy free_places, round((ST_Distance(geom::geography, {pt}) / 1000)::numeric, 1) km
            from shelters order by geom::geography <-> {pt} limit 3""", lat, lon)
    return {"rivers": [_row(r) for r in rivers], "warnings_nearby": [_row(r) for r in warns],
            "nearest_shelters": [_row(r) for r in shelters], "rain_gauges": (await rain_near(lat, lon, radius_km))["gauges"][:8],
            "weather": await weather_at(lat, lon)}


async def devices_status() -> dict:
    rows = await pool().fetch("select id, kind, name, status, battery_v, rssi_dbm, last_seen_at, test_mode, station_id from devices order by id")
    return {"devices": [_row(r) for r in rows]}


async def data_quality() -> dict:
    p = pool()
    sources = await p.fetch(
        """select code, name, enabled, last_success_at, left(last_error, 160) last_error,
                  (last_success_at is not null and last_success_at > now() - make_interval(secs => staleness_seconds)) fresh
           from data_sources order by code""")
    events = await p.fetch(
        """select e.kind, e.source_code, s.name station, e.opened_at from data_quality_events e
           left join stations s on s.id = e.station_id where e.closed_at is null order by e.opened_at desc limit 20""")
    return {"sources": [_row(r) for r in sources], "open_events": [_row(r) for r in events]}


async def active_warnings() -> dict:
    rows = await pool().fetch(
        """select w.id::text, w.level, w.status, w.source, w.exercise, w.reasons, w.created_at, s.id station_id, s.name station
           from warnings w join stations s on s.id = w.station_id where w.status in ('ACTIVE', 'PROPOSED')
           order by case w.level when 'CRITICAL' then 0 when 'WARNING' then 1 else 2 end""")
    return {"warnings": [_row(r) for r in rows]}


async def geocode(place: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(GEOCODE_URL, params={"name": place, "count": 5, "language": "en", "format": "json"})
        r.raise_for_status()
    results = r.json().get("results") or []
    return {"matches": [{"name": x.get("name"), "admin1": x.get("admin1"), "country": x.get("country"),
                         "lat": x.get("latitude"), "lon": x.get("longitude")} for x in results]}
