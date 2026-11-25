"""Independent safety and alert policy for photo-based detections.

The models (CNN, decision agent) only advise. This module decides what may be PROPOSED to a human reviewer, using
explicit, testable rules. Nothing here sends a notification: an approver must review the incident and press send.

Key rules
  * A photo alone never establishes that rain is happening now: "heavy rain" evidence is capped at WATCH, and
    weather corroboration is reported separately (confirmed / supported_by_model / contradicted / unavailable).
    Missing weather data is never counted as confirmation.
  * Without independent corroboration (rain gauges, river gauge, official warning) a photo is capped at WARNING.
    CRITICAL needs corroboration AND a second report or an official warning.
  * Stale photos (taken > 6 h ago), photos dated in the future, duplicates, uncertain locations and unknown capture
    times are blocked or capped.
  * An agent that has not been validated on real data runs in advisory (shadow) mode: its action is recorded and
    shown, but has no effect on the decision.
"""
from dataclasses import dataclass, field

from app.vision.classes import LEVEL_ACTION, RISK

MIN_CONFIDENCE = 0.60        # below this a photo cannot make an alert eligible
MONITOR_CONFIDENCE = 0.40
STALE_HOURS = 6.0
FUTURE_SKEW_MIN = 10.0
LOCATION_ACCURACY_M = 1000.0
RADII = (1, 3, 5, 10)

# Visual-only level per class (when confidence ≥ MIN_CONFIDENCE)
VISUAL_LEVEL = {"normal": 0, "uncertain": 0, "heavy_rain": 1, "road_waterlogging": 1, "rising_water": 1,
                "urban_flooding": 2, "river_flooding": 2, "flash_flooding": 2, "landslide": 2}
RAIN_DRIVEN = {"heavy_rain", "road_waterlogging", "urban_flooding", "flash_flooding"}

# Suggested radius (km) by class and level 1..3. Final radius is the reviewer's choice among RADII.
RADIUS = {"road_waterlogging": (1, 1, 3), "heavy_rain": (3, 3, 5), "urban_flooding": (1, 3, 5), "rising_water": (3, 5, 10),
          "river_flooding": (3, 5, 10), "flash_flooding": (5, 5, 10), "landslide": (1, 3, 3)}


@dataclass
class Evidence:
    weather_correlation: str = "unavailable"     # confirmed | supported_by_model | contradicted | unavailable
    river_level: int | None = None               # nearest river gauge level 0-3, None = no gauge nearby
    river_km: float | None = None
    official_level: int | None = None            # active official warning nearby, None = none
    reports_nearby: int = 0                      # other credible photo reports within 2 km in the last 6 h
    age_h: float | None = None                   # hours since capture; None = capture time unknown
    future_min: float = 0.0                      # minutes the capture time lies in the future
    capture_time_source: str = "unknown"
    image_source: str = "upload"
    location_source: str | None = None
    accuracy_m: float | None = None
    duplicate_of: str | None = None
    model_available: bool = True


@dataclass
class Decision:
    level: int
    alert_level: str
    risk_level: str
    policy_action: str
    eligible: bool
    radius_km: int
    weather_correlation: str
    corroborated: bool
    reasons: list[str] = field(default_factory=list)


def suggest_radius(cls: str, level: int, ev: Evidence) -> int:
    if level <= 0 or cls not in RADIUS:
        return 1
    r = RADIUS[cls][min(level, 3) - 1]
    if ev.official_level is not None and ev.official_level >= 2:
        r = max(r, 5)
    if cls in ("river_flooding", "rising_water") and ev.river_km is not None and ev.river_km <= 2:
        r = next((x for x in RADII if x > r), r)                  # right next to a gauged river: one step wider
    return min(RADII, key=lambda x: abs(x - r))


