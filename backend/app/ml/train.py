"""Train every ML model and write them to app/ml/artifacts/ with an honest evaluation on held-out years.

    docker compose --profile ml run --rm ml-train

Data: 2019-2024 daily GloFAS discharge + ERA5 rain at 24 river stations (train 2019-2022, test 2023-2024, split by
time so no future information leaks into training), plus the real gauge readings in our own database.

Models
  classification  logistic regression, random forest, SVM  → flood class for the next 3 days
  flood vs none   SVM on rain features only                → will the river reach WARNING in the next 3 days?
  regression      linear regression, XGBoost, LSTM          → river flow 1 day and 3 days ahead
  inputs          own flow and rain, upstream stations' flow, rain forecast 1/3/7 days and its uncertainty,
                  soil moisture, headwater temperature and snowfall (snow and glacier melt), season
  clustering      k-means                                   → stations with similar rain and flow regimes
  anomalies       Isolation Forest                          → suspicious readings from real gauges
  reinforcement   Deep Q-Network (DQN)                      → which warning level to show today
"""
import asyncio
import json
import logging
import random
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
import joblib
import numpy as np
import sklearn
import torch
import xgboost
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error, precision_score,
                             recall_score, roc_auc_score, silhouette_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from torch import nn

from app.config import get_settings
from app.ml import data, features as F

log = logging.getLogger("ml.train")
ART = Path(__file__).parent / "artifacts"
START, END, TEST_FROM = "2019-01-01", "2024-12-31", "2023-01-01"
SEED = 42
FC_IDX = F.FC_IDX


# ---------------------------------------------------------------- data
async def load() -> tuple[list[dict], list[dict]]:
    conn = await asyncpg.connect(get_settings().database_url)
    rows = await conn.fetch("""select id, name, ST_Y(geom) lat, ST_X(geom) lon from stations
                               where kind = 'river' and name = any($1::text[])""", data.TRAINING_STATIONS)
    readings = await conn.fetch("""select station_id, observed_at, value, quality from observations
                                   where variable = 'water_level_m' and value is not null order by station_id, observed_at""")
    await conn.close()
    stations = sorted((dict(r) for r in rows), key=lambda s: data.TRAINING_STATIONS.index(s["name"]))
    log.info("%d training stations found in the database", len(stations))

    snap_file = data.CACHE_DIR / "snaps.json"
    data.CACHE_DIR.mkdir(exist_ok=True)
    snaps = json.loads(snap_file.read_text()) if snap_file.exists() else {}
    by_name = {s["name"]: s for s in stations}
    async with httpx.AsyncClient(timeout=120) as client:
        for s in stations:
            if s["name"] not in snaps:
                snaps[s["name"]] = await data.snap(client, s["lat"], s["lon"])
                snap_file.write_text(json.dumps(snaps))
        # A tributary gauge must not sit on the bigger river it flows into (e.g. Arun on the Sapta Koshi cell):
        # re-snap it close to its own location, below the downstream river's flow.
        for down, ups in data.UPSTREAM.items():
            for u in ups:
                if u in snaps and down in snaps and snaps[u][2] >= 0.9 * snaps[down][2] and u in by_name:
                    old = snaps[u]
                    snaps[u] = await data.snap(client, by_name[u]["lat"], by_name[u]["lon"], max_flow=0.9 * snaps[down][2], reach=1)
                    log.info("re-snapped %s: %s -> %s (below %s)", u, old, snaps[u], down)
                    snap_file.write_text(json.dumps(snaps))
        for s in stations:
            s["cell_lat"], s["cell_lon"], s["median_flow_snap"] = snaps[s["name"]]
            s["head_lat"], s["head_lon"] = data.headwater(s["lat"], s["lon"])
        cells = [(s["cell_lat"], s["cell_lon"]) for s in stations]
        series = await data.history(client, cells, START, END)
        extra = await data.history_extra(client, cells, [(s["head_lat"], s["head_lon"]) for s in stations], START, END)
    for s, ser, ex in zip(stations, series, extra):
        assert ex["dates"] == ser["dates"], s["name"]
        s["dates"], s["q"], s["rain"] = ser["dates"], F.clean(ser["discharge"]), F.clean(ser["rain"])
        s["soil"], s["htemp"], s["hsnow"] = F.clean(ex["soil"], 0.3), F.clean(ex["htemp"], 0.0), F.clean(ex["hsnow"], 0.0)
        s["upstream"] = [u for u in data.UPSTREAM.get(s["name"], []) if u in by_name]
    return stations, [dict(r) for r in readings]


