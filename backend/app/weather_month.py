"""Thirty-day weather: the last 30 days, the next 16 days and the same 30 days last year, for any place or for a
set of world cities.

Source: Open-Meteo forecast API (past_days + forecast_days, model data blended with observations) and its
ERA5 archive API for last year. CC BY 4.0. Flags use indicative thresholds [D]; national definitions differ.
"""
import asyncio
import time
from datetime import date, timedelta

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["weather_code", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "apparent_temperature_max",
         "precipitation_sum", "snowfall_sum", "precipitation_hours", "wind_speed_10m_max", "wind_gusts_10m_max",
         "wind_direction_10m_dominant", "relative_humidity_2m_mean", "uv_index_max"]
PAST_DAYS = 31          # the API's "past" includes yesterday back; we keep the last 30 complete days
FORECAST_DAYS = 16
PLACE_TTL_S = 3600
WORLD_TTL_S = 3 * 3600

# Major cities on every continent, chosen to cover different climates.
WORLD_CITIES = [
    ("Kathmandu", "Nepal", "Asia", 27.71, 85.32), ("Delhi", "India", "Asia", 28.61, 77.21), ("Mumbai", "India", "Asia", 19.08, 72.88),
    ("Dhaka", "Bangladesh", "Asia", 23.81, 90.41), ("Karachi", "Pakistan", "Asia", 24.86, 67.01), ("Colombo", "Sri Lanka", "Asia", 6.93, 79.86),
    ("Beijing", "China", "Asia", 39.90, 116.41), ("Shanghai", "China", "Asia", 31.23, 121.47), ("Lhasa", "China", "Asia", 29.65, 91.11),
    ("Tokyo", "Japan", "Asia", 35.68, 139.69), ("Seoul", "South Korea", "Asia", 37.57, 126.98), ("Manila", "Philippines", "Asia", 14.60, 120.98),
    ("Bangkok", "Thailand", "Asia", 13.76, 100.50), ("Hanoi", "Vietnam", "Asia", 21.03, 105.85), ("Jakarta", "Indonesia", "Asia", -6.21, 106.85),
    ("Singapore", "Singapore", "Asia", 1.35, 103.82), ("Ulaanbaatar", "Mongolia", "Asia", 47.89, 106.91), ("Kabul", "Afghanistan", "Asia", 34.56, 69.21),
    ("Tehran", "Iran", "Asia", 35.69, 51.39), ("Riyadh", "Saudi Arabia", "Asia", 24.71, 46.68), ("Dubai", "UAE", "Asia", 25.20, 55.27),
    ("Istanbul", "Türkiye", "Europe", 41.01, 28.98), ("Moscow", "Russia", "Europe", 55.76, 37.62), ("London", "UK", "Europe", 51.51, -0.13),
    ("Paris", "France", "Europe", 48.86, 2.35), ("Berlin", "Germany", "Europe", 52.52, 13.40), ("Madrid", "Spain", "Europe", 40.42, -3.70),
    ("Rome", "Italy", "Europe", 41.90, 12.50), ("Stockholm", "Sweden", "Europe", 59.33, 18.07), ("Reykjavík", "Iceland", "Europe", 64.15, -21.94),
    ("Cairo", "Egypt", "Africa", 30.04, 31.24), ("Casablanca", "Morocco", "Africa", 33.57, -7.59), ("Lagos", "Nigeria", "Africa", 6.52, 3.38),
    ("Kinshasa", "DR Congo", "Africa", -4.44, 15.27), ("Addis Ababa", "Ethiopia", "Africa", 9.03, 38.74), ("Nairobi", "Kenya", "Africa", -1.29, 36.82),
    ("Johannesburg", "South Africa", "Africa", -26.20, 28.05), ("Antananarivo", "Madagascar", "Africa", -18.88, 47.51),
    ("New York", "USA", "North America", 40.71, -74.01), ("Chicago", "USA", "North America", 41.88, -87.63),
    ("Houston", "USA", "North America", 29.76, -95.37), ("Los Angeles", "USA", "North America", 34.05, -118.24),
    ("Miami", "USA", "North America", 25.76, -80.19), ("Anchorage", "USA", "North America", 61.22, -149.90),
    ("Toronto", "Canada", "North America", 43.65, -79.38), ("Vancouver", "Canada", "North America", 49.28, -123.12),
    ("Mexico City", "Mexico", "North America", 19.43, -99.13), ("Havana", "Cuba", "North America", 23.11, -82.37),
    ("Bogotá", "Colombia", "South America", 4.71, -74.07), ("Lima", "Peru", "South America", -12.05, -77.04),
    ("Manaus", "Brazil", "South America", -3.12, -60.02), ("São Paulo", "Brazil", "South America", -23.55, -46.63),
    ("Buenos Aires", "Argentina", "South America", -34.60, -58.38), ("Santiago", "Chile", "South America", -33.45, -70.67),
    ("Sydney", "Australia", "Oceania", -33.87, 151.21), ("Perth", "Australia", "Oceania", -31.95, 115.86),
    ("Darwin", "Australia", "Oceania", -12.46, 130.84), ("Auckland", "New Zealand", "Oceania", -36.85, 174.76),
    ("Honolulu", "USA", "Oceania", 21.31, -157.86),
]

