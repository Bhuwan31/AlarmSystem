"""Write adapter output to the database with validation and source-health tracking."""
import logging
from collections import defaultdict

import asyncpg

from app.adapters.base import GridPoint, ObservationRecord, StationRecord
from app.processing.validation import check, station_range

log = logging.getLogger(__name__)


async def upsert_stations(conn: asyncpg.Connection, stations: list[StationRecord], watch_fraction: float,
                          watch_margin_m: float = 1.0) -> dict[tuple[str, str], int]:
    """Watch level = watch_fraction x warning for gauge-zero stations, or warning - watch_margin_m for
    stations whose level is an elevation above sea level (thresholds > 60 m)."""
    if not stations:
        return {}
    rows = await conn.fetch(
        """
        insert into stations (source_code, external_id, kind, name, basin, district, geom, elevation_m,
                              watch_level, warning_level, danger_level, meta, updated_at)
        select s, e, k, n, b, d, ST_SetSRID(ST_MakePoint(lo, la), 4326), el,
               case when w is null then null when w > 60 then w - $14 else w * $13 end, w, dg, m, now()
        from unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::float8[], $8::float8[],
                    $9::float8[], $10::float8[], $11::float8[], $12::jsonb[]) as t(s, e, k, n, b, d, lo, la, el, w, dg, m)
        on conflict (source_code, external_id) do update set
          name = excluded.name, basin = excluded.basin, district = excluded.district, geom = excluded.geom,
          elevation_m = excluded.elevation_m, warning_level = excluded.warning_level,
          danger_level = excluded.danger_level, watch_level = excluded.watch_level, meta = excluded.meta, updated_at = now()
        returning id, source_code, external_id
        """,
        [s.source_code for s in stations], [s.external_id for s in stations], [s.kind for s in stations],
        [s.name for s in stations], [s.basin for s in stations], [s.district for s in stations],
        [s.lon for s in stations], [s.lat for s in stations], [s.elevation_m for s in stations],
        [s.warning_level for s in stations], [s.danger_level for s in stations], [s.meta for s in stations],
        watch_fraction, watch_margin_m,
    )
    return {(r["source_code"], r["external_id"]): r["id"] for r in rows}


async def insert_observations(conn: asyncpg.Connection, obs: list[ObservationRecord], ids: dict[tuple[str, str], int]) -> int:
    if not obs:
        return 0
    station_ids = sorted({ids[(o.source_code, o.external_id)] for o in obs if (o.source_code, o.external_id) in ids})
    history = defaultdict(list)
    for r in await conn.fetch(
        """
        select station_id, variable, value from (
          select station_id, variable, value, row_number() over (partition by station_id, variable order by observed_at desc) rn
          from observations where station_id = any($1::bigint[]) and quality in ('GOOD', 'SUSPECT')
            and observed_at > now() - interval '2 days') x
        where rn <= 12 order by station_id, variable, rn
        """, station_ids):
        history[(r["station_id"], r["variable"])].append(r["value"])

    thresholds = {r["id"]: (r["warning_level"], r["danger_level"]) for r in await conn.fetch(
        "select id, warning_level, danger_level from stations where id = any($1::bigint[])", station_ids)}
    records = []
    for o in obs:
        sid = ids.get((o.source_code, o.external_id))
        if sid is None:
            continue
        bounds = station_range(o.variable, *thresholds.get(sid, (None, None)))
        q = check(o.variable, o.value, history[(sid, o.variable)], bounds)
        records.append((sid, o.variable, o.value, o.unit, o.observed_at, q.quality, q.reason, o.is_simulated, o.raw))
    result = await conn.executemany(
        """
        insert into observations (station_id, variable, value, unit, observed_at, quality, quality_reason, is_simulated, raw)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        on conflict (station_id, variable, observed_at) do nothing
        """, records)
    return len(records)


async def insert_grid(conn: asyncpg.Connection, grid: str, source_code: str, points: list[GridPoint]) -> int:
    if not points:
        return 0
    await conn.copy_records_to_table(
        "weather_grid",
        columns=["grid", "source_code", "lat", "lon", "observed_at", "temperature_c", "humidity_pct", "precipitation_mm",
                 "rain_24h_forecast_mm", "wind_speed_kmh", "wind_dir_deg", "wind_gust_kmh", "cloud_cover_pct", "weather_code",
                 "apparent_temp_c", "pressure_hpa", "tmax_3d_c"],
        records=[(grid, source_code, p.lat, p.lon, p.observed_at, p.temperature_c, p.humidity_pct, p.precipitation_mm,
                  p.rain_24h_forecast_mm, p.wind_speed_kmh, p.wind_dir_deg, p.wind_gust_kmh, p.cloud_cover_pct,
                  p.weather_code, p.apparent_temp_c, p.pressure_hpa, p.tmax_3d_c) for p in points],
    )
    await conn.execute("delete from weather_grid where grid = $1 and received_at < now() - interval '7 days'", grid)
    return len(points)


async def mark_source(conn: asyncpg.Connection, code: str, error: str | None) -> None:
    if error is None:
        await conn.execute("update data_sources set last_success_at = now() where code = $1", code)
        await conn.execute("update data_quality_events set closed_at = now() where source_code = $1 and station_id is null and kind = 'stale' and closed_at is null", code)
    else:
        await conn.execute("update data_sources set last_error = $2, last_error_at = now() where code = $1", code, error[:500])


async def refresh_staleness(conn: asyncpg.Connection) -> None:
    """Open a 'stale' event for every enabled source that missed its staleness window (FR-07)."""
    await conn.execute(
        """
        insert into data_quality_events (source_code, kind, detail)
        select code, 'stale', jsonb_build_object('last_success_at', last_success_at)
        from data_sources
        where enabled and (last_success_at is null or last_success_at < now() - make_interval(secs => staleness_seconds))
        on conflict do nothing
        """)
