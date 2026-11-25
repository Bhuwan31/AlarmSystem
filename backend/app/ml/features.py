"""Feature engineering shared by training and the live outlook, so both always see identical inputs.

Discharge is standardised per station on the log scale (qn = (log1p(Q) - mu) / sd) so one model serves rivers
from 5 m³/s to 5,000 m³/s. Flood classes use each station's own discharge percentiles from the training years:
WATCH ≥ P90, WARNING ≥ P97, CRITICAL ≥ P99.5 of daily flow (about 36, 11 and 2 days a year).
"""
import math

import numpy as np

LEVELS = ["NORMAL", "WATCH", "WARNING", "CRITICAL"]
PCTL = (90.0, 97.0, 99.5)
LOOKBACK = 30            # days of history each sample needs
HORIZON = 3              # days ahead for the class target and the 3-day regression
SEQ_LEN = 30             # LSTM input length

FEATURES = [
    "flow_now", "flow_change_1d", "flow_change_3d", "flow_mean_7d", "flow_max_30d",
    "rain_today", "rain_3d", "rain_7d", "rain_30d", "forecast_rain_1d", "forecast_rain_3d",
    "season_sin", "season_cos", "class_now",
    # added inputs
    "upstream_flow_now", "upstream_change_1d", "upstream_change_3d", "has_upstream",   # flood wave coming from upstream
    "forecast_rain_7d", "forecast_uncertainty",                                          # rain further ahead, and how sure
    "soil_moisture", "soil_moisture_change_7d",                                          # how wet the ground already is
    "headwater_temp_3d", "headwater_warmth_7d", "headwater_snow_30d",                    # snow / glacier melt in the mountains
]
RAIN_ONLY = ["rain_today", "rain_3d", "rain_7d", "rain_30d", "forecast_rain_1d", "forecast_rain_3d", "forecast_rain_7d",
             "forecast_uncertainty", "season_sin", "season_cos"]
RAIN_IDX = [FEATURES.index(f) for f in RAIN_ONLY]
FC_FEATURES = ["forecast_rain_1d", "forecast_rain_3d", "forecast_rain_7d", "forecast_uncertainty"]
FC_IDX = [FEATURES.index(f) for f in FC_FEATURES]
SEQ_FEATURES = ["flow", "rain", "upstream_flow", "soil_moisture", "headwater_temp", "season_sin", "season_cos"]
UNCERTAINTY_RANGE = (0.1, 0.8)   # training forecasts are the real rain x lognormal(0, sigma), sigma drawn from this range


def station_stats(q: np.ndarray) -> dict:
    """Per-station scaling and flood thresholds, from training-period discharge only."""
    q = q[~np.isnan(q)]
    lq = np.log1p(q)
    th = np.percentile(q, PCTL)
    return {"mu": float(lq.mean()), "sd": float(max(lq.std(), 1e-3)), "q_watch": float(th[0]), "q_warning": float(th[1]), "q_critical": float(th[2])}


def qn(q, st: dict):
    return (np.log1p(q) - st["mu"]) / st["sd"]


def q_from_qn(z, st: dict):
    return np.expm1(np.asarray(z) * st["sd"] + st["mu"])


def classify(q, st: dict):
    q = np.asarray(q, dtype=float)
    return (q >= st["q_watch"]).astype(int) + (q >= st["q_warning"]) + (q >= st["q_critical"])


def _season(day_of_year: int) -> tuple[float, float]:
    a = 2 * math.pi * day_of_year / 365.25
    return math.sin(a), math.cos(a)


def clean(series, fill: float | None = None) -> np.ndarray:
    """None → NaN, then fill short gaps by carrying the last value forward (and back-fill the start).
    With `fill`, anything still missing becomes that value."""
    x = np.array([np.nan if v is None else v for v in series], dtype=float)
    for i in range(1, len(x)):
        if np.isnan(x[i]):
            x[i] = x[i - 1]
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok):
        x[:ok[0]] = x[ok[0]]
    if fill is not None:
        x = np.nan_to_num(x, nan=fill)
    return x


def context(q: np.ndarray, rain: np.ndarray, st: dict, q_up: np.ndarray | None, soil: np.ndarray, htemp: np.ndarray,
            hsnow: np.ndarray) -> dict:
    """Everything one station needs to build features, as arrays on the same daily dates.
    q_up = summed flow of the stations upstream (None if none); it is put on this station's own scale, so
    upstream_flow_now near flow_now means the water upstream is about what normally reaches here."""
    return {"z": qn(q, st), "q": q, "rain": rain, "zup": None if q_up is None else qn(q_up, st),
            "soil": soil, "htemp": htemp, "hsnow": hsnow, "st": st}