def datasets(stations: list[dict]) -> tuple[dict, dict]:
    rng = np.random.default_rng(SEED)
    parts = {"train": [], "test": []}
    by_name = {s["name"]: s for s in stations}
    for s in stations:
        s["stats"] = F.station_stats(s["q"][:s["dates"].index(TEST_FROM)])
    for k, s in enumerate(stations):
        q_up = np.sum([by_name[u]["q"] for u in s["upstream"]], axis=0) if s["upstream"] else None
        c = F.context(s["q"], s["rain"], s["stats"], q_up, s["soil"], s["htemp"], s["hsnow"])
        d = F.build(s["dates"], c, rng)
        d["station"] = np.full(len(d["y_cls"]), k)
        s["samples"] = d
        is_test = np.array([x >= TEST_FROM for x in d["dates"]])
        for name, mask in (("train", ~is_test), ("test", is_test)):
            parts[name].append({key: (v[mask] if isinstance(v, np.ndarray) else [x for x, m in zip(v, mask) if m]) for key, v in d.items()})
    joined = {}
    for name, ps in parts.items():
        joined[name] = {key: (np.concatenate([p[key] for p in ps]) if isinstance(ps[0][key], np.ndarray) else sum((p[key] for p in ps), []))
                        for key in ps[0]}
    log.info("samples: %d train, %d test; test class counts %s", len(joined["train"]["y_cls"]), len(joined["test"]["y_cls"]),
             np.bincount(joined["test"]["y_cls"], minlength=4).tolist())
    return joined["train"], joined["test"]


# ---------------------------------------------------------------- classification
def cls_report(y, p) -> dict:
    warn_t, warn_p = y >= 2, p >= 2
    return {"accuracy": round(float(accuracy_score(y, p)), 3), "macro_f1": round(float(f1_score(y, p, average="macro")), 3),
            "recall_per_class": [round(float(x), 3) for x in recall_score(y, p, average=None, labels=[0, 1, 2, 3], zero_division=0)],
            "warning_recall": round(float(recall_score(warn_t, warn_p, zero_division=0)), 3),
            "warning_precision": round(float(precision_score(warn_t, warn_p, zero_division=0)), 3),
            "confusion": confusion_matrix(y, p, labels=[0, 1, 2, 3]).tolist()}


def subsample(y: np.ndarray, n: int, rng) -> np.ndarray:
    """Stratified-ish subsample: keep every rare-class row, fill the rest from the common class."""
    rare = np.flatnonzero(y > 0)
    common = np.flatnonzero(y == 0)
    take = rng.choice(common, size=max(0, min(len(common), n - len(rare))), replace=False)
    return np.concatenate([rare[: n], take])