_place_cache: dict[tuple[float, float], tuple[float, dict]] = {}
_world_cache: tuple[float, dict] | None = None
_world_lock = asyncio.Lock()


def _days(daily: dict) -> list[dict]:
    keys = {"weather_code": "code", "temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c", "temperature_2m_mean": "tmean_c",
            "apparent_temperature_max": "feels_max_c", "precipitation_sum": "precip_mm", "snowfall_sum": "snow_cm",
            "precipitation_hours": "precip_hours", "wind_speed_10m_max": "wind_max_kmh", "wind_gusts_10m_max": "gust_max_kmh",
            "wind_direction_10m_dominant": "wind_dir_deg", "relative_humidity_2m_mean": "humidity_pct", "uv_index_max": "uv_max"}
    return [{"date": t, **{short: (daily.get(k) or [None] * (i + 1))[i] for k, short in keys.items()}}
            for i, t in enumerate(daily.get("time", []))]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _extreme(days, key, fn):
    vals = [d for d in days if d.get(key) is not None]
    if not vals:
        return None
    d = fn(vals, key=lambda d: d[key])
    return {"date": d["date"], "value": d[key]}


def summarize(days: list[dict]) -> dict:
    """Totals, extremes and indicative hazard flags for a run of days."""
    precip = [d["precip_mm"] for d in days if d.get("precip_mm") is not None]
    tmax = [d["tmax_c"] for d in days if d.get("tmax_c") is not None]
    tmin = [d["tmin_c"] for d in days if d.get("tmin_c") is not None]
    gusts = [d["gust_max_kmh"] for d in days if d.get("gust_max_kmh") is not None]
    s = {
        "days": len(days), "from": days[0]["date"] if days else None, "to": days[-1]["date"] if days else None,
        "temp_mean_c": _mean(d.get("tmean_c") for d in days), "tmax_mean_c": _mean(tmax), "tmin_mean_c": _mean(tmin),
        "hottest": _extreme(days, "tmax_c", max), "coldest": _extreme(days, "tmin_c", min),
        "precip_total_mm": round(sum(precip), 1) if precip else None, "rain_days": sum(p >= 1 for p in precip),
        "wettest": _extreme(days, "precip_mm", max), "snow_total_cm": round(sum(d.get("snow_cm") or 0 for d in days), 1),
        "strongest_gust": _extreme(days, "gust_max_kmh", max), "humidity_mean_pct": _mean(d.get("humidity_pct") for d in days),
        "hot_days_35c": sum(t >= 35 for t in tmax), "frost_days": sum(t <= 0 for t in tmin),
    }
    flags = []
    if any(t >= 40 for t in tmax) or s["hot_days_35c"] >= 3:
        flags.append("heat")
    if any(p >= 50 for p in precip) or (s["precip_total_mm"] or 0) >= 300:
        flags.append("heavy_rain")
    if any(g >= 90 for g in gusts):
        flags.append("storm_wind")
    if any(t <= -15 for t in tmin):
        flags.append("severe_cold")
    if s["snow_total_cm"] >= 10:
        flags.append("snow")
    if precip and len(precip) >= 25 and s["rain_days"] == 0 and (s["tmax_mean_c"] or 0) >= 25:
        flags.append("dry_spell")
    s["flags"] = flags
    return s


