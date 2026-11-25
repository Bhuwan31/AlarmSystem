"""The decision agent's state vector, built the same way in the training simulator and for live photos.

Missing information is encoded as "not available" (a 0/1 flag plus a zero value), never as a fake reading: the agent
must learn that no weather data is not the same as no rain.
"""
import math

import numpy as np

from app.vision.classes import CLASSES

EMBED_K = 16          # visual features after projecting the CNN's 160-d embedding with PCA (fitted on train images)

STATE_NAMES = (
    [f"p_{c}" for c in CLASSES] + ["visual_confidence", "visual_entropy"] + [f"visual_pc{i}" for i in range(EMBED_K)]
    + ["gauge_rain_available", "gauge_rain_1h", "gauge_rain_24h", "model_rain_available", "model_rain_24h",
       "river_level_available", "river_level", "official_warning_level", "reports_nearby_6h", "prior_level_nearby",
       "evidence_count", "hour_sin", "hour_cos", "season_sin", "season_cos",
       "location_manual", "gps_accuracy", "image_age", "alert_none", "alert_watch", "alert_warning", "alert_critical",
       "steps_since_change"]
)
STATE_DIM = len(STATE_NAMES)


def project(emb: np.ndarray, pca: dict) -> np.ndarray:
    z = (emb - pca["mean"]) @ pca["components"].T
    return np.clip(z / pca["scale"], -4, 4).astype(np.float32)


def entropy(p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1)
    return float(-(p * np.log(p)).sum() / math.log(len(p)))


def build(probs: np.ndarray, emb_proj: np.ndarray, ctx: dict) -> np.ndarray:
    """ctx keys (None = unavailable): gauge_rain_1h, gauge_rain_24h, model_rain_24h, river_level (0-3),
    official_level (0-3), reports_6h, prior_level, evidence, hour, doy, manual (bool), accuracy_m, age_h,
    alert (0-3), steps_since."""
    g1, g24, m24 = ctx.get("gauge_rain_1h"), ctx.get("gauge_rain_24h"), ctx.get("model_rain_24h")
    gauge = g1 is not None or g24 is not None
    river = ctx.get("river_level")
    hour, doy = float(ctx.get("hour", 12)), float(ctx.get("doy", 180))
    acc = ctx.get("accuracy_m")
    alert = int(ctx.get("alert", 0))
    v = np.concatenate([
        probs.astype(np.float32),
        [float(probs.max()), entropy(probs)],
        emb_proj,
        [1.0 if gauge else 0.0, min((g1 or 0) / 20, 3), min((g24 or 0) / 100, 3),
         1.0 if m24 is not None else 0.0, min((m24 or 0) / 100, 3),
         1.0 if river is not None else 0.0, (river or 0) / 3, (ctx.get("official_level") or 0) / 3,
         min(ctx.get("reports_6h", 0) / 5, 2), ctx.get("prior_level", 0) / 3, min(ctx.get("evidence", 1) / 5, 2),
         math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24),
         math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25),
         1.0 if ctx.get("manual") else 0.0, min((acc if acc is not None else 1000) / 1000, 2), min(ctx.get("age_h", 0) / 24, 2)],
        np.eye(4, dtype=np.float32)[alert],
        [min(ctx.get("steps_since", 0) / 12, 2)],
    ]).astype(np.float32)
    assert v.shape[0] == STATE_DIM
    return v