def train_classifiers(tr, te, metrics):
    rng = np.random.default_rng(SEED)
    X, y, Xt, yt = tr["X"], tr["y_cls"], te["X"], te["y_cls"]
    out = {"baseline_today_class": cls_report(yt, np.rint(Xt[:, F.FEATURES.index("class_now")] * 3).astype(int))}

    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    lr.fit(X, y)
    out["logistic_regression"] = cls_report(yt, lr.predict(Xt))

    rf = RandomForestClassifier(n_estimators=150, max_depth=12, min_samples_leaf=10, class_weight="balanced_subsample",
                                n_jobs=-1, random_state=SEED)
    rf.fit(X, y)
    out["random_forest"] = cls_report(yt, rf.predict(Xt))
    out["random_forest"]["feature_importance"] = dict(sorted(zip(F.FEATURES, (round(float(v), 4) for v in rf.feature_importances_)),
                                                             key=lambda kv: -kv[1]))

    idx = subsample(y, 12000, rng)
    svm = make_pipeline(StandardScaler(), SVC(C=3.0, kernel="rbf", gamma="scale", class_weight="balanced", probability=True, random_state=SEED))
    svm.fit(X[idx], y[idx])
    out["svm"] = cls_report(yt, svm.predict(Xt))
    out["svm"]["trained_on"] = int(len(idx))

    # Flood / no flood from rain alone (no river reading) — useful where there is no gauge.
    yb, ybt = (y >= 2).astype(int), (yt >= 2).astype(int)
    idx = subsample(yb, 12000, rng)
    fsvm = make_pipeline(StandardScaler(), SVC(C=2.0, kernel="rbf", gamma="scale", class_weight="balanced", probability=True, random_state=SEED))
    fsvm.fit(X[idx][:, F.RAIN_IDX], yb[idx])
    prob = fsvm.predict_proba(Xt[:, F.RAIN_IDX])[:, 1]
    pred = (prob >= 0.5).astype(int)
    out["flood_svm_rain_only"] = {"roc_auc": round(float(roc_auc_score(ybt, prob)), 3), "recall": round(float(recall_score(ybt, pred)), 3),
                                  "precision": round(float(precision_score(ybt, pred, zero_division=0)), 3),
                                  "f1": round(float(f1_score(ybt, pred)), 3), "trained_on": int(len(idx)),
                                  "confusion": confusion_matrix(ybt, pred, labels=[0, 1]).tolist()}

    for name, m in (("logistic_regression", lr), ("random_forest", rf), ("svm", svm), ("flood_svm", fsvm)):
        joblib.dump(m, ART / f"{name}.joblib", compress=3)
    metrics["classification"] = out
    log.info("classification: %s", {k: v.get("macro_f1", v.get("roc_auc")) for k, v in out.items()})
    return rf


# ---------------------------------------------------------------- regression
class FlowLSTM(nn.Module):
    def __init__(self, inputs=len(F.SEQ_FEATURES), hidden=32, extra=len(FC_IDX)):
        super().__init__()
        self.lstm = nn.LSTM(inputs, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden + extra, 32), nn.ReLU(), nn.Linear(32, 2))

    def forward(self, seq, extra):
        _, (h, _) = self.lstm(seq)
        return self.head(torch.cat([h[-1], extra], dim=1))


def reg_report(pred, te, stations) -> dict:
    out = {}
    for j, (h, key) in enumerate(((1, "y1"), (3, "y3"))):
        y, p = te[key], pred[:, j]
        # back to m³/s per station for an error people can read
        q_now = np.array([F.q_from_qn(te["X"][i, 0], stations[s]["stats"]) for i, s in enumerate(te["station"])])
        q_true = np.array([F.q_from_qn(te["X"][i, 0] + y[i], stations[s]["stats"]) for i, s in enumerate(te["station"])])
        q_pred = np.array([F.q_from_qn(te["X"][i, 0] + p[i], stations[s]["stats"]) for i, s in enumerate(te["station"])])
        mse, mse_persist = float(np.mean((y - p) ** 2)), float(np.mean(y ** 2))
        high = q_true >= np.array([stations[s]["stats"]["q_watch"] for s in te["station"]])
        out[f"{h}d"] = {
            "rmse_scaled": round(mse ** 0.5, 4), "mae_scaled": round(float(mean_absolute_error(y, p)), 4),
            "skill_vs_persistence": round(1 - mse / mse_persist, 3),
            "median_abs_pct_error": round(float(np.median(np.abs(q_pred - q_true) / np.maximum(q_true, 1e-3))) * 100, 1),
            "median_abs_pct_error_persistence": round(float(np.median(np.abs(q_now - q_true) / np.maximum(q_true, 1e-3))) * 100, 1),
            "median_abs_pct_error_high_flow": round(float(np.median(np.abs(q_pred[high] - q_true[high]) / q_true[high])) * 100, 1) if high.any() else None,
        }
    return out


