"""Warning lifecycle rules (FR-18..FR-28, SR-02, SR-07, SR-09). Pure, no I/O."""

LEVEL_RANK = {"WATCH": 1, "WARNING": 2, "CRITICAL": 3}


class TransitionError(ValueError):
    pass


def required_approvals(level: str, auto_publish_watch: bool) -> int:
    if level == "WATCH":
        return 0 if auto_publish_watch else 1
    if level == "WARNING":
        return 1
    if level == "CRITICAL":
        return 2
    raise TransitionError(f"unknown level {level}")


def approve(status: str, level: str, approvers: set[str], approver: str, auto_publish_watch: bool) -> tuple[str, set[str]]:
    """Record one approval. Returns (new_status, approvers)."""
    if status != "PROPOSED":
        raise TransitionError(f"cannot approve a {status} warning")
    if approver in approvers:
        raise TransitionError("second distinct approver required")
    approvers = approvers | {approver}
    new_status = "ACTIVE" if len(approvers) >= required_approvals(level, auto_publish_watch) else "PROPOSED"
    return new_status, approvers


def reject(status: str, reason: str) -> str:
    if status != "PROPOSED":
        raise TransitionError(f"cannot reject a {status} warning")
    if not reason or not reason.strip():
        raise TransitionError("a rejection reason is required")
    return "REJECTED"


def cancel(status: str, reason: str) -> str:
    if status != "ACTIVE":
        raise TransitionError(f"cannot cancel a {status} warning")
    if not reason or not reason.strip():
        raise TransitionError("a cancellation reason is required")
    return "CANCELLED"


def check_not_below_official(level: str, official_level: str | None) -> None:
    """SR-07: a system warning may never be lower than an official one for the same reach."""
    if official_level and LEVEL_RANK.get(level, 0) < LEVEL_RANK.get(official_level, 0):
        raise TransitionError(f"{level} would contradict the official {official_level} warning")


def proposal_needed(risk_level: str, active_level: str | None, open_proposal_level: str | None) -> str | None:
    """Return the level to propose, or None. Proposes only on a rise above what is active/proposed."""
    if risk_level not in LEVEL_RANK:
        return None
    current = max(LEVEL_RANK.get(active_level or "", 0), LEVEL_RANK.get(open_proposal_level or "", 0))
    return risk_level if LEVEL_RANK[risk_level] > current else None
