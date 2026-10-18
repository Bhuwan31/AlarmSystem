import pytest

from app.warnings import state_machine as sm
from app.warnings.templates import lint, render


def test_critical_needs_two_distinct_approvers_sr02():
    status, approvers = sm.approve("PROPOSED", "CRITICAL", set(), "anjali", False)
    assert status == "PROPOSED"
    with pytest.raises(sm.TransitionError, match="second distinct approver"):
        sm.approve(status, "CRITICAL", approvers, "anjali", False)
    status, approvers = sm.approve(status, "CRITICAL", approvers, "bikash", False)
    assert status == "ACTIVE" and approvers == {"anjali", "bikash"}


def test_warning_needs_one_approver():
    assert sm.approve("PROPOSED", "WARNING", set(), "anjali", False)[0] == "ACTIVE"


def test_watch_auto_publish_policy():
    assert sm.required_approvals("WATCH", True) == 0
    assert sm.required_approvals("WATCH", False) == 1


def test_cannot_approve_non_proposed():
    with pytest.raises(sm.TransitionError):
        sm.approve("ACTIVE", "WARNING", set(), "x", False)


def test_cancel_and_reject_need_reason():
    with pytest.raises(sm.TransitionError):
        sm.cancel("ACTIVE", " ")
    assert sm.cancel("ACTIVE", "gauge fault confirmed") == "CANCELLED"
    with pytest.raises(sm.TransitionError):
        sm.reject("PROPOSED", "")


def test_never_below_official_sr07():
    with pytest.raises(sm.TransitionError):
        sm.check_not_below_official("WATCH", "WARNING")
    sm.check_not_below_official("CRITICAL", "WARNING")


def test_proposal_only_on_rise():
    assert sm.proposal_needed("WARNING", None, None) == "WARNING"
    assert sm.proposal_needed("WARNING", "WARNING", None) is None
    assert sm.proposal_needed("CRITICAL", "WARNING", None) == "CRITICAL"
    assert sm.proposal_needed("WATCH", None, "WARNING") is None
    assert sm.proposal_needed("NORMAL", None, None) is None
    assert sm.proposal_needed("UNKNOWN", None, None) is None


def test_templates_complete_and_exercise_prefix_sr12():
    assert lint() == []
    msg = render("CRITICAL", "Ward 5", "Rajapur", "20:00", "HIGH", exercise=True)
    assert msg["en"].startswith("EXERCISE – NOT A REAL WARNING")
    assert msg["ne"].startswith("अभ्यास")
    assert "Ward 5" in msg["en"] and "Ward 5" in msg["ne"]
