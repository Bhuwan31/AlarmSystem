"""Transparent flood risk rules R1-R10 for one river reach (FR-11..FR-15, SR-06, SR-11).

Pure functions only: the caller gathers inputs from the database and stores the result.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

ENGINE_VERSION = "flood-rules-1.0"
LEVELS = ["NORMAL", "WATCH", "WARNING", "CRITICAL"]


def _rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else -1


def _max(a: str, b: str) -> str:
    return a if _rank(a) >= _rank(b) else b


@dataclass
class Reading:
    at: datetime
    value: float
    quality: str              # GOOD | SUSPECT


@dataclass
class RiskInputs:
    now: datetime
    watch_level: float | None
    warning_level: float | None
    danger_level: float | None
    readings: list[Reading]                   # newest first, GOOD/SUSPECT only
    staleness_s: int
    observed_rain_24h_mm: float | None = None  # max of nearby rain gauges
    satellite_rain_mm_h: float | None = None   # IMERG / INSAT cell rate
    forecast_rain_24h_mm: float | None = None  # Open-Meteo nearest cell
    official_level: str | None = None          # imported official warning for this reach
    previous_level: str | None = None
    recent_candidates: list[tuple[datetime, str]] = field(default_factory=list)  # (computed_at, candidate)
    rise_rate_m_per_h: float = 0.5
    rain_24h_watch_mm: float = 100.0
    satellite_rain_watch_mm_h: float = 20.0
    hold_minutes: int = 60


@dataclass
class RiskResult:
    level: str
    candidate_level: str
    confidence: str
    reasons: list[str]


def assess(i: RiskInputs) -> RiskResult:
    reasons: list[str] = []
    latest = i.readings[0] if i.readings else None
    stale = latest is None or (i.now - latest.at).total_seconds() > i.staleness_s

    # R8: missing/stale data never lowers the level by itself (SR-06)
    if stale:
        held = i.previous_level if i.previous_level in LEVELS else None
        reasons.append("R8: no fresh river reading" + (f"; holding {held}" if held else ""))
        level = held or "UNKNOWN"
        if i.official_level in LEVELS and _rank(i.official_level) > _rank(level if level in LEVELS else "NORMAL"):
            level = i.official_level
            reasons.append(f"Official warning floor: {i.official_level}")
        return RiskResult(level=level, candidate_level=level, confidence="LOW", reasons=reasons)

    v = latest.value
    candidate = "NORMAL"
    if i.danger_level is not None and v >= i.danger_level:
        candidate = "CRITICAL"; reasons.append(f"R1: level {v:.2f} m ≥ danger {i.danger_level:.2f} m")
    elif i.warning_level is not None and v >= i.warning_level:
        candidate = "WARNING"; reasons.append(f"R2: level {v:.2f} m ≥ warning {i.warning_level:.2f} m")
    elif i.watch_level is not None and v >= i.watch_level:
        candidate = "WATCH"; reasons.append(f"R3: level {v:.2f} m ≥ watch {i.watch_level:.2f} m")
    if i.warning_level is None and i.danger_level is None:
        reasons.append("No official thresholds for this station")

    # R4: rapid rise over roughly the last hour bumps one level
    past = [r for r in i.readings[1:] if (latest.at - r.at) >= timedelta(minutes=30)]
    if past:
        ref = past[0]
        hours = (latest.at - ref.at).total_seconds() / 3600
        rate = (v - ref.value) / hours if hours > 0 else 0.0
        if rate >= i.rise_rate_m_per_h:
            bumped = LEVELS[min(_rank(candidate) + 1, len(LEVELS) - 1)]
            reasons.append(f"R4: rising {rate:.2f} m/h ≥ {i.rise_rate_m_per_h} m/h")
            candidate = bumped

    # R6 / satellite: heavy observed rain nearby raises to at least WATCH
    if i.observed_rain_24h_mm is not None and i.observed_rain_24h_mm >= i.rain_24h_watch_mm:
        candidate = _max(candidate, "WATCH"); reasons.append(f"R6: {i.observed_rain_24h_mm:.0f} mm rain in 24 h nearby")
    if i.satellite_rain_mm_h is not None and i.satellite_rain_mm_h >= i.satellite_rain_watch_mm_h:
        candidate = _max(candidate, "WATCH"); reasons.append(f"R6s: satellite rain {i.satellite_rain_mm_h:.1f} mm/h")

    # R7: forecast alone can never go above WATCH (SR-11)
    if i.forecast_rain_24h_mm is not None and i.forecast_rain_24h_mm >= i.rain_24h_watch_mm and _rank(candidate) < _rank("WATCH"):
        candidate = "WATCH"; reasons.append(f"R7: {i.forecast_rain_24h_mm:.0f} mm forecast in 24 h")

    # Official floor (SR-07)
    level = candidate
    if i.official_level in LEVELS and _rank(i.official_level) > _rank(level):
        level = i.official_level; reasons.append(f"Official warning floor: {i.official_level}")

    # R10: hysteresis — only step down after the lower level held for hold_minutes
    if i.previous_level in LEVELS and _rank(level) < _rank(i.previous_level):
        window_start = i.now - timedelta(minutes=i.hold_minutes)
        recent = [c for t, c in i.recent_candidates if t >= window_start]
        covered = any(t <= window_start + timedelta(minutes=5) for t, _ in i.recent_candidates)
        if not covered or any(_rank(c) >= _rank(i.previous_level) for c in recent):
            reasons.append(f"R10: holding {i.previous_level} until lower readings persist {i.hold_minutes} min")
            level = i.previous_level

    confidence = "HIGH"
    if latest.quality != "GOOD" or (i.warning_level is None and i.danger_level is None):
        confidence = "MEDIUM"
    if not reasons:
        reasons.append(f"Level {v:.2f} m below thresholds")
    return RiskResult(level=level, candidate_level=candidate, confidence=confidence, reasons=reasons)
