"""Train and evaluate the visual models end to end (PyTorch, CPU). Reproducible: fixed seeds, versioned dataset.

    docker compose --profile ml run --rm ml-train python -m app.vision.train_all                     # synthetic data
    docker compose --profile ml run --rm ml-train python -m app.vision.train_all --dataset ml_data/vision/datasets/<version>

Steps
  1. dataset    (if none given) generate the synthetic set and prepare a versioned, leakage-free split
  2. CNN        from random weights; augmentation; class-balanced sampling; AdamW + cosine LR; best checkpoint by
                validation macro-F1; temperature scaling for calibrated confidence
  3. evaluate   precision / recall / F1 / confusion matrix / calibration on validation and test (unseen locations),
                accuracy per lighting condition
  4. agent      Double DQN with experience replay, target network, epsilon-greedy exploration and a Huber Bellman
                loss, trained in app.vision.env on CNN outputs; best checkpoint by validation reward; tested on
                episodes built from test images only; compared with a photo-only rule baseline
  5. export     numpy weights + meta to app/vision/artifacts, report to docs/vision-model-report.md, a row per
                model in model_training_runs
"""
import argparse
import asyncio
import json
import logging
import os
import random
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as Fnn
from PIL import Image, ImageOps

from app.vision import cnn as cnn_mod
from app.vision import dataset as ds
from app.vision import env as E
from app.vision import state as S
from app.vision.classes import ACTION_LEVEL, ACTIONS, CLASSES, ISSUE_CRITICAL, ISSUE_WARNING, ISSUE_WATCH, NO_ALERT, REQUEST_EVIDENCE
from app.vision.imageio import MEAN, STD
from app.vision.policy import MIN_CONFIDENCE, VISUAL_LEVEL

log = logging.getLogger("vision.train")
ROOT = Path(__file__).resolve().parents[2]                 # backend/
ART = Path(__file__).resolve().parent / "artifacts"
DATA = ROOT / "ml_data" / "vision"
REPORT = ART / "vision-model-report.md"            # copied to docs/ (the training container only mounts backend/)


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


# ------------------------------------------------------------------------------------------------------------------
# data
# ------------------------------------------------------------------------------------------------------------------
def load_images(rows, load_size: int) -> torch.Tensor:
    out = torch.empty((len(rows), 3, load_size, load_size), dtype=torch.uint8)
    for i, r in enumerate(rows):
        im = ImageOps.fit(ImageOps.exif_transpose(Image.open(r.path)).convert("RGB"), (load_size, load_size), Image.Resampling.BILINEAR)
        out[i] = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)
    return out


_MEAN = torch.tensor(MEAN).view(1, 3, 1, 1)
_STD = torch.tensor(STD).view(1, 3, 1, 1)


def normalise(x: torch.Tensor) -> torch.Tensor:
    return (x - _MEAN) / _STD


def eval_batch(x: torch.Tensor, size: int) -> torch.Tensor:
    x = x.float() / 255
    if x.shape[-1] != size:
        x = Fnn.interpolate(x, size=(size, size), mode="bilinear", align_corners=False, antialias=True)
    return normalise(x)