def train_regression(tr, te, stations, metrics):
    Y, out = np.stack([tr["y1"], tr["y3"]], 1), {}
    lin = LinearRegression().fit(tr["X"], Y)
    out["linear_regression"] = reg_report(lin.predict(te["X"]), te, stations)
    joblib.dump(lin, ART / "linear_regression.joblib", compress=3)

    preds = []
    for j, h in enumerate((1, 3)):
        m = xgboost.XGBRegressor(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                                 random_state=SEED, n_jobs=4)
        m.fit(tr["X"], Y[:, j])
        m.save_model(ART / f"xgboost_{h}d.json")
        preds.append(m.predict(te["X"]))
        if h == 1:
            out_imp = dict(sorted(zip(F.FEATURES, (round(float(v), 4) for v in m.feature_importances_)), key=lambda kv: -kv[1]))
    out["xgboost"] = reg_report(np.stack(preds, 1), te, stations)
    out["xgboost"]["feature_importance_1d"] = out_imp

    torch.manual_seed(SEED)
    net = FlowLSTM()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    S, E, Yt = torch.tensor(tr["S"]), torch.tensor(tr["X"][:, FC_IDX]), torch.tensor(Y)
    curve = []
    for epoch in range(20):
        perm, total = torch.randperm(len(S)), 0.0
        for i in range(0, len(S), 256):
            b = perm[i:i + 256]
            loss = nn.functional.mse_loss(net(S[b], E[b]), Yt[b])
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss) * len(b)
        curve.append(round(total / len(S), 5))
    net.eval()
    with torch.no_grad():
        p = net(torch.tensor(te["S"]), torch.tensor(te["X"][:, FC_IDX])).numpy()
    out["lstm"] = reg_report(p, te, stations)
    out["lstm"]["train_loss_by_epoch"] = curve
    np.savez(ART / "lstm.npz", **{k: v.numpy() for k, v in net.state_dict().items()})
    out["persistence_baseline"] = reg_report(np.zeros((len(te["y1"]), 2), dtype=np.float32), te, stations)
    metrics["regression"] = out
    log.info("regression skill 1d: %s", {k: v["1d"]["skill_vs_persistence"] for k, v in out.items()})


# ---------------------------------------------------------------- clustering
CLUSTER_FEATURES = ["annual_rain_mm", "monsoon_share", "wet_day_share", "p99_daily_rain_mm", "log10_median_flow", "flashiness", "log10_flood_ratio"]


