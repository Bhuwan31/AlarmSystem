"""Training and live data for the ML models: daily river discharge (GloFAS v4 via the Open-Meteo flood API) and
daily rainfall (ERA5 archive for history, Open-Meteo forecast for the live outlook) at each river station.

GloFAS is a hydrological model run on real weather (reanalysis), not a gauge record, but it is the only free,
multi-year, flood-including discharge series for Nepal's rivers. Each station is snapped to the largest river
cell within ~5 km so a small side stream is not used by mistake.
"""
import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np

log = logging.getLogger(__name__)

FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_DIR = Path(__file__).resolve().parents[2] / "ml_data"
SNAP_STEP = 0.05          # GloFAS grid spacing (degrees)
SNAP_WINDOW = ("2024-08-01", "2024-08-14")   # a monsoon fortnight: the main stem has clearly the biggest flow

# One or two gauges per major basin, east to west, so the models see every river regime in Nepal.
TRAINING_STATIONS = [
    "Sapta Koshi at Chatara (new)", "Arun River at Simle", "Tamor River at Mulghat", "Sunkoshi at Pachuwarghat",
    "Tamakoshi at Busti", "Bhote Koshi at Bahrabise", "Kankai River at Mainachuli", "Kamala at Ranibas",
    "Bagmati River at Khokana", "Bagmati River at Gaurighat", "East Rapti at Rajaiya", "Narayani at Devghat",
    "Trishuli at Betrawati", "Marsyangdi at Bhakundabesi", "Seti Gandaki at Damauli", "Kali Gandaki at Jomsom",
    "Myagdi at Mangalghat", "West Rapti at Bagasoti", "Babai at Chepang", "Bheri at Jamu", "Karnali at Chisapani",
    "Humla Karnali at Lalighat", "West Seti at Dipayal", "Mahakali at Parigaon",
]

# Which model stations drain into which (flood waves travel downstream in about 1-2 days).
UPSTREAM = {
    "Sapta Koshi at Chatara (new)": ["Arun River at Simle", "Tamor River at Mulghat", "Sunkoshi at Pachuwarghat", "Tamakoshi at Busti"],
    "Sunkoshi at Pachuwarghat": ["Bhote Koshi at Bahrabise"],
    "Bagmati River at Khokana": ["Bagmati River at Gaurighat"],
    "Narayani at Devghat": ["Trishuli at Betrawati", "Marsyangdi at Bhakundabesi", "Seti Gandaki at Damauli",
                            "Kali Gandaki at Jomsom", "Myagdi at Mangalghat"],
    "Karnali at Chisapani": ["Bheri at Jamu", "Humla Karnali at Lalighat", "West Seti at Dipayal"],
}
HEADWATER_NORTH = 0.35   # degrees north of a station (about 40 km), towards the high Himalaya where its snow and ice melt


def headwater(lat: float, lon: float) -> tuple[float, float]:
    return round(min(lat + HEADWATER_NORTH, 30.3), 3), round(lon, 3)


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
    """GET with patience for the free tier's per-minute / per-hour limits. Always returns a list of locations."""
    for attempt in range(40):
        r = await client.get(url, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            wait = 65 if "minute" in r.text.lower() or r.status_code >= 500 else 600
            log.warning("open-meteo %s (%s); waiting %ss", r.status_code, r.text[:120], wait)
            await asyncio.sleep(wait if attempt < 39 else 0)
            continue
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, list) else [body]
    raise RuntimeError(f"open-meteo kept refusing {url}")


def _coords(points: list[tuple[float, float]]) -> dict:
    return {"latitude": ",".join(f"{p[0]:.3f}" for p in points), "longitude": ",".join(f"{p[1]:.3f}" for p in points)}


