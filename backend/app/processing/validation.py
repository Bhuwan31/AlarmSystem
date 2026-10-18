"""Observation quality checks (FR-06, FR-08, NFR-R1)."""
from dataclasses import dataclass

# Physical plausibility per variable (min, max)
RANGES = {
    "water_level_m": (-5.0, 60.0),
    "rain_1h_mm": (0.0, 200.0),
    "rain_24h_mm": (0.0, 1000.0),
}
# Largest believable change between consecutive readings
SPIKE_DELTA = {"water_level_m": 3.0, "rain_1h_mm": 150.0}
FLATLINE_N = 12          # identical consecutive readings before a gauge is suspected stuck
FLATLINE_VARS = {"water_level_m"}


@dataclass(frozen=True)
class QualityResult:
    quality: str          # GOOD | SUSPECT | BAD | MISSING
    reason: str | None = None


def station_range(variable: str, warning_level: float | None, danger_level: float | None) -> tuple[float, float]:
    """Plausible range for one station. Some gauges report level as elevation above sea level
    (e.g. 1343.9 m with a 1345.8 m warning level), so the range follows the station's own datum."""
    ref = danger_level if danger_level is not None else warning_level
    if variable == "water_level_m" and ref is not None and ref > RANGES["water_level_m"][1]:
        return ref - 60.0, ref + 30.0
    return RANGES.get(variable, (float("-inf"), float("inf")))


def check(variable: str, value: float | None, previous: list[float],
          bounds: tuple[float, float] | None = None) -> QualityResult:
    """`previous` = earlier GOOD/SUSPECT values for the same station and variable, newest first."""
    if value is None:
        return QualityResult("MISSING", "no value")
    lo, hi = bounds or RANGES.get(variable, (float("-inf"), float("inf")))
    if not lo <= value <= hi:
        return QualityResult("BAD", f"out of range [{lo}, {hi}]")
    delta = SPIKE_DELTA.get(variable)
    if delta is not None and previous and abs(value - previous[0]) > delta:
        return QualityResult("SUSPECT", f"spike: change {value - previous[0]:+.2f} > {delta}")
    if variable in FLATLINE_VARS and len(previous) >= FLATLINE_N - 1 and all(p == value for p in previous[:FLATLINE_N - 1]):
        return QualityResult("SUSPECT", f"flatline: {FLATLINE_N} identical readings")
    return QualityResult("GOOD")
