from datetime import datetime, timedelta, timezone

from app.risk.engine import Reading, RiskInputs, assess

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def inputs(levels, **kw):
    """levels: newest-first water levels at 15 min spacing."""
    readings = [Reading(NOW - timedelta(minutes=15 * i), v, "GOOD") for i, v in enumerate(levels)]
    base = dict(now=NOW, watch_level=4.0, warning_level=5.0, danger_level=6.0, readings=readings, staleness_s=3600)
    base.update(kw)
    return RiskInputs(**base)


def test_thresholds_r1_to_r3():
    assert assess(inputs([3.0, 3.0, 3.0])).level == "NORMAL"
    assert assess(inputs([4.2, 4.2, 4.2])).level == "WATCH"
    assert assess(inputs([5.1, 5.1, 5.1])).level == "WARNING"
    assert assess(inputs([6.3, 6.3, 6.3])).level == "CRITICAL"


def test_rapid_rise_bumps_one_level_r4():
    r = assess(inputs([4.5, 4.2, 3.9, 3.6, 3.3]))   # +1.2 m/h, starting at WATCH
    assert r.level == "WARNING"
    assert any(x.startswith("R4") for x in r.reasons)


def test_stale_data_never_lowers_level_sr06():
    old = [Reading(NOW - timedelta(hours=3), 2.0, "GOOD")]
    r = assess(inputs([], readings=old, previous_level="WARNING"))
    assert r.level == "WARNING"
    assert r.confidence == "LOW"


def test_stale_with_no_history_is_unknown():
    r = assess(inputs([], readings=[]))
    assert r.level == "UNKNOWN" and r.confidence == "LOW"


def test_forecast_alone_never_exceeds_watch_sr11():
    r = assess(inputs([2.0, 2.0, 2.0], forecast_rain_24h_mm=400))
    assert r.level == "WATCH"


def test_heavy_rain_nearby_raises_to_watch():
    assert assess(inputs([2.0, 2.0], observed_rain_24h_mm=150)).level == "WATCH"


def test_official_warning_is_a_floor_sr07():
    r = assess(inputs([2.0, 2.0], official_level="WARNING"))
    assert r.level == "WARNING"


def test_hysteresis_holds_level_r10():
    # previous level WARNING, readings dropped just now -> must hold
    recent = [(NOW - timedelta(minutes=m), "WARNING") for m in (10, 30, 50, 70)]
    r = assess(inputs([4.1, 4.1, 4.1], previous_level="WARNING", recent_candidates=recent))
    assert r.level == "WARNING" and r.candidate_level == "WATCH"


def test_hysteresis_releases_after_hold_window():
    recent = [(NOW - timedelta(minutes=m), "WATCH") for m in (2, 20, 40, 60, 62)]
    r = assess(inputs([4.1, 4.1, 4.1], previous_level="WARNING", recent_candidates=recent))
    assert r.level == "WATCH"


def test_suspect_reading_lowers_confidence():
    readings = [Reading(NOW, 5.2, "SUSPECT")]
    r = assess(inputs([], readings=readings))
    assert r.level == "WARNING" and r.confidence == "MEDIUM"