def _split(days: list[dict]) -> tuple[list[dict], list[dict]]:
    """API returns PAST_DAYS before today, then today + forecast."""
    return days[PAST_DAYS - 30:PAST_DAYS], days[PAST_DAYS:]


async def _last_year(client: httpx.AsyncClient, lat: float, lon: float, start: str, end: str) -> dict | None:
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        s, e = s.replace(year=s.year - 1), e.replace(year=e.year - 1)
    except ValueError:  # 29 February
        s, e = date.fromisoformat(start) - timedelta(days=365), date.fromisoformat(end) - timedelta(days=365)
    try:
        r = await client.get(ARCHIVE_URL, params={"latitude": lat, "longitude": lon, "start_date": s.isoformat(), "end_date": e.isoformat(),
                                                  "timezone": "auto", "daily": ",".join(d for d in DAILY if d != "uv_index_max")})
        r.raise_for_status()
        return summarize(_days(r.json().get("daily", {})))
    except (httpx.HTTPError, ValueError):
        return None  # comparison is optional


async def place(lat: float, lon: float) -> dict:
    key = (round(lat * 20) / 20, round(lon * 20) / 20)
    hit = _place_cache.get(key)
    if hit and time.time() - hit[0] < PLACE_TTL_S:
        return hit[1]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(FORECAST_URL, params={"latitude": key[0], "longitude": key[1], "timezone": "auto", "past_days": PAST_DAYS,
                                                   "forecast_days": FORECAST_DAYS, "daily": ",".join(DAILY)})
        r.raise_for_status()
        d = r.json()
        days = _days(d.get("daily", {}))
        past, ahead = _split(days)
        last_year = await _last_year(client, key[0], key[1], past[0]["date"], past[-1]["date"]) if past else None
    result = {
        "lat": d.get("latitude"), "lon": d.get("longitude"), "elevation_m": d.get("elevation"), "timezone": d.get("timezone"),
        "today": ahead[0]["date"] if ahead else None, "past_30d": summarize(past), "next_16d": summarize(ahead),
        "same_period_last_year": last_year, "days": days,
        "source": "Open-Meteo (CC BY 4.0): forecast model + ERA5 archive. Model data, not station observations.",
    }
    if len(_place_cache) > 1000:
        _place_cache.clear()
    _place_cache[key] = (time.time(), result)
    return result


async def world() -> dict:
    """Thirty-day summary and 7-day outlook for every city in WORLD_CITIES (one batched request, cached 3 h)."""
    global _world_cache
    async with _world_lock:
        if _world_cache and time.time() - _world_cache[0] < WORLD_TTL_S:
            return _world_cache[1]
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(FORECAST_URL, params={
                "latitude": ",".join(str(c[3]) for c in WORLD_CITIES), "longitude": ",".join(str(c[4]) for c in WORLD_CITIES),
                "timezone": "auto", "past_days": PAST_DAYS, "forecast_days": 7, "daily": ",".join(DAILY)})
            r.raise_for_status()
            data = r.json()
        cities = []
        for (name, country, region, lat, lon), d in zip(WORLD_CITIES, data if isinstance(data, list) else [data]):
            days = _days(d.get("daily", {}))
            past, ahead = _split(days)
            cities.append({"name": name, "country": country, "region": region, "lat": lat, "lon": lon,
                           "past_30d": summarize(past), "next_7d": summarize(ahead)})
        result = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cities": cities,
                  "source": "Open-Meteo (CC BY 4.0) — model data"}
        _world_cache = (time.time(), result)
        return result