def train_clusters(stations, metrics):
    rows = []
    for s in stations:
        q, r, months = s["q"], s["rain"], np.array([int(d[5:7]) for d in s["dates"]])
        years = len(s["dates"]) / 365.25
        rows.append([np.nansum(r) / years, np.nansum(r[(months >= 6) & (months <= 9)]) / max(np.nansum(r), 1), float(np.mean(r > 1)),
                     float(np.nanpercentile(r, 99)), float(np.log10(max(np.nanmedian(q), 0.01))),
                     float(np.nansum(np.abs(np.diff(q))) / max(np.nansum(q), 1e-6)),
                     float(np.log10(max(np.nanpercentile(q, 99), 0.01) / max(np.nanmedian(q), 0.01)))])
    Xc = np.array(rows)
    scaler = StandardScaler().fit(Xc)
    Z = scaler.transform(Xc)
    best = None
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(Z)
        score = float(silhouette_score(Z, km.labels_))
        if best is None or score > best[0]:
            best = (score, k, km)
    score, k, km = best
    xy = PCA(n_components=2, random_state=SEED).fit_transform(Z)
    names = []
    for c in range(k):
        m = Xc[km.labels_ == c].mean(0)
        wet = "very wet" if m[0] > 2500 else "wet" if m[0] > 1600 else "drier"
        size = "large" if m[4] > 2.5 else "medium" if m[4] > 1.5 else "small"
        flashy = ", flashy" if m[5] > np.median(Xc[:, 5]) else ""
        names.append(f"{size} rivers, {wet}{flashy}")
    for i, s in enumerate(stations):
        s["cluster"], s["pca"] = int(km.labels_[i]), [round(float(xy[i, 0]), 3), round(float(xy[i, 1]), 3)]
        s["climate"] = dict(zip(CLUSTER_FEATURES, (round(float(v), 3) for v in Xc[i])))
    joblib.dump({"scaler": scaler, "kmeans": km, "names": names}, ART / "kmeans.joblib", compress=3)
    metrics["clustering"] = {"k": k, "silhouette": round(score, 3), "features": CLUSTER_FEATURES, "names": names,
                             "sizes": np.bincount(km.labels_, minlength=k).tolist(),
                             "centres": [dict(zip(CLUSTER_FEATURES, (round(float(v), 2) for v in Xc[km.labels_ == c].mean(0)))) for c in range(k)]}
    log.info("k-means: k=%d silhouette=%.3f %s", k, score, names)


# ---------------------------------------------------------------- anomaly detection
def train_iforest(readings, metrics):
    by_station: dict[int, list] = {}
    for r in readings:
        by_station.setdefault(r["station_id"], []).append(r)
    X, flags = [], []
    for rows in by_station.values():
        if len(rows) < 20:
            continue
        X.append(F.anomaly_matrix([r["observed_at"] for r in rows], [r["value"] for r in rows]))
        flags += [r["quality"] != "GOOD" for r in rows]
    X, flags = np.concatenate(X), np.array(flags)
    iso = IsolationForest(n_estimators=200, contamination=0.01, random_state=SEED).fit(X)
    pred = iso.predict(X) == -1
    joblib.dump(iso, ART / "isolation_forest.joblib", compress=3)
    metrics["anomaly"] = {"readings": int(len(X)), "gauges": len(by_station), "flagged": int(pred.sum()),
                          "flagged_share": round(float(pred.mean()), 4), "rule_flagged": int(flags.sum()),
                          "also_flagged_by_rules": int((pred & flags).sum()), "features": F.ANOMALY_FEATURES,
                          "note": "Unsupervised: there are no labelled sensor faults, so agreement with the rule-based quality checks is shown instead of accuracy."}
    log.info("isolation forest: %d of %d readings flagged", pred.sum(), len(X))


# ---------------------------------------------------------------- reinforcement learning (DQN)
N_ACT = 4
STATE_DIM = len(F.FEATURES) + N_ACT + 1


def state(x: np.ndarray, alert: int, since: int) -> np.ndarray:
    return np.concatenate([x, np.eye(N_ACT, dtype=np.float32)[alert], [min(since / 7, 1.0)]]).astype(np.float32)


def reward(action: int, target: int, prev: int) -> float:
    """Missing or under-calling a flood costs most; false alarms cost less; changing the level costs a little
    (people stop trusting warnings that flicker); being right about a flood earns most."""
    if action < target:
        r = -2.5 * (target - action)
    elif action > target:
        r = -1.0 * (action - target)
    else:
        r = 1.0 if target > 0 else 0.2
    return r - (0.25 if action != prev else 0.0)


class QNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(STATE_DIM, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, N_ACT))

    def forward(self, x):
        return self.net(x)


def run_policy(policy, X, y) -> tuple[list[int], float]:
    alert, since, acts, total = 0, 0, [], 0.0
    for i in range(len(y)):
        a = policy(X[i], alert, since)
        total += reward(a, int(y[i]), alert)
        since = since + 1 if a == alert else 0
        alert = a
        acts.append(a)
    return acts, total


