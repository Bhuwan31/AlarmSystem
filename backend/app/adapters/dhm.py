"""Department of Hydrology and Meteorology (Nepal) live river and rainfall feed.

hydrology.gov.np publishes live readings over socket.io (Engine.IO v3). The site's own client
emits `client_request` with "river_test" (river levels) and "rainfall_watch" (rainfall) and
receives a list of stations on the event with the same name.

Production use needs DHM's agreement (roadmap Phase 1). The adapter only reads public data.
"""
import asyncio
import time
from datetime import datetime

import socketio

from app.adapters.base import ObservationRecord, StationRecord

SOURCE_RIVER = "dhm_river"
SOURCE_RAIN = "dhm_rain"


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def parse_river(items: list[dict]) -> tuple[list[StationRecord], list[ObservationRecord]]:
    stations, obs = [], []
    for it in items or []:
        if it.get("latitude") is None or it.get("longitude") is None:
            continue
        ext = str(it["id"])
        stations.append(StationRecord(
            source_code=SOURCE_RIVER, external_id=ext, kind="river",
            name=(it.get("name") or "").strip(), lat=float(it["latitude"]), lon=float(it["longitude"]),
            basin=(it.get("basin") or "").strip() or None, district=(it.get("district") or "").strip() or None,
            elevation_m=_num(it.get("elevation")),
            warning_level=_num(it.get("warning_level")), danger_level=_num(it.get("danger_level")),
            meta={"station_index": it.get("stationIndex"), "dhm_status": it.get("status"), "trend": it.get("steady"),
                  "series_id": it.get("series_id"), "office": it.get("onm")},
        ))
        wl = it.get("waterLevel") or {}
        when = _ts(wl.get("datetime"))
        if when is not None:
            obs.append(ObservationRecord(SOURCE_RIVER, ext, "water_level_m", _num(wl.get("value")), "m", when,
                                         raw={"waterLevel": wl, "status": it.get("status"), "steady": it.get("steady")}))
    return stations, obs


def parse_rain(items: list[dict]) -> tuple[list[StationRecord], list[ObservationRecord]]:
    stations, obs = [], []
    for it in items or []:
        if it.get("latitude") is None or it.get("longitude") is None:
            continue
        ext = str(it["id"])
        stations.append(StationRecord(
            source_code=SOURCE_RAIN, external_id=ext, kind="rain",
            name=(it.get("name") or "").strip(), lat=float(it["latitude"]), lon=float(it["longitude"]),
            basin=(it.get("basin") or "").strip() or None, district=(it.get("district") or "").strip() or None,
            elevation_m=_num(it.get("elevation")),
            meta={"station_index": it.get("stationIndex"), "dhm_status": it.get("status"), "series_id": it.get("series_id")},
        ))
        latest = it.get("latest_observation") or {}
        when = _ts(latest.get("datetime"))
        if when is None:
            continue
        avgs = {a.get("interval"): a for a in it.get("averages") or []}
        for interval, var in ((1, "rain_1h_mm"), (24, "rain_24h_mm")):
            a = avgs.get(interval)
            if a is not None:
                obs.append(ObservationRecord(SOURCE_RAIN, ext, var, _num(a.get("value")), "mm", when,
                                             raw={"interval": interval, "average": a, "status": it.get("status")}))
    return stations, obs


def _fetch_sync(base_url: str, path: str, events: list[str], timeout_s: float) -> dict[str, list]:
    got: dict[str, list] = {}
    sio = socketio.Client(reconnection=False)

    def handler(name):
        def h(data):
            if isinstance(data, list):
                got[name] = data
        return h

    for ev in events:
        sio.on(ev, handler(ev))

    @sio.event
    def connect():
        for ev in events:
            sio.emit("client_request", ev)

    sio.connect(base_url, socketio_path=path, transports=["polling", "websocket"])
    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline and len(got) < len(events):
            time.sleep(0.3)
    finally:
        sio.disconnect()
    return got


async def fetch(base_url: str, path: str, timeout_s: float = 30) -> dict[str, list]:
    """Returns {"river_test": [...], "rainfall_watch": [...]} (missing keys if DHM did not answer)."""
    return await asyncio.to_thread(_fetch_sync, base_url, path, ["river_test", "rainfall_watch"], timeout_s)