async def snap(client: httpx.AsyncClient, lat: float, lon: float, max_flow: float | None = None, reach: int = 2) -> tuple[float, float, float]:
    """Largest-flow GloFAS cell in a (2*reach+1)^2 neighbourhood, optionally below `max_flow` (so a tributary gauge
    does not land on the bigger river it joins). Returns (cell_lat, cell_lon, median flow m³/s)."""
    pts = [(lat + dy * SNAP_STEP, lon + dx * SNAP_STEP) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)]
    rows = await _get(client, FLOOD_URL, {**_coords(pts), "daily": "river_discharge",
                                          "start_date": SNAP_WINDOW[0], "end_date": SNAP_WINDOW[1]})
    best = (-1.0, lat, lon)
    for row in rows:
        vals = sorted(v for v in row["daily"]["river_discharge"] if v is not None)
        if vals and vals[len(vals) // 2] > best[0] and (max_flow is None or vals[len(vals) // 2] < max_flow):
            best = (vals[len(vals) // 2], row["latitude"], row["longitude"])
    return round(best[1], 3), round(best[2], 3), best[0]


async def history(client: httpx.AsyncClient, cells: list[tuple[float, float]], start: str, end: str) -> list[dict]:
    """Daily discharge and rain for each cell over [start, end]. Cached on disk so a rerun costs no API calls."""
    CACHE_DIR.mkdir(exist_ok=True)
    out = []
    for lat, lon in cells:
        f = CACHE_DIR / f"{lat:.3f}_{lon:.3f}_{start}_{end}.json"
        if f.exists():
            out.append(json.loads(f.read_text()))
            continue
        q = (await _get(client, FLOOD_URL, {**_coords([(lat, lon)]), "daily": "river_discharge", "start_date": start, "end_date": end}))[0]
        r = (await _get(client, ARCHIVE_URL, {**_coords([(lat, lon)]), "daily": "precipitation_sum", "timezone": "GMT",
                                              "start_date": start, "end_date": end}))[0]
        rec = {"dates": q["daily"]["time"], "discharge": q["daily"]["river_discharge"],
               "rain": dict(zip(r["daily"]["time"], r["daily"]["precipitation_sum"]))}
        rec["rain"] = [rec["rain"].get(d) for d in rec["dates"]]
        f.write_text(json.dumps(rec))
        out.append(rec)
        log.info("downloaded %s,%s (%d days)", lat, lon, len(rec["dates"]))
    return out


async def history_extra(client: httpx.AsyncClient, cells: list[tuple[float, float]], heads: list[tuple[float, float]],
                        start: str, end: str) -> list[dict]:
    """Soil moisture (top 1 m) at each river cell and temperature + snowfall at its headwater point, daily (ERA5)."""
    CACHE_DIR.mkdir(exist_ok=True)
    out = []
    for (lat, lon), (hlat, hlon) in zip(cells, heads):
        f = CACHE_DIR / f"{lat:.3f}_{lon:.3f}_extra_{hlat:.3f}_{start}_{end}.json"
        if f.exists():
            out.append(json.loads(f.read_text()))
            continue
        a = (await _get(client, ARCHIVE_URL, {**_coords([(lat, lon)]), "daily": "soil_moisture_0_to_100cm_mean", "timezone": "GMT",
                                              "start_date": start, "end_date": end}))[0]["daily"]
        h = (await _get(client, ARCHIVE_URL, {**_coords([(hlat, hlon)]), "daily": "temperature_2m_mean,snowfall_sum", "timezone": "GMT",
                                              "start_date": start, "end_date": end}))[0]["daily"]
        ht, hs = dict(zip(h["time"], h["temperature_2m_mean"])), dict(zip(h["time"], h["snowfall_sum"]))
        rec = {"dates": a["time"], "soil": a["soil_moisture_0_to_100cm_mean"],
               "htemp": [ht.get(d) for d in a["time"]], "hsnow": [hs.get(d) for d in a["time"]]}
        f.write_text(json.dumps(rec))
        out.append(rec)
        log.info("downloaded soil and headwater weather for %s,%s (%d days)", lat, lon, len(rec["dates"]))
    return out


SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"


def _members(daily: dict, prefix: str) -> list[list]:
    return [v for k, v in daily.items() if k == prefix or k.startswith(prefix + "_member")]


def _mean_by_day(daily: dict, prefix: str) -> dict:
    ms = _members(daily, prefix)
    out = {}
    for j, d in enumerate(daily["time"]):
        vals = [m[j] for m in ms if m[j] is not None]
        if vals:
            out[d] = sum(vals) / len(vals)
    return out


def _spread(daily: dict, prefix: str) -> dict:
    """For each day d: spread (std of log) of the ensemble members' rain totals over the 3 days after d."""
    ms = [np.array([np.nan if v is None else v for v in m], dtype=float) for m in _members(daily, prefix)]
    out: dict = {}
    if not ms:
        return out
    M = np.stack(ms)
    for j, d in enumerate(daily["time"]):
        tot = M[:, j + 1:j + 4]
        if tot.shape[1] < 3:
            continue
        tot = tot[~np.isnan(tot).any(1)].sum(1)
        if len(tot) > 5:
            out[d] = float(np.clip(np.std(np.log1p(tot)), 0.05, 1.0))
    return out


async def live_all(cells: list[tuple[float, float]], heads: list[tuple[float, float]], past_days: int = 40,
                   days: int = 30) -> tuple[str, list[dict]]:
    """Everything the live outlooks need, per cell, on one daily calendar from `past_days` ago to today + days + 7.

    river flow   GloFAS 51-member ensemble, past + next `days` days (member 0 is the main forecast)
    rain         forecast for 16 days, then the ECMWF seasonal ensemble mean
    uncertainty  spread of the 51-member ECMWF rain ensemble (15 days), then of the seasonal ensemble
    soil         forecast top-1 m soil moisture for 16 days, then held at the last value
    headwater    temperature and snowfall: forecast for 16 days, then the seasonal ensemble mean
    """
    today = date.today()
    first = today - timedelta(days=past_days)
    cal = [(first + timedelta(days=k)).isoformat() for k in range(past_days + days + 8)]
    async with httpx.AsyncClient(timeout=120) as client:
        flood, fc, hfc, ens, sea, hsea = [], [], [], [], [], []
        for i in range(0, len(cells), 4):
            flood += await _get(client, FLOOD_URL, {**_coords(cells[i:i + 4]), "daily": "river_discharge", "ensemble": "true",
                                                    "past_days": past_days, "forecast_days": days})
        for i in range(0, len(cells), 8):
            ens += await _get(client, ENSEMBLE_URL, {**_coords(cells[i:i + 8]), "models": "ecmwf_ifs025",
                                                     "daily": "precipitation_sum", "forecast_days": 15})
        for i in range(0, len(cells), 25):
            c, h = cells[i:i + 25], heads[i:i + 25]
            try:
                fc += await _get(client, FORECAST_URL, {**_coords(c), "daily": "precipitation_sum,soil_moisture_0_to_100cm_mean",
                                                        "timezone": "GMT", "past_days": past_days, "forecast_days": 16})
                hfc += await _get(client, FORECAST_URL, {**_coords(h), "daily": "temperature_2m_mean,snowfall_sum",
                                                         "timezone": "GMT", "past_days": past_days, "forecast_days": 16})
            except httpx.HTTPError as exc:
                # The forecast service is down: use the reanalysis archive for the past (a few days behind) and let the
                # rain ensemble / seasonal forecast fill the days after it; soil is then held at its last known value.
                log.warning("open-meteo forecast unavailable (%r); falling back to archive + ensemble", exc)
                fc = fc[:i]
                hfc = hfc[:i]
                span = {"timezone": "GMT", "start_date": first.isoformat(), "end_date": (today - timedelta(days=1)).isoformat()}
                fc += await _get(client, ARCHIVE_URL, {**_coords(c), "daily": "precipitation_sum,soil_moisture_0_to_100cm_mean", **span})
                hfc += await _get(client, ARCHIVE_URL, {**_coords(h), "daily": "temperature_2m_mean,snowfall_sum", **span})
            sea += await _get(client, SEASONAL_URL, {**_coords(c), "daily": "precipitation_sum", "forecast_days": days + 15})
            hsea += await _get(client, SEASONAL_URL, {**_coords(h), "daily": "temperature_2m_max,temperature_2m_min,snowfall_sum",
                                                      "forecast_days": days + 15})
    rows = []
    for q, f, hf, e, se, hs in zip(flood, fc, hfc, ens, sea, hsea):
        fd, hd, qd = f["daily"], hf["daily"], q["daily"]
        rain = {d: v for d, v in zip(fd["time"], fd["precipitation_sum"]) if v is not None}
        for d, v in _mean_by_day(e["daily"], "precipitation_sum").items():
            rain.setdefault(d, v)                                 # ensemble mean only where the main forecast has no value
        first_seasonal = (date.fromisoformat(max(rain)) + timedelta(days=1)).isoformat() if rain else today.isoformat()
        rain_sea = _mean_by_day(se["daily"], "precipitation_sum")
        soil = {d: v for d, v in zip(fd["time"], fd["soil_moisture_0_to_100cm_mean"]) if v is not None}
        htemp = {d: v for d, v in zip(hd["time"], hd["temperature_2m_mean"]) if v is not None}
        hsnow = {d: v for d, v in zip(hd["time"], hd["snowfall_sum"]) if v is not None}
        tmax, tmin = _mean_by_day(hs["daily"], "temperature_2m_max"), _mean_by_day(hs["daily"], "temperature_2m_min")
        snow_sea = _mean_by_day(hs["daily"], "snowfall_sum")
        members = []
        for m in _members(qd, "river_discharge"):
            by_day = dict(zip(qd["time"], m))
            members.append([by_day.get(d) for d in cal])
        unc = _spread(se["daily"], "precipitation_sum")
        unc.update(_spread(e["daily"], "precipitation_sum"))     # the 15-day ensemble wins where both exist
        rows.append({
            "dates": cal, "today_index": past_days, "members": members,
            "rain": [rain[d] if d in rain else rain_sea.get(d, 0.0) for d in cal],
            "soil": [soil.get(d) for d in cal],
            "htemp": [htemp[d] if d in htemp else ((tmax[d] + tmin[d]) / 2 if d in tmax and d in tmin else None) for d in cal],
            "hsnow": [hsnow[d] if d in hsnow else snow_sea.get(d, 0.0) for d in cal],
            "uncertainty": [unc.get(d) for d in cal],
            "first_seasonal_day": first_seasonal,
        })
    return today.isoformat(), rows
