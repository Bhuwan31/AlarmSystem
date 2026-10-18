"""Weather for one clicked location: current conditions, air flow at several heights, 24 h outlook, heat risk.

Source: Open-Meteo (model data, not an observation). Results are cached for 10 minutes per ~5 km cell
to stay inside the free-tier call budget.
"""
import time

import httpx

URL = "https://api.open-meteo.com/v1/forecast"
LEVELS_M = [10, 80, 120, 180]
LEVELS_HPA = [850, 700, 500, 300]          # ~1.5 km, ~3 km, ~5.5 km, ~9 km
_cache: dict[tuple[float, float], tuple[float, dict]] = {}
TTL_S = 600


def heat_status(tmax_c: list[float | None], apparent_now: float | None) -> dict:
    """Indicative heat-risk class [D]. National heatwave definitions differ; thresholds belong in the
    deployment profile. Uses the next 3 days' maximum temperature and the current feels-like temperature."""
    days = [t for t in tmax_c if t is not None]
    hot_days = sum(t >= 35 for t in days)
    peak = max(days, default=None)
    if (peak is not None and peak >= 40) or (apparent_now is not None and apparent_now >= 45):
        level, text = "EXTREME_HEAT", "Extreme heat: avoid outdoor work 11:00-16:00, drink water often, check on elderly people."
    elif hot_days >= 2 or (apparent_now is not None and apparent_now >= 40):
        level, text = "HEATWAVE", "Heatwave conditions: limit time in the sun, keep hydrated, watch for heat exhaustion."
    elif peak is not None and peak >= 32:
        level, text = "HOT", "Hot: take care during the afternoon."
    else:
        level, text = "NONE", "No heat risk expected in the next 3 days."
    return {"level": level, "advice": text, "max_temp_3d_c": peak, "days_at_or_above_35c": hot_days}


def _parse(d: dict) -> dict:
    cur, hourly, daily = d.get("current", {}), d.get("hourly", {}), d.get("daily", {})
    first = lambda key: (hourly.get(key) or [None])[0]  # noqa: E731
    profile = [{"label": f"{h} m above ground", "height_m": h,
                "speed_kmh": cur.get("wind_speed_10m") if h == 10 else first(f"wind_speed_{h}m"),
                "direction_deg": cur.get("wind_direction_10m") if h == 10 else first(f"wind_direction_{h}m")} for h in LEVELS_M]
    for p in LEVELS_HPA:
        profile.append({"label": f"{p} hPa", "height_m": first(f"geopotential_height_{p}hPa"),
                        "speed_kmh": first(f"wind_speed_{p}hPa"), "direction_deg": first(f"wind_direction_{p}hPa"),
                        "temperature_c": first(f"temperature_{p}hPa")})
    times = hourly.get("time", [])
    outlook = [{"t": t, "temperature_c": hourly["temperature_2m"][i], "humidity_pct": hourly["relative_humidity_2m"][i],
                "wind_kmh": hourly["wind_speed_10m"][i], "precip_mm": hourly["precipitation"][i]} for i, t in enumerate(times)]
    return {
        "lat": d.get("latitude"), "lon": d.get("longitude"), "elevation_m": d.get("elevation"),
        "observed_at": cur.get("time"),
        "current": {
            "temperature_c": cur.get("temperature_2m"), "apparent_temp_c": cur.get("apparent_temperature"),
            "humidity_pct": cur.get("relative_humidity_2m"), "dew_point_c": cur.get("dew_point_2m"),
            "pressure_hpa": cur.get("surface_pressure"), "precipitation_mm": cur.get("precipitation"),
            "cloud_cover_pct": cur.get("cloud_cover"), "wind_speed_kmh": cur.get("wind_speed_10m"),
            "wind_dir_deg": cur.get("wind_direction_10m"), "wind_gust_kmh": cur.get("wind_gusts_10m"),
            "weather_code": cur.get("weather_code"), "is_day": cur.get("is_day"),
        },
        "air_flow": profile,
        "outlook_24h": outlook,
        "daily": [{"date": t, "tmax_c": daily["temperature_2m_max"][i], "tmin_c": daily["temperature_2m_min"][i]}
                  for i, t in enumerate(daily.get("time", []))],
        "heat": heat_status(daily.get("temperature_2m_max", []), cur.get("apparent_temperature")),
        "source": "Open-Meteo (CC BY 4.0) — model data",
    }


async def fetch(lat: float, lon: float) -> dict:
    key = (round(lat * 20) / 20, round(lon * 20) / 20)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    hourly = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation"]
    hourly += [f"wind_speed_{h}m" for h in LEVELS_M[1:]] + [f"wind_direction_{h}m" for h in LEVELS_M[1:]]
    for p in LEVELS_HPA:
        hourly += [f"wind_speed_{p}hPa", f"wind_direction_{p}hPa", f"geopotential_height_{p}hPa", f"temperature_{p}hPa"]
    params = {
        "latitude": key[0], "longitude": key[1], "timezone": "GMT", "forecast_hours": 24, "forecast_days": 3,
        "current": ",".join(["temperature_2m", "apparent_temperature", "relative_humidity_2m", "dew_point_2m", "surface_pressure",
                             "precipitation", "cloud_cover", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
                             "weather_code", "is_day"]),
        "hourly": ",".join(hourly),
        "daily": "temperature_2m_max,temperature_2m_min",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(URL, params=params)
        resp.raise_for_status()
    result = _parse(resp.json())
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.time(), result)
    return result
