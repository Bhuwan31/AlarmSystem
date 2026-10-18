"""Background jobs: one per data source, plus assessment and device health."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import assess, ingest
from app.adapters import dhm, gpm_imerg, insat, open_meteo
from app.adapters.base import AdapterDisabled
from app.config import get_settings
from app.db import pool

log = logging.getLogger(__name__)

WORLD_BBOX = [-180.0, -60.0, 180.0, 75.0]


async def _profile(conn):
    return await conn.fetchrow("select * from deployment_profile where id = 1")


async def _enabled(conn, code: str) -> bool:
    return bool(await conn.fetchval("select enabled from data_sources where code = $1", code))


async def job_dhm() -> None:
    s = get_settings()
    async with pool().acquire() as conn:
        profile = await _profile(conn)
        try:
            data = await dhm.fetch(s.dhm_base_url, s.dhm_socket_path)
            wf = float(profile["policies"].get("watch_fraction", 0.8))
            for event, parser, code in (("river_test", dhm.parse_river, dhm.SOURCE_RIVER),
                                        ("rainfall_watch", dhm.parse_rain, dhm.SOURCE_RAIN)):
                if event not in data:
                    await ingest.mark_source(conn, code, f"no '{event}' response")
                    continue
                stations, obs = parser(data[event])
                async with conn.transaction():
                    ids = await ingest.upsert_stations(conn, stations, wf, float(profile["policies"].get("watch_margin_m", 1.0)))
                    n = await ingest.insert_observations(conn, obs, ids)
                    await ingest.mark_source(conn, code, None)
                log.info("DHM %s: %d stations, %d observations", event, len(stations), n)
        except Exception as e:  # noqa: BLE001 — one source failing must not stop others (NFR-R2)
            log.exception("DHM fetch failed")
            for code in (dhm.SOURCE_RIVER, dhm.SOURCE_RAIN):
                await ingest.mark_source(conn, code, repr(e))


async def job_weather(grid: str) -> None:
    s = get_settings()
    async with pool().acquire() as conn:
        profile = await _profile(conn)
        bbox, step = (list(profile["bbox"]), s.nepal_grid_step_deg) if grid == "nepal" else (WORLD_BBOX, s.global_grid_step_deg)
        try:
            points = await open_meteo.fetch_grid(bbox, step, detailed=(grid == "nepal"))
            async with conn.transaction():
                await ingest.insert_grid(conn, grid, "open_meteo", points)
                await ingest.mark_source(conn, "open_meteo", None)
            log.info("Open-Meteo %s grid: %d points", grid, len(points))
        except Exception as e:  # noqa: BLE001
            log.exception("Open-Meteo %s failed", grid)
            await ingest.mark_source(conn, "open_meteo", repr(e))


async def job_imerg() -> None:
    s = get_settings()
    async with pool().acquire() as conn:
        if not await _enabled(conn, "gpm_imerg"):
            return
        profile = await _profile(conn)
        try:
            points = await gpm_imerg.fetch(list(profile["bbox"]), s.earthdata_token, s.imerg_product, s.imerg_version_tag)
            async with conn.transaction():
                await ingest.insert_grid(conn, "imerg_nepal", "gpm_imerg", points)
                await ingest.mark_source(conn, "gpm_imerg", None)
        except AdapterDisabled as e:
            await ingest.mark_source(conn, "gpm_imerg", f"disabled: {e}")
        except Exception as e:  # noqa: BLE001
            log.exception("IMERG failed")
            await ingest.mark_source(conn, "gpm_imerg", repr(e))


async def job_insat() -> None:
    s = get_settings()
    async with pool().acquire() as conn:
        if not await _enabled(conn, "insat"):
            return
        profile = await _profile(conn)
        try:
            points = insat.collect(s.insat_inbox_dir, list(profile["bbox"]), s.insat_rain_dataset,
                                   s.insat_lat_dataset, s.insat_lon_dataset)
            async with conn.transaction():
                await ingest.insert_grid(conn, "insat_nepal", "insat", points)
                await ingest.mark_source(conn, "insat", None)
        except AdapterDisabled as e:
            await ingest.mark_source(conn, "insat", f"disabled: {e}")
        except Exception as e:  # noqa: BLE001
            log.exception("INSAT failed")
            await ingest.mark_source(conn, "insat", repr(e))


async def job_assess() -> None:
    async with pool().acquire() as conn:
        await ingest.refresh_staleness(conn)
        result = await assess.run(conn)
        log.info("Assessment: %s", result)


async def job_device_health() -> None:
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """update devices set status = 'offline'
               where status <> 'offline' and (last_seen_at is null or last_seen_at < now() - interval '5 minutes')
               returning id, station_id""")
        for r in rows:
            await conn.execute(
                """insert into data_quality_events (source_code, station_id, kind, detail)
                   values ('device', $1, 'device_fault', jsonb_build_object('device_id', $2::text, 'reason', 'missed heartbeat'))
                   on conflict do nothing""", r["station_id"], r["id"])


def build_scheduler() -> AsyncIOScheduler:
    s = get_settings()
    sched = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120})
    sched.add_job(job_dhm, "interval", seconds=s.dhm_poll_s, id="dhm", next_run_time=_soon(2))
    sched.add_job(job_weather, "interval", args=["nepal"], seconds=s.nepal_weather_poll_s, id="weather_nepal", next_run_time=_soon(5))
    sched.add_job(job_weather, "interval", args=["global"], seconds=s.global_weather_poll_s, id="weather_global", next_run_time=_soon(10))
    sched.add_job(job_imerg, "interval", seconds=s.imerg_poll_s, id="imerg", next_run_time=_soon(15))
    sched.add_job(job_insat, "interval", seconds=s.insat_poll_s, id="insat", next_run_time=_soon(20))
    sched.add_job(job_assess, "interval", seconds=120, id="assess", next_run_time=_soon(60))
    sched.add_job(job_device_health, "interval", seconds=60, id="device_health")
    return sched


def _soon(seconds: int):
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
