"""Open-Meteo current weather + 24 h rainfall forecast on a regular lat/lon grid.

Free tier is for non-commercial use (CC BY 4.0). Multi-location requests count as one
call per location, so grid spacing and poll interval are configurable.
"""
import asyncio
import math
from datetime import datetime, timezone

import httpx

from app.adapters.base import GridPoint

URL = "https://api.open-meteo.com/v1/forecast"
CURRENT = ",".join([
    "temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover", "weather_code", "apparent_temperature", "surface_pressure",
])
BATCH = 100


def grid_points(bbox: list[float], step: float) -> list[tuple[float, float]]:
    """Cell-centre points covering bbox = [min_lon, min_lat, max_lon, max_lat]."""
    min_lon, min_lat, max_lon, max_lat = bbox
    n_lat = math.ceil((max_lat - min_lat) / step - 1e-9)
    n_lon = math.ceil((max_lon - min_lon) / step - 1e-9)
    return [(round(min_lat + (i + 0.5) * step, 4), round(min_lon + (j + 0.5) * step, 4))
            for i in range(n_lat) for j in range(n_lon)]


def parse_response(payload, points: list[tuple[float, float]]) -> list[GridPoint]:
    items = payload if isinstance(payload, list) else [payload]
    out = []
    for (lat, lon), item in zip(points, items):
        cur = item.get("current") or {}
        hourly = (item.get("hourly") or {}).get("precipitation") or []
        observed = datetime.fromisoformat(cur["time"]).replace(tzinfo=timezone.utc) if cur.get("time") else datetime.now(timezone.utc)
        out.append(GridPoint(
            lat=lat, lon=lon, observed_at=observed,
            temperature_c=cur.get("temperature_2m"),
            humidity_pct=cur.get("relative_humidity_2m"),
            precipitation_mm=cur.get("precipitation"),
            rain_24h_forecast_mm=round(sum(v for v in hourly if v is not None), 2) if hourly else None,
            wind_speed_kmh=cur.get("wind_speed_10m"),
            wind_dir_deg=cur.get("wind_direction_10m"),
            wind_gust_kmh=cur.get("wind_gusts_10m"),
            cloud_cover_pct=cur.get("cloud_cover"),
            weather_code=cur.get("weather_code"),
            apparent_temp_c=cur.get("apparent_temperature"),
            pressure_hpa=cur.get("surface_pressure"),
            tmax_3d_c=max((v for v in (item.get("daily") or {}).get("temperature_2m_max") or [] if v is not None), default=None),
        ))
    return out


async def _get(client: httpx.AsyncClient, params: dict, retries: int = 3) -> httpx.Response:
    """GET with back-off on HTTP 429 (Open-Meteo free tier has per-minute and per-hour limits)."""
    for attempt in range(retries + 1):
        resp = await client.get(URL, params=params)
        if resp.status_code != 429 or attempt == retries:
            resp.raise_for_status()
            return resp
        await asyncio.sleep(65 * (attempt + 1))
    raise RuntimeError("unreachable")


async def fetch_grid(bbox: list[float], step: float, client: httpx.AsyncClient | None = None,
                     detailed: bool = True, pause_s: float = 5.0) -> list[GridPoint]:
    """detailed=False skips the hourly rain series (world grid) to save API budget."""
    points = grid_points(bbox, step)
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        result: list[GridPoint] = []
        for i in range(0, len(points), BATCH):
            chunk = points[i:i + BATCH]
            params = {
                "latitude": ",".join(str(p[0]) for p in chunk),
                "longitude": ",".join(str(p[1]) for p in chunk),
                "current": CURRENT,
                "daily": "temperature_2m_max",
                "forecast_days": 3,
                "timezone": "GMT",
            }
            if detailed:
                params.update({"hourly": "precipitation", "forecast_hours": 24})
            resp = await _get(client, params)
            result.extend(parse_response(resp.json(), chunk))
            if i + BATCH < len(points):
                await asyncio.sleep(pause_s)   # spread batches to stay under the per-minute limit
        return result
    finally:
        if own:
            await client.aclose()