def augment(x: torch.Tensor, size: int, g: torch.Generator, strength: float = 1.0) -> torch.Tensor:
    """Random resized crop, flip, small rotation, colour jitter, darkening/fog, blur and noise."""
    n, _, L, _ = x.shape
    x = x.float() / 255
    out = torch.empty((n, 3, size, size))
    for i in range(n):
        s = int(L * (1 - torch.rand(1, generator=g).item() * 0.35 * strength))
        ox, oy = (torch.randint(0, L - s + 1, (2,), generator=g)).tolist()
        crop = x[i:i + 1, :, oy:oy + s, ox:ox + s]
        out[i] = Fnn.interpolate(crop, size=(size, size), mode="bilinear", align_corners=False, antialias=True)[0]
    flip = torch.rand(n, generator=g) < 0.5
    out[flip] = out[flip].flip(-1)
    ang = (torch.rand(n, generator=g) - 0.5) * 0.17 * strength                     # ±5°
    cos, sin = torch.cos(ang), torch.sin(ang)
    theta = torch.stack([torch.stack([cos, -sin, torch.zeros(n)], 1), torch.stack([sin, cos, torch.zeros(n)], 1)], 1)
    out = Fnn.grid_sample(out, Fnn.affine_grid(theta, out.shape, align_corners=False), padding_mode="reflection", align_corners=False)
    b = 1 + (torch.rand(n, 1, 1, 1, generator=g) - 0.5) * 0.5 * strength
    c = 1 + (torch.rand(n, 1, 1, 1, generator=g) - 0.5) * 0.5 * strength
    sat = 1 + (torch.rand(n, 1, 1, 1, generator=g) - 0.5) * 0.6 * strength
    m = out.mean(dim=(1, 2, 3), keepdim=True)
    out = (out - m) * c + m
    gray = out.mean(1, keepdim=True)
    out = ((out - gray) * sat + gray) * b
    dark = torch.rand(n, generator=g) < 0.12 * strength                           # difficult lighting
    out[dark] = out[dark] * (0.25 + 0.35 * torch.rand(int(dark.sum()), 1, 1, 1, generator=g))
    fog = torch.rand(n, generator=g) < 0.08 * strength
    out[fog] = out[fog] * 0.6 + 0.4 * 0.8
    blur = torch.rand(n, generator=g) < 0.15 * strength
    if blur.any():
        out[blur] = Fnn.avg_pool2d(out[blur], 3, 1, 1, count_include_pad=False)
    out = out + torch.randn(out.shape, generator=g) * 0.02 * strength
    return normalise(out.clamp(0, 1))


# ------------------------------------------------------------------------------------------------------------------
# metrics
# ------------------------------------------------------------------------------------------------------------------
def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    k = len(CLASSES)
    pred = p.argmax(1)
    cm = np.zeros((k, k), dtype=int)
    for t, q in zip(y, pred):
        cm[t, q] += 1
    per = {}
    for i, c in enumerate(CLASSES):
        tp, fp, fn = cm[i, i], cm[:, i].sum() - cm[i, i], cm[i].sum() - cm[i, i]
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": round(prec, 3), "recall": round(rec, 3),
                  "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0, "support": int(cm[i].sum())}
    conf = p.max(1)
    bins = np.linspace(0, 1, 11)
    ece = sum(abs((pred[(conf > lo) & (conf <= hi)] == y[(conf > lo) & (conf <= hi)]).mean() - conf[(conf > lo) & (conf <= hi)].mean())
              * ((conf > lo) & (conf <= hi)).mean() for lo, hi in zip(bins[:-1], bins[1:]) if ((conf > lo) & (conf <= hi)).any())
    hazard = np.array([VISUAL_LEVEL[c] >= 2 for c in CLASSES])
    yh, ph = hazard[y], hazard[pred]
    return {"accuracy": round(float((pred == y).mean()), 3),
            "macro_f1": round(float(np.mean([v["f1"] for v in per.values() if v["support"]])), 3),
            "per_class": per, "confusion_matrix": cm.tolist(), "ece": round(float(ece), 3),
            "flood_or_landslide_recall": round(float((yh & ph).sum() / max(yh.sum(), 1)), 3),
            "flood_or_landslide_precision": round(float((yh & ph).sum() / max(ph.sum(), 1)), 3), "n": int(len(y))}