def evaluate(cls: str, confidence: float, ev: Evidence, dqn_action: str | None = None, dqn_validated: bool = False) -> Decision:
    reasons: list[str] = []
    corroborated = (ev.weather_correlation == "confirmed" or (ev.river_level is not None and ev.river_level >= 2)
                    or (ev.official_level is not None and ev.official_level >= 2))

    def done(level: int, action: str | None, eligible: bool) -> Decision:
        return Decision(level=level, alert_level=["NONE", "WATCH", "WARNING", "CRITICAL"][level], risk_level=RISK[level],
                        policy_action=action or LEVEL_ACTION[level], eligible=eligible,
                        radius_km=suggest_radius(cls, level, ev), weather_correlation=ev.weather_correlation,
                        corroborated=corroborated, reasons=reasons)

    if not ev.model_available:
        reasons.append("Image model unavailable: no automatic assessment. A reviewer can still look at the photo.")
        return done(0, "REQUEST_ADDITIONAL_EVIDENCE", False)
    if ev.duplicate_of:
        reasons.append(f"Same or near-identical photo already submitted (observation {ev.duplicate_of}); not counted again.")
        return done(0, "NO_ALERT", False)
    if ev.future_min > FUTURE_SKEW_MIN:
        reasons.append(f"Capture time is {ev.future_min:.0f} min in the future: timestamp unreliable.")
        return done(0, "REQUEST_ADDITIONAL_EVIDENCE", False)
    if ev.age_h is not None and ev.age_h > STALE_HOURS:
        reasons.append(f"Photo was taken {ev.age_h:.0f} h ago (more than {STALE_HOURS:.0f} h): historical evidence, not a current alert.")
        return done(0, "NO_ALERT", False)

    level = VISUAL_LEVEL.get(cls, 0) if confidence >= MIN_CONFIDENCE else 0
    if cls == "uncertain" or confidence < MONITOR_CONFIDENCE:
        reasons.append("The photo does not show clear evidence; more photos or sensor data are needed.")
        return done(0, "REQUEST_ADDITIONAL_EVIDENCE", False)
    if level == 0:
        if VISUAL_LEVEL.get(cls, 0) > 0:
            reasons.append(f"Possible {cls.replace('_', ' ')} but confidence {confidence:.0%} is below {MIN_CONFIDENCE:.0%}: monitor only.")
            return done(0, "MONITOR", False)
        reasons.append("No hazard visible in the photo.")
        return done(0, "NO_ALERT", False)

    if cls == "rising_water" and confidence >= 0.85 and (ev.river_level or 0) >= 1:
        level = 2
        reasons.append("Water close to the banks and the nearest river gauge is elevated.")
    if corroborated and cls in ("urban_flooding", "river_flooding", "flash_flooding") and confidence >= 0.80 \
            and (ev.reports_nearby >= 1 or (ev.official_level or 0) >= 2):
        level = 3
        reasons.append("Corroborated by independent data and a second report / official warning.")

    # --- caps -------------------------------------------------------------------------------------------------
    if cls == "heavy_rain" and level > 1:
        level = 1
    if cls == "heavy_rain":
        reasons.append("A photo shows rain was falling when taken; it does not by itself confirm rain now.")
    if not corroborated and level > 2:
        level = 2
    if not corroborated:
        reasons.append("Not yet corroborated by rain gauges, river gauges or an official warning: capped at WARNING.")
    if ev.weather_correlation == "contradicted" and cls in RAIN_DRIVEN and level > 1:
        level = 1
        reasons.append("Rain gauges near the photo recorded little rain: capped at WATCH pending review.")
    elif ev.weather_correlation == "unavailable":
        reasons.append("No weather data for this place and time — treated as unknown, not as confirmation.")
    loc_uncertain = ev.location_source is None or ev.location_source == "manual" or (ev.accuracy_m is not None and ev.accuracy_m > LOCATION_ACCURACY_M)
    if loc_uncertain and level > 1 and not corroborated:
        level = 1
        reasons.append("Location was entered by hand or is imprecise: capped at WATCH until confirmed.")
    if ev.age_h is None and ev.image_source == "upload" and level > 1 and not corroborated:
        level = 1
        reasons.append("Uploaded photo has no capture time, so it may not be current: capped at WATCH.")

    # --- decision agent (advisory unless validated) ----------------------------------------------------------
    if dqn_action:
        if not dqn_validated:
            reasons.append(f"Decision agent advised {dqn_action} (advisory only: not yet validated on real data).")
        elif dqn_action == "REQUEST_ADDITIONAL_EVIDENCE":
            reasons.append("Validated decision agent asks for more evidence before alerting.")
            return done(level, "REQUEST_ADDITIONAL_EVIDENCE", False)
        else:
            from app.vision.classes import ACTION_LEVEL, ACTIONS
            agent = ACTION_LEVEL.get(ACTIONS.index(dqn_action), 0)
            if agent < level:
                level = max(level - 1, agent)
                reasons.append(f"Validated decision agent advised {dqn_action}: lowered one level.")

    eligible = level >= 1 and confidence >= MIN_CONFIDENCE
    reasons.append("Eligible to PROPOSE an alert: a reviewer must approve before anything is sent." if eligible
                   else "Not eligible for an alert.")
    return done(level, None, eligible)
