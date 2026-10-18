"""Public read endpoints used by the dashboard and citizen app."""
import httpx
from fastapi import APIRouter, HTTPException, Query

from app import weather_point as weather_point_mod
from app.db import pool

router = APIRouter(prefix="/api/v1", tags=["public"])

GRIDS = {"nepal", "global", "imerg_nepal", "insat_nepal"}


def warning_index(value: float | None, warning: float | None) -> float | None:
    """0 = far below warning, 1 = at warning level. Gauge-zero stations: value / warning.
    Elevation-datum stations (thresholds > 60 m): 1 - metres below warning / 5 m."""
    if value is None or not warning:
        return None
    scale = 5.0 if warning > 60 else warning
    return round(1 - (warning - value) / scale, 3)


def _feature(lon, lat, props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


@router.get("/profile")
async def profile():
    row = await pool().fetchrow("select country_code, name, timezone, languages, bbox, hydromet_authority, drr_authority, emergency_numbers, policies from deployment_profile where id = 1")
    return dict(row)


@router.get("/status")
async def status():
    rows = await pool().fetch(
        """select d.code, d.name, d.kind, d.enabled, d.last_success_at, d.last_error, d.last_error_at, d.licence,
                  (d.last_success_at is not null and d.last_success_at > now() - make_interval(secs => d.staleness_seconds)) fresh
           from data_sources d order by d.code""")
    out = []
    for r in rows:
        r = dict(r)
        if not r["enabled"]:
            r["state"] = "disabled"
        elif r["fresh"]:
            r["state"] = "ok"
        elif r["last_success_at"] is None and (r["last_error"] or "").startswith("disabled"):
            r["state"] = "needs_credentials"
        else:
            r["state"] = "stale"
        out.append(r)
    return out


@router.get("/weather/grid")
async def weather_grid(grid: str = Query("nepal")):
    if grid not in GRIDS:
        raise HTTPException(400, f"grid must be one of {sorted(GRIDS)}")
    rows = await pool().fetch(
        """select * from weather_grid where grid = $1
             and received_at = (select max(received_at) from weather_grid where grid = $1)""", grid)
    feats = [_feature(r["lon"], r["lat"], {
        "temperature_c": r["temperature_c"], "humidity_pct": r["humidity_pct"], "precipitation_mm": r["precipitation_mm"],
        "rain_24h_forecast_mm": r["rain_24h_forecast_mm"], "wind_speed_kmh": r["wind_speed_kmh"],
        "wind_dir_deg": r["wind_dir_deg"], "wind_gust_kmh": r["wind_gust_kmh"], "cloud_cover_pct": r["cloud_cover_pct"],
        "weather_code": r["weather_code"], "apparent_temp_c": r["apparent_temp_c"], "pressure_hpa": r["pressure_hpa"],
        "tmax_3d_c": r["tmax_3d_c"], "observed_at": r["observed_at"].isoformat(),
    }) for r in rows]
    return {"type": "FeatureCollection", "grid": grid,
            "observed_at": rows[0]["observed_at"].isoformat() if rows else None, "features": feats}


@router.get("/weather/point")
async def weather_point(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    try:
        return await weather_point_mod.fetch(lat, lon)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"weather provider unavailable: {e}") from e


@router.get("/weather/summary")
async def weather_summary():
    r = await pool().fetchrow(
        """select count(*) n, avg(temperature_c) t_avg, min(temperature_c) t_min, max(temperature_c) t_max,
                  max(wind_speed_kmh) wind_max, max(wind_gust_kmh) gust_max, max(precipitation_mm) precip_max,
                  max(rain_24h_forecast_mm) rain24_max, avg(humidity_pct) rh_avg, max(observed_at) observed_at
           from weather_grid where grid = 'nepal' and received_at = (select max(received_at) from weather_grid where grid = 'nepal')""")
    return dict(r)


@router.get("/stations")
async def stations(kind: str = Query("river", pattern="^(river|rain|device_river|device_rain)$")):
    rows = await pool().fetch(
        """select s.id, s.source_code, s.external_id, s.name, s.basin, s.district, ST_X(s.geom) lon, ST_Y(s.geom) lat,
                  s.watch_level, s.warning_level, s.danger_level, s.meta->>'trend' trend,
                  o.value, o.observed_at, o.quality, o24.value rain_24h_mm, ra.level risk_level, ra.confidence, ra.reasons
           from stations s
           left join lateral (select value, observed_at, quality from observations
                              where station_id = s.id and variable = case when s.kind like '%rain' then 'rain_1h_mm' else 'water_level_m' end
                              order by observed_at desc limit 1) o on true
           left join lateral (select value from observations where station_id = s.id and variable = 'rain_24h_mm'
                              order by observed_at desc limit 1) o24 on true
           left join lateral (select level, confidence, reasons from risk_assessments
                              where station_id = s.id order by computed_at desc limit 1) ra on true
           where s.kind = $1""", kind)
    feats = []
    for r in rows:
        ratio = warning_index(r["value"], r["warning_level"])
        feats.append(_feature(r["lon"], r["lat"], {
            "id": r["id"], "source": r["source_code"], "name": r["name"], "basin": r["basin"], "district": r["district"],
            "value": r["value"], "observed_at": r["observed_at"].isoformat() if r["observed_at"] else None,
            "quality": r["quality"], "rain_24h_mm": r["rain_24h_mm"], "watch_level": r["watch_level"],
            "warning_level": r["warning_level"], "danger_level": r["danger_level"], "ratio_to_warning": ratio,
            "trend": r["trend"], "risk_level": r["risk_level"] or "UNKNOWN", "confidence": r["confidence"],
            "reasons": r["reasons"] or [],
        }))
    return {"type": "FeatureCollection", "kind": kind, "features": feats}


@router.get("/stations/{station_id}/series")
async def series(station_id: int, variable: str = "water_level_m", hours: int = Query(48, le=24 * 30)):
    rows = await pool().fetch(
        """select observed_at, value, quality from observations
           where station_id = $1 and variable = $2 and observed_at > now() - make_interval(hours => $3)
           order by observed_at""", station_id, variable, hours)
    return [{"t": r["observed_at"].isoformat(), "v": r["value"], "q": r["quality"]} for r in rows]


@router.get("/risk/summary")
async def risk_summary():
    rows = await pool().fetch(
        """select level, count(*) n from (
             select distinct on (station_id) station_id, level from risk_assessments order by station_id, computed_at desc) x
           group by level""")
    return {r["level"]: r["n"] for r in rows}


@router.get("/warnings")
async def list_warnings(status: str | None = None):
    rows = await pool().fetch(
        """select w.*, s.name station_name, s.district, ST_X(s.geom) lon, ST_Y(s.geom) lat,
                  coalesce((select array_agg(approver) from warning_approvals a where a.warning_id = w.id), '{}') approvers
           from warnings w join stations s on s.id = w.station_id
           where ($1::text is null and w.status in ('PROPOSED', 'ACTIVE')) or w.status = $1
              or ($1 = 'all' and w.created_at > now() - interval '30 days')
           order by case w.level when 'CRITICAL' then 0 when 'WARNING' then 1 else 2 end, w.created_at desc
           limit 200""", status)
    return [dict(r) for r in rows]


@router.get("/stations/{station_id}")
async def station_detail(station_id: int):
    s = await pool().fetchrow(
        """select s.id, s.source_code, s.external_id, s.kind, s.name, s.basin, s.district, ST_X(s.geom) lon, ST_Y(s.geom) lat,
                  s.elevation_m, s.watch_level, s.warning_level, s.danger_level, s.meta, s.updated_at
           from stations s where s.id = $1""", station_id)
    if s is None:
        raise HTTPException(404, "station not found")
    latest = await pool().fetch(
        """select distinct on (variable) variable, value, unit, observed_at, quality, quality_reason
           from observations where station_id = $1 order by variable, observed_at desc""", station_id)
    risk = await pool().fetch(
        """select level, confidence, reasons, inputs, computed_at from risk_assessments
           where station_id = $1 and computed_at > now() - interval '48 hours' order by computed_at desc limit 300""", station_id)
    warns = await pool().fetch(
        "select id, level, status, source, created_at, valid_until, reasons from warnings where station_id = $1 order by created_at desc limit 20",
        station_id)
    events = await pool().fetch(
        "select kind, detail, opened_at, closed_at from data_quality_events where station_id = $1 order by opened_at desc limit 20", station_id)
    return {"station": dict(s), "latest": [dict(r) for r in latest], "risk_history": [dict(r) for r in risk],
            "warnings": [dict(r) for r in warns], "quality_events": [dict(r) for r in events],
            "warning_index": warning_index(next((r["value"] for r in latest if r["variable"] == "water_level_m"), None), s["warning_level"])}


@router.get("/risk/near")
async def risk_near(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), radius_km: float = Query(30, le=100)):
    """Citizen view: risk on rivers near a place, active warnings there, nearest open shelters."""
    pt = "ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography"
    rivers = await pool().fetch(
        f"""select s.id, s.name, s.basin, s.district, round((ST_Distance(s.geom::geography, {pt}) / 1000)::numeric, 1) distance_km,
                   ra.level, ra.confidence, ra.computed_at
            from stations s
            left join lateral (select level, confidence, computed_at from risk_assessments where station_id = s.id
                               order by computed_at desc limit 1) ra on true
            where s.kind in ('river', 'device_river') and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)
            order by case ra.level when 'CRITICAL' then 0 when 'WARNING' then 1 when 'WATCH' then 2 else 3 end, distance_km
            limit 10""", lat, lon, radius_km)
    warns = await pool().fetch(
        f"""select w.id, w.level, w.status, w.message, w.exercise, w.valid_until, s.name station_name,
                   round((ST_Distance(s.geom::geography, {pt}) / 1000)::numeric, 1) distance_km
            from warnings w join stations s on s.id = w.station_id
            where w.status = 'ACTIVE' and ST_DWithin(s.geom::geography, {pt}, $3 * 1000)
            order by case w.level when 'CRITICAL' then 0 when 'WARNING' then 1 else 2 end""", lat, lon, radius_km)
    shelters = await pool().fetch(
        f"""select id, name, name_local, district, ST_X(geom) lon, ST_Y(geom) lat, capacity, occupancy, status, accessible,
                   accepts_livestock, has_medical, contact, updated_at,
                   round((ST_Distance(geom::geography, {pt}) / 1000)::numeric, 1) distance_km
            from shelters where status = 'open' and occupancy < capacity
            order by geom::geography <-> {pt} limit 5""", lat, lon)
    worst = next((r["level"] for r in rivers if r["level"] in ("CRITICAL", "WARNING", "WATCH")), "NORMAL" if rivers else "UNKNOWN")
    if warns:
        worst = warns[0]["level"]
    profile = await pool().fetchrow("select emergency_numbers from deployment_profile where id = 1")
    return {"level": worst, "rivers": [dict(r) for r in rivers], "warnings": [dict(r) for r in warns],
            "shelters": [dict(r) for r in shelters], "emergency_numbers": profile["emergency_numbers"],
            "note": "Decision support only. Follow instructions from police and local officials on site."}


@router.get("/quality-events")
async def quality_events(open_only: bool = True, limit: int = Query(100, le=500)):
    rows = await pool().fetch(
        """select e.id, e.source_code, e.kind, e.detail, e.opened_at, e.closed_at, s.name station_name, s.id station_id
           from data_quality_events e left join stations s on s.id = e.station_id
           where ($1::bool = false or e.closed_at is null) order by e.opened_at desc limit $2""", open_only, limit)
    return [dict(r) for r in rows]