def policy_report(acts_by_station, stations, samples_by_station, rewards) -> dict:
    events = hits_early = hits = 0
    leads, false_days, warn_days, switches, days = [], 0, 0, 0, 0
    for k, acts in acts_by_station.items():
        d, s = samples_by_station[k], stations[k]
        daily = F.classify(s["q"], s["stats"])
        alert_on = {int(t): a for t, a in zip(d["t"], acts)}
        for t, a, yc in zip(d["t"], acts, d["y_cls"]):
            days += 1
            if a >= 2:
                warn_days += 1
                false_days += yc < 2
        switches += sum(1 for a, b in zip(acts, acts[1:]) if a != b)
        for t in d["t"]:
            if daily[t] >= 2 and daily[t - 1] < 2:      # a new flood (WARNING+) begins on day t
                events += 1
                early = [k2 for k2 in (3, 2, 1) if alert_on.get(t - k2, 0) >= 2]   # days of warning before onset
                if early:
                    hits_early += 1
                    leads.append(max(early))
                if early or alert_on.get(t, 0) >= 2:
                    hits += 1
    years = days / 365.25 / max(len(acts_by_station), 1)
    return {"flood_events": events, "warned_in_advance": round(hits_early / max(events, 1), 3),
            "warned_by_onset_day": round(hits / max(events, 1), 3), "mean_lead_days": round(float(np.mean(leads)), 2) if leads else 0.0,
            "false_alarm_ratio": round(false_days / max(warn_days, 1), 3),
            "level_changes_per_station_year": round(switches / max(len(acts_by_station), 1) / max(years, 1e-6), 1),
            "mean_reward_per_day": round(float(sum(rewards) / max(days, 1)), 3)}


def train_dqn(stations, rf, metrics, steps=150_000):
    rng = random.Random(SEED)
    torch.manual_seed(SEED)
    train_eps = []
    for s in stations:
        d = s["samples"]
        m = np.array([x < TEST_FROM for x in d["dates"]])
        if m.sum() > 120:
            train_eps.append((d["X"][m], d["y_cls"][m]))
    q, target = QNet(), QNet()
    target.load_state_dict(q.state_dict())
    opt = torch.optim.Adam(q.parameters(), lr=5e-4)
    buf: deque = deque(maxlen=100_000)
    gamma, batch, ep_len = 0.9, 128, 90
    curve, ep_rewards = [], []
    step = 0
    while step < steps:
        X, y = rng.choice(train_eps)
        i0 = rng.randrange(0, len(y) - ep_len)
        alert, since, ep_r = 0, 0, 0.0
        s = state(X[i0], alert, since)
        for i in range(i0, i0 + ep_len):
            eps = max(0.05, 1 - step / (steps * 0.6))
            if rng.random() < eps:
                a = rng.randrange(N_ACT)
            else:
                with torch.no_grad():
                    a = int(q(torch.tensor(s)).argmax())
            r = reward(a, int(y[i]), alert)
            since = since + 1 if a == alert else 0
            alert = a
            s2 = state(X[i + 1], alert, since) if i + 1 < len(y) else s
            buf.append((s, a, r, s2, i + 1 == i0 + ep_len))
            s, ep_r, step = s2, ep_r + r, step + 1
            if len(buf) >= 2000:
                b = rng.sample(buf, batch)
                S = torch.tensor(np.stack([t[0] for t in b])); A = torch.tensor([t[1] for t in b])
                R = torch.tensor([t[2] for t in b], dtype=torch.float32); S2 = torch.tensor(np.stack([t[3] for t in b]))
                D = torch.tensor([t[4] for t in b], dtype=torch.float32)
                with torch.no_grad():                      # Double DQN: online net picks, target net values
                    a2 = q(S2).argmax(1, keepdim=True)
                    y_t = R + gamma * (1 - D) * target(S2).gather(1, a2).squeeze(1)
                loss = nn.functional.smooth_l1_loss(q(S).gather(1, A.unsqueeze(1)).squeeze(1), y_t)
                opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(q.parameters(), 10); opt.step()
            if step % 1000 == 0:
                target.load_state_dict(q.state_dict())
        ep_rewards.append(ep_r / ep_len)
        if len(ep_rewards) % 50 == 0:
            curve.append({"episode": len(ep_rewards), "step": step, "mean_reward_per_day": round(float(np.mean(ep_rewards[-50:])), 3),
                          "epsilon": round(max(0.05, 1 - step / (steps * 0.6)), 3)})
    np.savez(ART / "dqn.npz", **{k: v.numpy() for k, v in q.state_dict().items()})
    q.eval()

    test = {}
    for k, s in enumerate(stations):
        d = s["samples"]
        m = np.array([x >= TEST_FROM for x in d["dates"]])
        test[k] = {"X": d["X"][m], "y_cls": d["y_cls"][m], "t": d["t"][m]}
    i_now = F.FEATURES.index("class_now")
    policies = {
        "dqn": lambda x, al, si: int(q(torch.tensor(state(x, al, si))).argmax()),
        "random_forest": lambda x, al, si: int(rf.predict(x[None])[0]),
        "threshold_rule_today": lambda x, al, si: int(round(x[i_now] * 3)),
    }
    out = {}
    with torch.no_grad():
        for name, pol in policies.items():
            acts, rewards = {}, []
            for k, d in test.items():
                acts[k], r = run_policy(pol, d["X"], d["y_cls"])
                rewards.append(r)
            out[name] = policy_report(acts, stations, test, rewards)
    metrics["dqn"] = {"steps": steps, "episodes": len(ep_rewards), "episode_days": ep_len, "gamma": gamma, "double_dqn": True,
                      "state": F.FEATURES + ["alert_" + lv.lower() for lv in F.LEVELS] + ["days_since_change"],
                      "actions": F.LEVELS, "reward": "miss: -2.5 per level too low; false alarm: -1 per level too high; "
                                                    "correct: +1 (flood) / +0.2 (normal); changing level: -0.25",
                      "training_curve": curve, "evaluation_2023_2024": out}
    log.info("dqn evaluation: %s", out)