def vector(c: dict, t: int, doy: int, fc: tuple[float, float, float, float]) -> np.ndarray:
    """Feature vector for day t (needs t >= LOOKBACK). fc = (forecast rain next 1 / 3 / 7 days in mm, uncertainty)."""
    z, q, rain, zup, soil, ht, hs = c["z"], c["q"], c["rain"], c["zup"], c["soil"], c["htemp"], c["hsnow"]
    s, co = _season(doy)
    up = (0.0, 0.0, 0.0, 0.0) if zup is None else (zup[t], zup[t] - zup[t - 1], zup[t] - zup[t - 3], 1.0)
    return np.array([
        z[t], z[t] - z[t - 1], z[t] - z[t - 3], z[t - 6:t + 1].mean(), z[t - 29:t + 1].max(),
        rain[t] / 50, rain[t - 2:t + 1].sum() / 100, rain[t - 6:t + 1].sum() / 150, rain[t - 29:t + 1].sum() / 500,
        fc[0] / 50, fc[1] / 100, s, co, classify(q[t], c["st"]) / 3,
        *up, fc[2] / 200, fc[3],
        (soil[t] - 0.3) / 0.1, (soil[t] - soil[t - 7]) / 0.05,
        ht[t - 2:t + 1].mean() / 15, np.maximum(ht[t - 6:t + 1], 0).sum() / 50, hs[t - 29:t + 1].sum() / 100,
    ], dtype=np.float32)


def sequence(c: dict, t: int, doys: list[int]) -> np.ndarray:
    """30-day-reader input: the last SEQ_LEN days of [flow, rain, upstream flow, soil, headwater temperature, season]."""
    rows = []
    for k in range(t - SEQ_LEN + 1, t + 1):
        s, co = _season(doys[k])
        up = 0.0 if c["zup"] is None else c["zup"][k]
        rows.append([c["z"][k], c["rain"][k] / 50, up, (c["soil"][k] - 0.3) / 0.1, c["htemp"][k] / 15, s, co])
    return np.array(rows, dtype=np.float32)


AHEAD = 7    # days of real rain needed after t to make the training forecast


def build(dates: list[str], c: dict, rng: np.random.Generator | None = None) -> dict:
    """All supervised samples for one station. Forecast rain in training is the rain that really fell, times
    lognormal noise whose size (the uncertainty input) differs per sample, so the models learn to lean on the
    forecast when it is confident and less when it is not."""
    from datetime import date as _d
    z, q, rain, st = c["z"], c["q"], c["rain"], c["st"]
    doys = [_d.fromisoformat(d).timetuple().tm_yday for d in dates]
    rng = rng or np.random.default_rng(0)
    X, S, y_cls, y1, y3, t_idx = [], [], [], [], [], []
    cls = classify(q, st)
    bad = np.isnan(z) | np.isnan(rain) | (np.isnan(c["zup"]) if c["zup"] is not None else False)
    for t in range(LOOKBACK, len(q) - AHEAD):
        if bad[t - LOOKBACK:t + AHEAD + 1].any():
            continue
        sigma = rng.uniform(*UNCERTAINTY_RANGE)
        n = rng.lognormal(0, sigma, 3)
        fc = (rain[t + 1] * n[0], rain[t + 1:t + 4].sum() * n[1], rain[t + 1:t + 8].sum() * n[2], sigma)
        X.append(vector(c, t, doys[t], fc))
        S.append(sequence(c, t, doys))
        y_cls.append(int(cls[t + 1:t + HORIZON + 1].max()))
        y1.append(z[t + 1] - z[t])
        y3.append(z[t + 3] - z[t])
        t_idx.append(t)
    return {"X": np.array(X), "S": np.array(S), "y_cls": np.array(y_cls), "y1": np.array(y1, dtype=np.float32),
            "y3": np.array(y3, dtype=np.float32), "t": np.array(t_idx), "dates": [dates[t] for t in t_idx]}


# ---- sensor anomaly features (Isolation Forest, real gauge readings) ----
ANOMALY_FEATURES = ["distance_from_typical", "jump", "rate_per_hour", "gap_hours", "flat_run"]


def anomaly_matrix(times: list, values: list[float]) -> np.ndarray:
    """One row per reading of one gauge, oldest first. Scaled by the gauge's own typical variation (MAD)."""
    v = np.asarray(values, dtype=float)
    med = np.median(v)
    scale = max(1.4826 * np.median(np.abs(v - med)), 0.02)
    rows, run = [], 0
    for i in range(len(v)):
        gap = (times[i] - times[i - 1]).total_seconds() / 3600 if i else 0.25
        jump = abs(v[i] - v[i - 1]) if i else 0.0
        run = run + 1 if i and v[i] == v[i - 1] else 0
        rows.append([min(abs(v[i] - med) / scale, 50), min(jump / scale, 50), min(jump / max(gap, 0.25) / scale, 50),
                     math.log1p(max(gap, 0)), min(run / 12, 5)])
    return np.array(rows, dtype=np.float32)