# ------------------------------------------------------------------------------------------------------------------
# CNN
# ------------------------------------------------------------------------------------------------------------------
@torch.no_grad()
def predict(model, X: torch.Tensor, size: int, temperature: float = 1.0, bs: int = 128, aug_g: torch.Generator | None = None):
    model.eval()
    logits, embs = [], []
    for i in range(0, len(X), bs):
        xb = augment(X[i:i + bs], size, aug_g, strength=1.3) if aug_g is not None else eval_batch(X[i:i + bs], size)
        lo, e = model(xb)
        logits.append(lo)
        embs.append(e)
    lo = torch.cat(logits)
    return torch.softmax(lo / temperature, 1).numpy(), lo.numpy(), torch.cat(embs).numpy()


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    lt = torch.zeros(1, requires_grad=True)
    L, Y = torch.tensor(logits), torch.tensor(y)
    opt = torch.optim.LBFGS([lt], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = Fnn.cross_entropy(L / lt.exp(), Y)
        loss.backward()
        return loss
    opt.step(closure)
    return float(lt.detach().exp().clamp(0.5, 5.0))


def train_cnn(Xtr, ytr, Xva, yva, args, ckpt_dir: Path):
    model = cnn_mod.DisasterCNN()
    counts = np.bincount(ytr, minlength=len(CLASSES)).astype(float)
    w_sample = (1.0 / np.maximum(counts, 1))[ytr]                                # class-balanced sampling
    sampler = torch.utils.data.WeightedRandomSampler(torch.tensor(w_sample), num_samples=len(ytr), replacement=True,
                                                     generator=torch.Generator().manual_seed(args.seed))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=5e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * (len(ytr) // args.batch + 1))
    g = torch.Generator().manual_seed(args.seed + 1)
    best, best_ep, history, wait = -1.0, -1, [], 0
    Ytr = torch.tensor(ytr)
    for ep in range(args.epochs):
        model.train()
        idx = torch.tensor(list(sampler))
        tot, n0 = 0.0, time.time()
        for i in range(0, len(idx), args.batch):
            b = idx[i:i + args.batch]
            logits, _ = model(augment(Xtr[b], args.img_size, g))
            loss = Fnn.cross_entropy(logits, Ytr[b], label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += float(loss.detach()) * len(b)
        pv, _, _ = predict(model, Xva, args.img_size)
        m = classification_metrics(yva, pv)
        history.append({"epoch": ep + 1, "train_loss": round(tot / len(idx), 4), "val_macro_f1": m["macro_f1"], "val_accuracy": m["accuracy"]})
        log.info("cnn epoch %d/%d loss %.4f val macro-F1 %.3f acc %.3f (%.0fs)", ep + 1, args.epochs, tot / len(idx),
                 m["macro_f1"], m["accuracy"], time.time() - n0)
        torch.save(model.state_dict(), ckpt_dir / f"cnn_epoch{ep + 1:02d}.pt")
        if m["macro_f1"] > best:
            best, best_ep, wait = m["macro_f1"], ep + 1, 0
            torch.save(model.state_dict(), ckpt_dir / "cnn_best.pt")
        else:
            wait += 1
            if wait >= args.patience:
                log.info("early stop: no validation improvement for %d epochs", args.patience)
                break
    model.load_state_dict(torch.load(ckpt_dir / "cnn_best.pt"))
    return model, history, best_ep


# ------------------------------------------------------------------------------------------------------------------
# decision agent
# ------------------------------------------------------------------------------------------------------------------
class QNet(torch.nn.Module):
    def __init__(self, n_in=S.STATE_DIM, n_out=len(ACTIONS), h=128):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(n_in, h), torch.nn.ReLU(), torch.nn.Linear(h, h), torch.nn.ReLU(), torch.nn.Linear(h, n_out))

    def forward(self, x):
        return self.net(x)


def rule_action(state: np.ndarray, alert: int) -> int:
    """Baseline: level straight from the photo (same visual mapping and confidence threshold as the policy)."""
    probs = state[:len(CLASSES)]
    cls, conf = CLASSES[int(probs.argmax())], float(probs.max())
    lvl = VISUAL_LEVEL[cls] if conf >= MIN_CONFIDENCE else 0
    if cls == "heavy_rain":
        lvl = min(lvl, 1)
    return [NO_ALERT, ISSUE_WATCH, ISSUE_WARNING, ISSUE_CRITICAL][lvl]


def run_episodes(env: E.VisualIncidentEnv, policy, n: int) -> dict:
    rewards, metrics = [], []
    for _ in range(n):
        s, done, tot = env.reset(), False, 0.0
        while not done:
            a = policy(s, env.ep.alert)
            s, r, done, _ = env.step(a)
            tot += r
        rewards.append(tot)
        metrics.append(E.episode_metrics(env.ep.log, env.ep.latent))
    ev = [m for m in metrics if m["event"]]
    quiet = [m for m in metrics if not m["event"]]
    det = [m for m in ev if m["detected"]]
    return {"episodes": n, "mean_reward": round(float(np.mean(rewards)), 3), "events": len(ev),
            "events_detected": round(len(det) / max(len(ev), 1), 3),
            "events_warned_early": round(sum(m["early"] for m in ev) / max(len(ev), 1), 3),
            "missed_events": round(1 - len(det) / max(len(ev), 1), 3),
            "mean_delay_steps": round(float(np.mean([m["delay"] for m in det])) if det else None, 2) if det else None,
            "false_alarm_rate_quiet": round(sum(m["false_public_alert"] for m in quiet) / max(len(quiet), 1), 3),
            "repeated_alerts_per_episode": round(float(np.mean([m["repeats"] for m in metrics])), 3),
            "level_changes_per_episode": round(float(np.mean([m["changes"] for m in metrics])), 3),
            "evidence_requests_per_episode": round(float(np.mean([m["requests"] for m in metrics])), 3)}


def train_dqn(pools: dict, args, ckpt_dir: Path):
    env = E.VisualIncidentEnv(pools["train"], seed=args.seed)
    val_env_seed, test_env_seed = args.seed + 100, args.seed + 200
    q, tgt = QNet(), QNet()
    tgt.load_state_dict(q.state_dict())
    opt = torch.optim.Adam(q.parameters(), lr=5e-4)
    replay: deque = deque(maxlen=60_000)
    rng = np.random.default_rng(args.seed)
    gamma, batch, sync, step = 0.95, 128, 1000, 0
    eps_end_ep = int(args.dqn_episodes * 0.6)
    best, curve = -1e9, []

    def greedy(s, _alert):
        with torch.no_grad():
            return int(q(torch.tensor(s)[None]).argmax())
    for ep in range(args.dqn_episodes):
        eps = max(0.05, 1 - ep / eps_end_ep * 0.95)
        s, done = env.reset(), False
        while not done:
            a = int(rng.integers(len(ACTIONS))) if rng.random() < eps else greedy(s, None)   # epsilon-greedy
            s2, r, done, _ = env.step(a)
            replay.append((s, a, r, s2, done))                                            # experience replay
            s = s2
            step += 1
            if len(replay) >= 2000:
                idx = rng.integers(len(replay), size=batch)
                bs, ba, br, bs2, bd = (torch.tensor(np.array(x)) for x in zip(*(replay[i] for i in idx)))
                with torch.no_grad():                                                     # Double DQN target
                    a2 = q(bs2).argmax(1, keepdim=True)
                    y = br.float() + gamma * (1 - bd.float()) * tgt(bs2).gather(1, a2).squeeze(1)
                qsa = q(bs).gather(1, ba.long()[:, None]).squeeze(1)
                loss = Fnn.smooth_l1_loss(qsa, y)                                         # Bellman (Huber) loss
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(q.parameters(), 5.0)
                opt.step()
            if step % sync == 0:
                tgt.load_state_dict(q.state_dict())                                       # target network
        if (ep + 1) % max(1, args.dqn_episodes // 12) == 0:
            v = run_episodes(E.VisualIncidentEnv(pools["val"], seed=val_env_seed), greedy, 600)
            curve.append({"episode": ep + 1, "epsilon": round(eps, 3), **{k: v[k] for k in ("mean_reward", "events_detected", "false_alarm_rate_quiet")}})
            log.info("dqn episode %d eps %.2f val reward %.3f detected %.3f false-alarm %.3f", ep + 1, eps, v["mean_reward"],
                     v["events_detected"], v["false_alarm_rate_quiet"])
            if v["mean_reward"] > best:
                best = v["mean_reward"]
                torch.save(q.state_dict(), ckpt_dir / "dqn_best.pt")
    q.load_state_dict(torch.load(ckpt_dir / "dqn_best.pt"))
    val = {"agent": run_episodes(E.VisualIncidentEnv(pools["val"], seed=val_env_seed), greedy, 1500),
           "photo_rule_baseline": run_episodes(E.VisualIncidentEnv(pools["val"], seed=val_env_seed), rule_action, 1500)}
    test = {"agent": run_episodes(E.VisualIncidentEnv(pools["test"], seed=test_env_seed), greedy, 1500),
            "photo_rule_baseline": run_episodes(E.VisualIncidentEnv(pools["test"], seed=test_env_seed), rule_action, 1500)}
    return q, curve, val, test


# ------------------------------------------------------------------------------------------------------------------
async def record_runs(rows: list[dict]) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.info("DATABASE_URL not set: training runs recorded in vision_meta.json only")
        return
    import asyncpg
    try:
        conn = await asyncpg.connect(url)
    except Exception as e:  # noqa: BLE001
        log.warning("could not record training runs in the database: %s", e)
        return
    try:
        for r in rows:
            await conn.execute(
                """insert into model_training_runs (model_name, model_version, dataset_version, training_parameters,
                   validation_metrics, test_metrics, checkpoint_reference, validated_for_alerts)
                   values ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8) on conflict (model_name, model_version) do nothing""",
                r["model_name"], r["model_version"], r["dataset_version"], json.dumps(r["training_parameters"]),
                json.dumps(r["validation_metrics"]), json.dumps(r["test_metrics"]), r["checkpoint_reference"], r["validated"])
    finally:
        await conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, help="prepared dataset folder (default: build the synthetic one)")
    ap.add_argument("--img-size", type=int, default=128, help="model input resolution (multiple of 16)")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--patience", type=int, default=7)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--dqn-episodes", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()
    assert args.img_size % 16 == 0, "--img-size must be a multiple of 16"
    torch.set_num_threads(args.threads)
    seed_all(args.seed)
    t0 = time.time()

    if args.dataset is None:
        syn = DATA / "synthetic_v1"
        if not (syn / "manifest.csv").exists():
            from app.vision.synth import generate
            log.info("generating the synthetic dataset in %s", syn)
            generate(syn, size=160, seed=7)
        args.dataset = ds.prepare("synthetic", [syn], DATA / "datasets")
    rows, card = ds.load(args.dataset)
    log.info("dataset %s: %d images %s", card["version"], card["images"], card["counts"])
    load_size = int(args.img_size * 1.25)
    split = {sp: [r for r in rows if r.split == sp] for sp in ("train", "val", "test")}
    X = {sp: load_images(rs, load_size) for sp, rs in split.items()}
    y = {sp: np.array([CLASSES.index(r.label) for r in rs]) for sp, rs in split.items()}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    cnn_version, dqn_version = f"visual-cnn-{stamp}", f"visual-dqn-{stamp}"
    ckpt = DATA / "checkpoints" / stamp
    ckpt.mkdir(parents=True, exist_ok=True)

    model, history, best_ep = train_cnn(X["train"], y["train"], X["val"], y["val"], args, ckpt)
    _, lv, _ = predict(model, X["val"], args.img_size)
    T = fit_temperature(lv, y["val"])
    probs, embs = {}, {}
    for sp in ("val", "test"):
        probs[sp], _, embs[sp] = predict(model, X[sp], args.img_size, T)
    p_tr, _, e_tr = predict(model, X["train"], args.img_size, T)
    cnn_val, cnn_test = classification_metrics(y["val"], probs["val"]), classification_metrics(y["test"], probs["test"])
    cond = {}
    for c in sorted({r.condition for r in split["test"]}):
        m = np.array([r.condition == c for r in split["test"]])
        cond[c] = {"n": int(m.sum()), "accuracy": round(float((probs["test"][m].argmax(1) == y["test"][m]).mean()), 3)}
    cnn_test["accuracy_by_condition"] = cond
    log.info("cnn test macro-F1 %.3f accuracy %.3f (temperature %.2f)", cnn_test["macro_f1"], cnn_test["accuracy"], T)

    mu = e_tr.mean(0)
    _, _, vt = np.linalg.svd(e_tr - mu, full_matrices=False)
    comps = vt[:S.EMBED_K]
    scale = ((e_tr - mu) @ comps.T).std(0) + 1e-6
    pca = {"mean": mu.astype(np.float32), "components": comps.astype(np.float32), "scale": scale.astype(np.float32)}

    def pool(p, e, yy):
        proj = S.project(e, pca)
        return E.Pool(probs={c: p[yy == i] for i, c in enumerate(CLASSES)}, emb={c: proj[yy == i] for i, c in enumerate(CLASSES)})
    g = torch.Generator().manual_seed(args.seed + 7)
    aug = [predict(model, X["train"], args.img_size, T, aug_g=g) for _ in range(2)]                 # noisier train pool
    p_aug = np.concatenate([p_tr] + [a[0] for a in aug])
    e_aug = np.concatenate([e_tr] + [a[2] for a in aug])
    pools = {"train": pool(p_aug, e_aug, np.concatenate([y["train"]] * 3)),
             "val": pool(probs["val"], embs["val"], y["val"]), "test": pool(probs["test"], embs["test"], y["test"])}
    q, curve, dqn_val, dqn_test = train_dqn(pools, args, ckpt)
    log.info("agent test: %s", dqn_test["agent"])
    log.info("rule  test: %s", dqn_test["photo_rule_baseline"])

    synthetic = bool(card.get("synthetic_only"))
    cnn_ok = (not synthetic) and cnn_test["macro_f1"] >= 0.80 and cnn_test["flood_or_landslide_recall"] >= 0.85
    a, b = dqn_test["agent"], dqn_test["photo_rule_baseline"]
    dqn_ok = cnn_ok and a["missed_events"] <= b["missed_events"] and a["false_alarm_rate_quiet"] <= b["false_alarm_rate_quiet"] + 0.02

    ART.mkdir(exist_ok=True)
    np.savez_compressed(ART / "cnn.npz", **cnn_mod.export(model))
    np.savez_compressed(ART / "dqn.npz", **{k: v.numpy() for k, v in q.state_dict().items()},
                        pca_mean=pca["mean"], pca_components=pca["components"], pca_scale=pca["scale"])
    params = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "classes": CLASSES, "actions": ACTIONS, "img_size": args.img_size, "mean": MEAN.tolist(), "std": STD.tolist(),
        "temperature": round(T, 4), "state_names": S.STATE_NAMES, "embed_k": S.EMBED_K,
        "cnn": {"version": cnn_version, "architecture": "DisasterCNN " + "-".join(map(str, cnn_mod.CHANNELS)) + " (from scratch)",
                "parameters": int(sum(p.numel() for p in model.parameters())), "best_epoch": best_ep,
                "validated_for_alerts": cnn_ok},
        "dqn": {"version": dqn_version, "algorithm": "Double DQN, replay 60k, target sync 1000, eps 1→0.05, Huber loss, gamma 0.95",
                "validated_for_alerts": dqn_ok, "mode": "active (within policy limits)" if dqn_ok else "advisory (shadow)"},
        "dataset": card, "training_parameters": params,
        "validation_rule": "validated only if trained on non-synthetic data with test macro-F1 ≥ 0.80 and flood/landslide "
                           "recall ≥ 0.85; the agent additionally must not miss more events or raise more false alarms than the photo rule",
        "training_seconds": round(time.time() - t0),
    }
    metrics = {"cnn": {"history": history, "validation": cnn_val, "test": cnn_test, "temperature": T},
               "dqn": {"learning_curve": curve, "validation": dqn_val, "test": dqn_test}}
    (ART / "vision_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (ART / "vision_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_report(meta, metrics)
    asyncio.run(record_runs([
        {"model_name": "visual_cnn", "model_version": cnn_version, "dataset_version": card["version"], "training_parameters": params,
         "validation_metrics": cnn_val, "test_metrics": cnn_test, "checkpoint_reference": str(ckpt / "cnn_best.pt"), "validated": cnn_ok},
        {"model_name": "visual_dqn", "model_version": dqn_version, "dataset_version": card["version"], "training_parameters": params,
         "validation_metrics": dqn_val, "test_metrics": dqn_test, "checkpoint_reference": str(ckpt / "dqn_best.pt"), "validated": dqn_ok}]))
    log.info("done in %.0fs", time.time() - t0)


def write_report(meta: dict, m: dict) -> None:
    c, d = m["cnn"], m["dqn"]
    L = [f"# Visual model evaluation report", "",
         f"Generated {meta['created_at']} by `python -m app.vision.train_all`. Dataset **{meta['dataset']['version']}** "
         f"({meta['dataset']['images']} images).", ""]
    if meta["dataset"].get("synthetic_only"):
        L += ["> **Synthetic data only.** These numbers measure the pipeline on procedurally generated scenes. They say "
              "nothing about accuracy on real photographs. Both models are therefore recorded as *not validated for alerts*, "
              "and the decision agent runs in advisory (shadow) mode. Retrain with a real, labelled dataset (see "
              "docs/visual-disaster-detection.md) before relying on them.", ""]
    L += ["## Image model (CNN, trained from random weights)", "",
          f"{meta['cnn']['architecture']}, {meta['cnn']['parameters']:,} parameters, input {meta['img_size']} px, best epoch "
          f"{meta['cnn']['best_epoch']}, temperature {meta['temperature']}.", "",
          "| Split | Images | Accuracy | Macro-F1 | Flood/landslide recall | Flood/landslide precision | Calibration error (ECE) |",
          "|---|---|---|---|---|---|---|"]
    for name, x in (("Validation (held-out incidents)", c["validation"]), ("Test (held-out locations)", c["test"])):
        L.append(f"| {name} | {x['n']} | {x['accuracy']} | {x['macro_f1']} | {x['flood_or_landslide_recall']} | "
                 f"{x['flood_or_landslide_precision']} | {x['ece']} |")
    L += ["", "### Per class (test)", "", "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for k, v in c["test"]["per_class"].items():
        L.append(f"| {k} | {v['precision']} | {v['recall']} | {v['f1']} | {v['support']} |")
    L += ["", "### Confusion matrix (test; rows = true, columns = predicted)", "", "| | " + " | ".join(CLASSES) + " |",
          "|---" * (len(CLASSES) + 1) + "|"]
    for k, row in zip(CLASSES, c["test"]["confusion_matrix"]):
        L.append(f"| **{k}** | " + " | ".join(map(str, row)) + " |")
    L += ["", "### Accuracy by lighting condition (test)", "", "| Condition | Images | Accuracy |", "|---|---|---|"]
    for k, v in c["test"]["accuracy_by_condition"].items():
        L.append(f"| {k} | {v['n']} | {v['accuracy']} |")
    L += ["", "## Decision agent (DQN) in the simulated incident environment", "",
          "Episodes are built from CNN outputs on validation / test images only. *Photo rule* = level taken straight from "
          "the photo class with the policy's confidence threshold.", "",
          "| Split | Policy | Mean reward | Events detected | Warned before onset | Missed events | Mean delay (steps of 30 min) | False alarms (quiet episodes) | Repeated alerts / episode | Level changes / episode |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for sp, res in (("validation", d["validation"]), ("test", d["test"])):
        for name, x in (("decision agent", res["agent"]), ("photo rule", res["photo_rule_baseline"])):
            L.append(f"| {sp} | {name} | {x['mean_reward']} | {x['events_detected']} | {x['events_warned_early']} | {x['missed_events']} | "
                     f"{x['mean_delay_steps']} | {x['false_alarm_rate_quiet']} | {x['repeated_alerts_per_episode']} | {x['level_changes_per_episode']} |")
    L += ["", f"Agent mode: **{meta['dqn']['mode']}**. Validation rule: {meta['validation_rule']}.", ""]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
