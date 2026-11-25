"""Simulated incident environment for training and evaluating the decision agent (numpy only).

Why a simulator: one static photo is not a sequence of decisions. An *episode* is one place over 12 steps of
30 minutes. A hidden true hazard level (0 none, 1 watch, 2 warning, 3 critical) follows a scenario:

  quiet        stays 0 — normal / rainy / ambiguous photos
  nuisance     0 → 1 → 0 — waterlogged roads that drain
  rising_urban 0 → 1 → 2 (→ 3) — streets slowly flood
  river        1 → 2 (→ 3) — river rises over its banks; river gauge agrees most of the time
  flash        0 … then jumps to 3 — sudden flash flood after intense rain
  landslide    0 … then jumps to 2 or 3
  stale        an OLD flood photo uploaded today while the true level now is 0

Transitions. At each step a new photo arrives with probability 0.6 (always, if the agent asked for more evidence).
Its class follows the hidden level and scenario, and 12 % of photos are wrong or unrelated. The photo's features
are the trained CNN's real outputs on held-out images of that class from the split (train / val / test). Rain-gauge
readings, model rain, river level and official warnings are noisy, sometimes missing, and official warnings lag
by two steps.

Actions: NO_ALERT, MONITOR, ISSUE_WATCH, ISSUE_WARNING, ISSUE_CRITICAL_ALERT, REQUEST_ADDITIONAL_EVIDENCE.

Reward (per step)
  + matching the true level (larger when the level is dangerous)
  − missed danger, growing with the gap (CRITICAL misses cost 1.5×)       → minimise missed events
  − public alert while nothing is happening (false alarm)                  → avoid unnecessary warnings
  − re-raising to a level this incident already had (re-notifies), − flicker → no repeated alerts
    (keeping the current level is free: notifications are deduplicated per incident and level)
  − asking for more evidence (delay), more while danger is present          → reduce notification delays
  + one-off bonus for reaching WARNING up to 3 steps before the true level does → early detection
"""
from dataclasses import dataclass, field

import numpy as np

from app.vision import state as S
from app.vision.classes import ACTION_LEVEL, CLASSES, ISSUE_CRITICAL, ISSUE_WARNING, ISSUE_WATCH, MONITOR, REQUEST_EVIDENCE

T = 12
SCENARIOS = ["quiet", "nuisance", "rising_urban", "river", "flash", "landslide", "stale"]
SCEN_P = [0.22, 0.18, 0.18, 0.14, 0.10, 0.10, 0.08]
C = {c: i for i, c in enumerate(CLASSES)}


def _latent(scen: str, rng: np.random.Generator) -> np.ndarray:
    lv = np.zeros(T, dtype=int)
    if scen == "nuisance":
        a = rng.integers(1, 6)
        lv[a:a + rng.integers(2, 6)] = 1
    elif scen == "rising_urban":
        a = rng.integers(0, 4)
        b = a + rng.integers(2, 4)
        lv[a:] = 1
        lv[b:] = 2
        if rng.random() < 0.35:
            lv[b + rng.integers(2, 4):] = 3
    elif scen == "river":
        lv[:] = 1
        b = rng.integers(1, 6)
        lv[b:] = 2
        if rng.random() < 0.4:
            lv[b + rng.integers(2, 5):] = 3
    elif scen == "flash":
        lv[rng.integers(2, 9):] = 3
    elif scen == "landslide":
        lv[rng.integers(1, 9):] = 3 if rng.random() < 0.4 else 2
    return lv


