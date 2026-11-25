"""Hour-by-hour weather card for any place and any date: current conditions, 8 days of daily highs and lows, and
hourly temperature, rain chance and wind for those 8 days.

Sources: Open-Meteo forecast API (dates from 92 days ago to 15 days ahead, model data blended with observations),
its ERA5 archive API for older dates (no rain-chance field there) and OpenStreetMap Nominatim for the place name.
"""
import time
from datetime import date, timedelta

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
HOURLY = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "precipitation_probability", "precipitation",
          "weather_code", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "is_day"]
DAILY = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "precipitation_sum",
         "wind_speed_10m_max", "wind_direction_10m_dominant", "sunrise", "sunset", "uv_index_max"]
CURRENT = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "precipitation", "weather_code",
           "wind_speed_10m", "wind_direction_10m", "is_day"]
WINDOW_DAYS = 8
FORECAST_PAST_DAYS = 92   # how far back the forecast API serves past days
FORECAST_AHEAD_DAYS = 15  # last day the forecast API can return is today + 15
ARCHIVE_LAG_DAYS = 6      # ERA5 archive is usually complete up to about 5 days ago
EARLIEST = date(1940, 1, 1)
TTL_S = 900
NAME_TTL_S = 7 * 86400

_cache: dict[tuple[float, float, str], tuple[float, dict]] = {}
_names: dict[tuple[float, float], tuple[float, str | None]] = {}


def _rows(block: dict, keys: dict[str, str]) -> list[dict]:
    times = block.get("time") or []
    return [{"t": t, **{short: (block.get(k) or [None] * len(times))[i] for k, short in keys.items()}} for i, t in enumerate(times)]


HOUR_KEYS = {"temperature_2m": "temp_c", "apparent_temperature": "feels_c", "relative_humidity_2m": "humidity_pct",
             "precipitation_probability": "precip_prob", "precipitation": "precip_mm", "weather_code": "code",
             "wind_speed_10m": "wind_kmh", "wind_direction_10m": "wind_dir_deg", "wind_gusts_10m": "gust_kmh", "is_day": "is_day"}
DAY_KEYS = {"weather_code": "code", "temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c",
            "precipitation_probability_max": "precip_prob", "precipitation_sum": "precip_mm", "wind_speed_10m_max": "wind_max_kmh",
            "wind_direction_10m_dominant": "wind_dir_deg", "sunrise": "sunrise", "sunset": "sunset", "uv_index_max": "uv_max"}


async def place_name(client: httpx.AsyncClient, lat: float, lon: float) -> str | None:
    """Neighbourhood / district / city name from OpenStreetMap; None if the lookup fails."""
    key = (round(lat, 2), round(lon, 2))
    hit = _names.get(key)
    if hit and time.time() - hit[0] < NAME_TTL_S:
        return hit[1]
    name = None
    try:
        r = await client.get(REVERSE_URL, params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14, "accept-language": "en"},
                             headers={"User-Agent": "AMHEWS early-warning prototype (university project)"})
        r.raise_for_status()
        a = r.json().get("address") or {}
        local = a.get("suburb") or a.get("neighbourhood") or a.get("quarter") or a.get("village") or a.get("town") or a.get("city_district")
        wider = a.get("city") or a.get("county") or a.get("state_district") or a.get("state")
        parts = [p for p in (local, wider if wider != local else None, a.get("country")) if p]
        name = ", ".join(parts[:3]) or None
    except (httpx.HTTPError, ValueError):
        pass
    _names[key] = (time.time(), name)
    return name


async def card(lat: float, lon: float, start: date | None = None) -> dict:
    """Eight days from `start` (default: today at the place). Older dates come from the ERA5 archive."""
    lat, lon = round(lat, 3), round(lon, 3)
    key = (lat, lon, start.isoformat() if start else "")
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]

    async with httpx.AsyncClient(timeout=25) as client:
        # Ask for "today" first so the window is in the place's own time zone, not the server's.
        params = {"latitude": lat, "longitude": lon, "timezone": "auto", "current": ",".join(CURRENT),
                  "daily": "temperature_2m_max", "forecast_days": 1}
        r = await client.get(FORECAST_URL, params=params)
        r.raise_for_status()
        now = r.json()
        today = date.fromisoformat(now["daily"]["time"][0])
        first = max(start or today, EARLIEST)
        first = min(first, today + timedelta(days=FORECAST_AHEAD_DAYS - WINDOW_DAYS + 1))
        last = first + timedelta(days=WINDOW_DAYS - 1)

        if first >= today - timedelta(days=FORECAST_PAST_DAYS):
            source = "Open-Meteo forecast (model data blended with observations)"
            r = await client.get(FORECAST_URL, params={"latitude": lat, "longitude": lon, "timezone": "auto", "hourly": ",".join(HOURLY),
                                                       "daily": ",".join(DAILY), "start_date": first.isoformat(), "end_date": last.isoformat()})
        else:
            source = "Open-Meteo ERA5 archive (reanalysis; no rain-chance field)"
            last = min(last, today - timedelta(days=ARCHIVE_LAG_DAYS))
            r = await client.get(ARCHIVE_URL, params={"latitude": lat, "longitude": lon, "timezone": "auto",
                                                      "hourly": ",".join(h for h in HOURLY if h != "precipitation_probability"),
                                                      "daily": ",".join(d for d in DAILY if d not in ("precipitation_probability_max", "uv_index_max")),
                                                      "start_date": first.isoformat(), "end_date": last.isoformat()})
        r.raise_for_status()
        body = r.json()
        name = await place_name(client, lat, lon)

    cur = now.get("current") or {}
    out = {
        "lat": lat, "lon": lon, "name": name, "timezone": now.get("timezone"), "elevation_m": now.get("elevation"),
        "today": today.isoformat(), "start": first.isoformat(), "end": last.isoformat(),
        "min_date": EARLIEST.isoformat(), "max_date": (today + timedelta(days=FORECAST_AHEAD_DAYS)).isoformat(),
        "current": {"time": cur.get("time"), "temp_c": cur.get("temperature_2m"), "feels_c": cur.get("apparent_temperature"),
                    "humidity_pct": cur.get("relative_humidity_2m"), "precip_mm": cur.get("precipitation"), "code": cur.get("weather_code"),
                    "wind_kmh": cur.get("wind_speed_10m"), "wind_dir_deg": cur.get("wind_direction_10m"), "is_day": cur.get("is_day")},
        "days": [{"date": d.pop("t"), **d} for d in _rows(body.get("daily") or {}, DAY_KEYS)],
        "hours": _rows(body.get("hourly") or {}, HOUR_KEYS),
        "source": f"{source}; place name © OpenStreetMap contributors",
    }
    _cache[key] = (time.time(), out)
    return out