# ---------------------------------------------------------------- main
async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    np.random.seed(SEED)
    stations, readings = await load()
    tr, te = datasets(stations)
    metrics: dict = {}
    rf = train_classifiers(tr, te, metrics)
    train_regression(tr, te, stations, metrics)
    train_clusters(stations, metrics)
    train_iforest(readings, metrics)
    train_dqn(stations, rf, metrics)

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "train_seconds": round(time.time() - t0),
        "period": {"start": START, "end": END, "test_from": TEST_FROM},
        "samples": {"train": int(len(tr["y_cls"])), "test": int(len(te["y_cls"]))},
        "class_counts_test": np.bincount(te["y_cls"], minlength=4).tolist(),
        "features": F.FEATURES, "rain_only_features": F.RAIN_ONLY, "levels": F.LEVELS, "percentiles": F.PCTL,
        "versions": {"scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__, "numpy": np.__version__, "torch": torch.__version__},
        "data_sources": ["GloFAS v4 river discharge (Copernicus EMS) via Open-Meteo flood API",
                         "ERA5 daily rain, soil moisture, headwater temperature and snowfall via Open-Meteo archive API",
                         "AMHEWS gauge readings (Isolation Forest)"],
        "upstream": {s["name"]: s["upstream"] for s in stations if s["upstream"]},
        "stations": [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"], "cell_lat": s["cell_lat"], "cell_lon": s["cell_lon"],
                      "head_lat": s["head_lat"], "head_lon": s["head_lon"], "upstream": s["upstream"], "stats": s["stats"], "cluster": s["cluster"], "pca": s["pca"], "climate": s["climate"]} for s in stations],
    }
    (ART / "meta.json").write_text(json.dumps(meta, indent=1))
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=1))
    log.info("done in %ds", time.time() - t0)


if __name__ == "__main__":
    asyncio.run(main())