def _photo_class(scen: str, lvl: int, rng: np.random.Generator) -> str:
    if rng.random() < 0.12:                                   # wrong, unrelated or ambiguous submission
        return str(rng.choice(CLASSES))
    if scen == "stale":
        return str(rng.choice(["urban_flooding", "river_flooding", "flash_flooding"]))
    if lvl == 0:
        return str(rng.choice(["normal", "normal", "heavy_rain", "uncertain", "road_waterlogging"] if scen != "quiet"
                              else ["normal", "normal", "heavy_rain", "uncertain"]))
    if scen in ("landslide",):
        return "landslide"
    if scen == "flash":
        return "flash_flooding"
    if scen == "river":
        return "rising_water" if lvl == 1 else str(rng.choice(["river_flooding", "river_flooding", "rising_water"]))
    if lvl == 1:
        return str(rng.choice(["road_waterlogging", "road_waterlogging", "heavy_rain"]))
    return "urban_flooding"


@dataclass
class Pool:
    """CNN outputs for images of one split: per class, arrays of calibrated probabilities and projected features."""
    probs: dict[str, np.ndarray]
    emb: dict[str, np.ndarray]

    def sample(self, cls: str, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        if cls not in self.probs or len(self.probs[cls]) == 0:
            cls = "uncertain"
        i = rng.integers(len(self.probs[cls]))
        return self.probs[cls][i], self.emb[cls][i]


@dataclass
class Episode:
    scen: str
    latent: np.ndarray
    gauge: bool
    model: bool
    river_av: bool
    official_av: bool
    manual: bool
    accuracy: float
    age_h: float
    hour0: int
    doy: int
    t: int = 0
    alert: int = 0
    steps_since: int = 0
    reports: int = 0
    prior: int = 0
    bonus_given: bool = False
    photo: tuple = field(default_factory=tuple)
    log: list = field(default_factory=list)


class VisualIncidentEnv:
    def __init__(self, pool: Pool, seed: int = 0):
        self.pool = pool
        self.rng = np.random.default_rng(seed)
        self.ep: Episode | None = None

    def reset(self) -> np.ndarray:
        r = self.rng
        scen = str(r.choice(SCENARIOS, p=SCEN_P))
        manual = r.random() < 0.25
        flood_season = scen not in ("quiet", "stale") and r.random() < 0.8
        self.ep = Episode(
            scen=scen, latent=_latent(scen, r), gauge=r.random() < 0.55, model=r.random() < 0.85,
            river_av=r.random() < (0.8 if scen == "river" else 0.4), official_av=r.random() < 0.15, manual=manual,
            accuracy=1000.0 if manual else float(r.uniform(5, 120)),
            age_h=float(r.uniform(12, 96)) if scen == "stale" else float(r.exponential(0.5)),
            hour0=int(r.integers(0, 24)), doy=int(r.integers(160, 270) if flood_season else r.integers(1, 366)))
        self._new_photo(force=True)
        return self._state()

    def _new_photo(self, force=False) -> bool:
        ep = self.ep
        if not force and self.rng.random() > 0.6:
            return False
        cls = _photo_class(ep.scen, int(ep.latent[ep.t]), self.rng)
        ep.photo = self.pool.sample(cls, self.rng)
        ep.reports += 1
        return True

    def _readings(self) -> dict:
        ep, r = self.ep, self.rng
        lvl = int(ep.latent[ep.t])
        out: dict = {}
        if ep.gauge:
            base = {"quiet": 6, "nuisance": 14, "stale": 2}.get(ep.scen, 18)
            g24 = max(0.0, r.normal(base + 28 * lvl, 10))
            g1 = max(0.0, r.normal(1 + (9 if ep.scen == "flash" and lvl else 2.5) * lvl, 2))
            out.update(gauge_rain_1h=g1, gauge_rain_24h=g24)
        if ep.model:
            out["model_rain_24h"] = max(0.0, r.normal(8 + 22 * lvl, 14))
        if ep.river_av:
            rv = lvl if ep.scen == "river" else min(lvl, 1)
            out["river_level"] = int(np.clip(rv + (r.integers(-1, 2) if r.random() < 0.2 else 0), 0, 3))
        if ep.official_av:
            out["official_level"] = int(ep.latent[max(0, ep.t - 2)])
        return out

    def _state(self) -> np.ndarray:
        ep = self.ep
        probs, emb = ep.photo
        ctx = {**self._readings(), "reports_6h": ep.reports, "prior_level": ep.prior, "evidence": ep.reports,
               "hour": (ep.hour0 + ep.t // 2) % 24, "doy": ep.doy, "manual": ep.manual, "accuracy_m": ep.accuracy,
               "age_h": ep.age_h, "alert": ep.alert, "steps_since": ep.steps_since}
        return S.build(probs, emb, ctx)

    def reward(self, action: int, prev_alert: int, new_alert: int) -> float:
        ep = self.ep
        s = int(ep.latent[ep.t])
        r = 0.0
        if new_alert == s:
            r += 0.3 if s > 0 else 0.05
        elif new_alert < s:
            miss = 0.5 * (s - new_alert) * (1.5 if s == 3 else 1.0)
            r -= miss * (0.5 if (action == MONITOR and s == 1) else 1.0)
        else:
            r -= 0.4 * new_alert if s == 0 else 0.15 * (new_alert - s)
        # Keeping the current level is free (dedup means no new message). Raising again to a level this incident already
        # had, after lowering it, re-notifies the same people about the same incident.
        if new_alert > prev_alert and new_alert <= ep.prior:
            r -= 0.25                                                    # duplicate notification
        if new_alert != prev_alert:
            r -= 0.08                                                    # flicker
        if action == REQUEST_EVIDENCE:
            r -= 0.05 + (0.15 if s >= 2 and new_alert < 2 else 0.0)
        if not ep.bonus_given and new_alert >= 2 and s < 2 and (ep.latent[ep.t:ep.t + 4] >= 2).any():
            r += 0.6
            ep.bonus_given = True
        if new_alert >= 2 and s >= 2:
            ep.bonus_given = True                                        # onset reached: no later early bonus
        return r

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        ep = self.ep
        prev = ep.alert
        new = prev if action == REQUEST_EVIDENCE else ACTION_LEVEL[action]
        rew = self.reward(action, prev, new)
        ep.log.append((ep.t, int(ep.latent[ep.t]), action, new))
        ep.steps_since = 0 if new != prev else ep.steps_since + 1
        ep.alert = new
        ep.prior = max(ep.prior, new)
        ep.t += 1
        done = ep.t >= T
        if not done:
            self._new_photo(force=action == REQUEST_EVIDENCE)
        return (np.zeros(S.STATE_DIM, np.float32) if done else self._state()), rew, done, {}


def episode_metrics(log: list, latent: np.ndarray) -> dict:
    """Per-episode outcome. log = [(t, true_level, action, alert_after)]."""
    alerts = np.array([a for *_, a in log])
    acts = [a for _, _, a, _ in log]
    onset = int(np.argmax(latent >= 2)) if (latent >= 2).any() else None
    first_warn = int(np.argmax(alerts >= 2)) if (alerts >= 2).any() else None
    repeats, peak = 0, 0
    for i, a in enumerate(alerts):
        if i > 0 and a > alerts[i - 1] and a <= peak:
            repeats += 1                                     # re-raised to a level already issued: duplicate notification
        peak = max(peak, int(a))
    out = {"event": onset is not None, "repeats": repeats, "changes": int((np.diff(alerts) != 0).sum()),
           "requests": sum(1 for a in acts if a == REQUEST_EVIDENCE)}
    if onset is not None:
        detected = first_warn is not None and (alerts[onset:] >= 2).any()
        out.update(detected=bool(detected), early=bool(first_warn is not None and first_warn < onset),
                   delay=(max(0, first_warn - onset) if detected else None), lead=(onset - first_warn if detected and first_warn < onset else 0))
    out["false_public_alert"] = bool(((alerts >= 1) & (latent == 0)).any() if latent.max() == 0 else ((alerts >= 2) & (latent < 2)).sum() > 2)
    return out
