"""Live ML outlook from the trained models (advisory only — nothing here issues or changes a warning).

Loads app/ml/artifacts/ once and fetches, for every model station, the last 40 days and the next 30 days of
river flow (51 ensemble futures), rain, rain-forecast uncertainty, soil moisture and headwater temperature/snow.
`outlook()` runs every model on today's inputs; `outlook30()` steps the warning agent through the 30 days of
each future. Live inputs are cached for 3 hours (GloFAS updates daily).
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import xgboost

from app.db import pool
from app.ml import data, features as F
from app.ml.nets import lstm_forward, mlp_forward

log = logging.getLogger(__name__)
ART = Path(__file__).parent / "artifacts"
TTL_S = 3 * 3600
DAYS = 30

_models: dict | None = None
_live: tuple[float, dict] | None = None
_outlook: tuple[float, dict] | None = None
_outlook30: tuple[float, dict] | None = None
_lock = asyncio.Lock()


class NotTrained(RuntimeError):
    pass


def models() -> dict:
    global _models
    if _models is None:
        if not (ART / "meta.json").exists():
            raise NotTrained("the ML models have not been trained yet: docker compose --profile ml run --rm ml-train")
        m = {"meta": json.loads((ART / "meta.json").read_text()), "metrics": json.loads((ART / "metrics.json").read_text())}
        if m["meta"].get("features") != F.FEATURES:
            raise NotTrained("the saved models use older inputs; retrain: docker compose --profile ml run --rm ml-train")
        for name in ("logistic_regression", "random_forest", "svm", "flood_svm", "linear_regression", "isolation_forest", "kmeans"):
            m[name] = joblib.load(ART / f"{name}.joblib")
        for h in (1, 3):
            m[f"xgb_{h}"] = xgboost.XGBRegressor()
            m[f"xgb_{h}"].load_model(ART / f"xgboost_{h}d.json")
        m["lstm"] = dict(np.load(ART / "lstm.npz"))
        m["dqn"] = dict(np.load(ART / "dqn.npz"))
        _models = m
    return _models


def _probs(model, X) -> np.ndarray:
    """Class probabilities as (n, 4) even if a class was absent from training."""
    p = model.predict_proba(X)
    out = np.zeros((len(X), len(F.LEVELS)))
    out[:, model.classes_] = p
    return out


def _dqn_state(x: np.ndarray, alert: int, since: int = 1) -> np.ndarray:
    return np.concatenate([x, np.eye(len(F.LEVELS), dtype=np.float32)[alert], [min(since / 7, 1.0)]]).astype(np.float32)


async def _inputs() -> dict:
    """Live inputs per station: one feature context per ensemble future, plus forecast rain and uncertainty paths."""
    global _live
    if _live and time.time() - _live[0] < TTL_S:
        return _live[1]
    M = models()
    stations = M["meta"]["stations"]
    today, rows = await data.live_all([(s["cell_lat"], s["cell_lon"]) for s in stations],
                                      [(s["head_lat"], s["head_lon"]) for s in stations], days=DAYS)
    current = {r["station_id"]: r["level"] for r in await pool().fetch(
        """select distinct on (station_id) station_id, level from risk_assessments
           where station_id = any($1::bigint[]) order by station_id, computed_at desc""", [s["id"] for s in stations])}
    raw = {}
    for s, row in zip(stations, rows):
        n_days = row["today_index"] + DAYS                           # flow exists up to today + DAYS - 1
        members = [F.clean(m[:n_days]) for m in row["members"]]
        members = [m for m in members if not np.isnan(m).any()]
        if members:
            raw[s["name"]] = (s, row, members)
    n_fut = min(len(v[2]) for v in raw.values()) if raw else 0
    out = []
    for name, (s, row, members) in raw.items():
        ups = [u for u in s.get("upstream", []) if u in raw]
        n = row["today_index"] + DAYS
        rain = F.clean(row["rain"], 0.0)
        ctx = []
        for k in range(n_fut):
            q_up = np.sum([raw[u][2][k] for u in ups], axis=0) if ups else None
            ctx.append(F.context(members[k], rain[:n], s["stats"], q_up, F.clean(row["soil"][:n], 0.3),
                                 F.clean(row["htemp"][:n], 0.0), F.clean(row["hsnow"][:n], 0.0)))
        unc = F.clean(row["uncertainty"], 0.4)
        lv = current.get(s["id"])
        out.append({"station": s, "dates": row["dates"][:n], "t0": row["today_index"], "rain": rain, "uncertainty": unc,
                    "first_seasonal_day": row["first_seasonal_day"], "futures": ctx, "upstream_used": ups,
                    "doys": [datetime.fromisoformat(d).timetuple().tm_yday for d in row["dates"][:n]],
                    "current": F.LEVELS.index(lv) if lv in F.LEVELS else 0})
    if not out:
        raise RuntimeError("no live discharge data returned")
    result = {"today": today, "stations": out}
    _live = (time.time(), result)
    return result


def _fc(r: dict, t: int) -> tuple[float, float, float, float]:
    rain = r["rain"]
    return float(rain[t + 1]), float(rain[t + 1:t + 4].sum()), float(rain[t + 1:t + 8].sum()), float(r["uncertainty"][t])


async def outlook() -> dict:
    global _outlook
    async with _lock:
        if _outlook and time.time() - _outlook[0] < TTL_S:
            return _outlook[1]
        M = models()
        live = await _inputs()
        X, S = [], []
        for r in live["stations"]:
            c, t = r["futures"][0], r["t0"]                         # future 0 = the main forecast
            X.append(F.vector(c, t, r["doys"][t], _fc(r, t)))
            S.append(F.sequence(c, t, r["doys"]))
        X, S = np.stack(X), np.stack(S)
        cls = {name: _probs(M[name], X) for name in ("logistic_regression", "random_forest", "svm")}
        flood_p = M["flood_svm"].predict_proba(X[:, F.RAIN_IDX])[:, list(M["flood_svm"].classes_).index(1)]
        deltas = {"linear_regression": M["linear_regression"].predict(X),
                  "xgboost": np.stack([M["xgb_1"].predict(X), M["xgb_3"].predict(X)], 1),
                  "lstm": lstm_forward(M["lstm"], S, X[:, F.FC_IDX])}
        names = M["kmeans"]["names"]
        out = []
        for i, r in enumerate(live["stations"]):
            s, c, t = r["station"], r["futures"][0], r["t0"]
            st, fc = s["stats"], _fc(r, t)
            qv = mlp_forward(M["dqn"], _dqn_state(X[i], r["current"])[None])[0]
            out.append({
                "station_id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                "cluster": s["cluster"], "cluster_name": names[s["cluster"]], "as_of": r["dates"][t],
                "flow_m3s": round(float(c["q"][t]), 1), "level_now": F.LEVELS[int(F.classify(c["q"][t], st))],
                "thresholds_m3s": {"watch": round(st["q_watch"], 1), "warning": round(st["q_warning"], 1), "critical": round(st["q_critical"], 1)},
                "rain_7d_mm": round(float(r["rain"][t - 6:t + 1].sum()), 1), "forecast_rain_3d_mm": round(max(fc[1], 0.0), 1),
                "forecast_rain_7d_mm": round(max(fc[2], 0.0), 1), "forecast_uncertainty": round(fc[3], 2),
                "upstream": r["upstream_used"],
                "upstream_flow_m3s": round(float(F.q_from_qn(c["zup"][t], st)), 1) if c["zup"] is not None else None,
                "soil_moisture": round(float(c["soil"][t]), 3), "headwater_temp_c": round(float(c["htemp"][t]), 1),
                "headwater_snow_30d_cm": round(float(c["hsnow"][t - 29:t + 1].sum()), 1),
                "flow_30d": [round(float(v), 1) for v in c["q"][t - 29:t + 1]],
                "classification": {k: {"level": F.LEVELS[int(p[i].argmax())], "probabilities": [round(float(v), 3) for v in p[i]]}
                                   for k, p in cls.items()},
                "flood_probability_rain_only": round(float(flood_p[i]), 3),
                "regression": {k: {"flow_1d_m3s": round(float(F.q_from_qn(c["z"][t] + d[i, 0], st)), 1),
                                   "flow_3d_m3s": round(float(F.q_from_qn(c["z"][t] + d[i, 1], st)), 1)} for k, d in deltas.items()},
                "dqn": {"current_alert": F.LEVELS[r["current"]], "recommended": F.LEVELS[int(qv.argmax())],
                        "q_values": [round(float(v), 3) for v in qv]},
            })
        result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "today": live["today"], "stations": out,
                  "note": "Advisory model output. Official warnings still come only from the rule engine and human approval."}
        _outlook = (time.time(), result)
        return result


def _likely(probs: np.ndarray, min_p: float = 0.2) -> int:
    """Highest level that has at least `min_p` chance (a cautious reading of the futures, not just the average)."""
    hits = np.flatnonzero(probs >= min_p)
    return int(hits.max()) if len(hits) else int(probs.argmax())


async def outlook30() -> dict:
    """30-day warning outlook from the warning agent.

    For each river and each of the ensemble futures, the agent is stepped forward one day at a time: every day it
    sees that future's flow (and its upstream rivers' flow in the same future), the rain, how uncertain the rain
    forecast is, soil moisture, headwater temperature and snow, and the level it chose the day before, and picks a
    level. Counting its choices over the futures gives the chance of each level on each day. Advisory only."""
    global _outlook30
    async with _lock:
        if _outlook30 and time.time() - _outlook30[0] < TTL_S:
            return _outlook30[1]
        M = models()
        live = await _inputs()
        n_lv, out = len(F.LEVELS), []
        for r in live["stations"]:
            s, st, futs, t0 = r["station"], r["station"]["stats"], r["futures"], r["t0"]
            alert = np.full(len(futs), r["current"])
            since = np.ones(len(futs), dtype=int)
            day_rows = []
            for d in range(DAYS):
                t = t0 + d
                fc = _fc(r, t)
                X = np.stack([F.vector(c, t, r["doys"][t], fc) for c in futs])
                S = np.stack([_dqn_state(X[m], int(alert[m]), int(since[m])) for m in range(len(futs))])
                act = mlp_forward(M["dqn"], S).argmax(1)
                since = np.where(act == alert, since + 1, 0)
                alert = act
                probs = np.bincount(act, minlength=n_lv) / len(futs)
                flows = np.array([c["q"][t] for c in futs])
                flow_lv = F.classify(flows, st)
                day_rows.append({
                    "date": r["dates"][t], "level": F.LEVELS[_likely(probs)],
                    "probabilities": [round(float(p), 3) for p in probs],
                    "chance_flow_at_or_above": {lv.lower(): round(float((flow_lv >= k).mean()), 3) for k, lv in enumerate(F.LEVELS) if k},
                    "flow_m3s": {"low": round(float(np.percentile(flows, 10)), 1), "middle": round(float(np.median(flows)), 1),
                                 "high": round(float(np.percentile(flows, 90)), 1)},
                    "rain_mm": round(float(r["rain"][t]), 1), "forecast_uncertainty": round(fc[3], 2),
                    "soil_moisture": round(float(futs[0]["soil"][t]), 3), "headwater_temp_c": round(float(futs[0]["htemp"][t]), 1),
                    "rain_source": "seasonal average" if r["dates"][t] >= r["first_seasonal_day"] else "forecast",
                })
            peak = max(day_rows, key=lambda x: (F.LEVELS.index(x["level"]), sum(x["probabilities"][1:])))
            first = {lv.lower(): next((x["date"] for x in day_rows if F.LEVELS.index(x["level"]) >= k), None)
                     for k, lv in enumerate(F.LEVELS) if k}
            out.append({"station_id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                        "current_level": F.LEVELS[r["current"]], "highest_level": peak["level"], "highest_level_date": peak["date"],
                        "first_date": first, "upstream": r["upstream_used"],
                        "thresholds_m3s": {"watch": round(st["q_watch"], 1), "warning": round(st["q_warning"], 1), "critical": round(st["q_critical"], 1)},
                        "futures": len(futs), "days": day_rows})
        out.sort(key=lambda x: (-F.LEVELS.index(x["highest_level"]), x["name"]))
        result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "today": live["today"], "days": DAYS,
                  "stations": out,
                  "method": "The warning agent (which learned when to warn by trial and reward on 2019-2022 river data) is stepped "
                            "forward day by day through each possible future of the 30-day river forecast. Every day it sees that "
                            "future's flow and upstream flow, the rain ahead and how sure the forecast is, soil wetness and mountain "
                            "temperature and snow. Each day's level is the highest one it picks in at least 20% of the futures.",
                  "note": "Advisory only. Days 1-16 use forecast rain; after that rain is a seasonal average, so treat the "
                          "second half of the month as a rough guide. Official warnings come only from the rule engine and human approval."}
        _outlook30 = (time.time(), result)
        return result


def _reason(x: np.ndarray) -> str:
    """Plain-words hint for why a reading looks odd (the forest itself gives only a score)."""
    if x[:3].max() >= 3:
        return ["far from this gauge's typical level", "sudden jump from the previous reading", "change too fast per hour"][int(np.argmax(x[:3]))]
    if x[3] >= np.log1p(6):
        return "long gap before this reading"
    if x[4] >= 1:
        return "value stuck (same reading repeated)"
    return "unusual combination of small changes"


async def anomalies(hours: int = 48) -> dict:
    """Isolation Forest scores for the real gauge readings of the last `hours` (with 3 days of context per gauge)."""
    M = models()
    iso = M["isolation_forest"]
    rows = await pool().fetch(
        """select o.station_id, s.name, o.observed_at, o.value, o.quality from observations o join stations s on s.id = o.station_id
           where o.variable = 'water_level_m' and o.value is not null and o.observed_at > now() - interval '72 hours'
           order by o.station_id, o.observed_at""")
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    by: dict[int, list] = {}
    for r in rows:
        by.setdefault(r["station_id"], []).append(r)
    found, scored = [], 0
    for sid, rs in by.items():
        if len(rs) < 10:
            continue
        Xa = F.anomaly_matrix([r["observed_at"] for r in rs], [r["value"] for r in rs])
        score = iso.decision_function(Xa)
        flag = iso.predict(Xa) == -1
        for r, x, sc, fl in zip(rs, Xa, score, flag):
            if r["observed_at"] < since:
                continue
            scored += 1
            if fl:
                found.append({"station_id": sid, "name": r["name"], "observed_at": r["observed_at"].isoformat(), "value_m": r["value"],
                              "score": round(float(sc), 3), "rule_quality": r["quality"],
                              "main_reason": _reason(x),
                              "features": dict(zip(F.ANOMALY_FEATURES, (round(float(v), 2) for v in x)))})
    found.sort(key=lambda a: a["score"])
    if not rows:
        log.info("no gauge readings in the last 72 h")
    return {"hours": hours, "readings_scored": scored, "gauges": len(by), "anomalies": found[:200], "total_anomalies": len(found)}
