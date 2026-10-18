"""Warning workflow for authorities (FR-20..FR-25, FR-53, SR-02, SR-07, SR-09, SR-13)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import User, require
from app.db import audit, pool
from app.devices import sirens
from app.warnings import state_machine as sm
from app.warnings.templates import render

router = APIRouter(prefix="/api/v1/warnings", tags=["warnings"])


class ManualWarning(BaseModel):
    station_id: int
    level: str = Field(pattern="^(WATCH|WARNING|CRITICAL)$")
    valid_hours: int = Field(6, ge=1, le=72)
    note: str = Field(min_length=3, max_length=500)


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


async def _load(conn, wid):
    w = await conn.fetchrow("select w.*, s.name station_name from warnings w join stations s on s.id = w.station_id where w.id = $1 for update of w", wid)
    if w is None:
        raise HTTPException(404, "warning not found")
    return w


@router.post("")
async def create_manual(body: ManualWarning, user: User = Depends(require("operator"))):
    async with pool().acquire() as conn, conn.transaction():
        st = await conn.fetchrow("select id, name from stations where id = $1", body.station_id)
        if st is None:
            raise HTTPException(404, "station not found")
        profile = await conn.fetchrow("select policies from deployment_profile where id = 1")
        official = await conn.fetchval("select level from warnings where station_id = $1 and status = 'ACTIVE' and source = 'official_import'", body.station_id)
        try:
            sm.check_not_below_official(body.level, official)
        except sm.TransitionError as e:
            raise HTTPException(409, str(e)) from e
        exercise = bool(profile["policies"].get("exercise_mode", True))
        valid_until = datetime.now(timezone.utc) + timedelta(hours=body.valid_hours)
        msg = render(body.level, st["name"], issuer="pending approval", valid_until=valid_until.strftime("%Y-%m-%d %H:%M UTC"),
                     confidence="set by operator", exercise=exercise)
        await conn.execute("update warnings set status = 'SUPERSEDED', updated_at = now() where station_id = $1 and status = 'PROPOSED'", body.station_id)
        wid = await conn.fetchval(
            """insert into warnings (station_id, level, status, source, exercise, confidence, message, reasons, proposed_by, valid_until)
               values ($1, $2, 'PROPOSED', 'manual', $3, 'MEDIUM', $4, $5, $6, $7) returning id""",
            body.station_id, body.level, exercise, msg, [f"Manual: {body.note}"], user.id, valid_until)
        await audit(conn, user.id, "warning.create_manual", "warning", str(wid), body.model_dump())
    return {"id": str(wid), "status": "PROPOSED"}


@router.post("/{wid}/approve")
async def approve(wid: str, user: User = Depends(require("approver", mfa=False))):
    async with pool().acquire() as conn, conn.transaction():
        w = await _load(conn, wid)
        if w["level"] == "CRITICAL" and not user.mfa:
            # CRITICAL approvals need an MFA session (NFR-S1); lower levels tolerate password sessions in the MVP
            raise HTTPException(403, "multi-factor authentication required to approve CRITICAL")
        profile = await conn.fetchrow("select policies from deployment_profile where id = 1")
        approvers = set(await conn.fetchval("select coalesce(array_agg(approver), '{}') from warning_approvals where warning_id = $1", w["id"]))
        try:
            new_status, approvers = sm.approve(w["status"], w["level"], approvers, user.id, bool(profile["policies"].get("auto_publish_watch")))
        except sm.TransitionError as e:
            raise HTTPException(409, str(e)) from e
        await conn.execute("insert into warning_approvals (warning_id, approver) values ($1, $2)", w["id"], user.id)
        await audit(conn, user.id, "warning.approve", "warning", wid, {"level": w["level"], "approvals": len(approvers)})
        if new_status == "ACTIVE":
            prev = await conn.fetchval("update warnings set status = 'SUPERSEDED', updated_at = now() where station_id = $1 and status = 'ACTIVE' returning id", w["station_id"])
            issuer = user.email or user.id
            msg = render(w["level"], w["station_name"], issuer=issuer, valid_until=w["valid_until"].strftime("%Y-%m-%d %H:%M UTC"),
                         confidence=w["confidence"], exercise=w["exercise"])
            await conn.execute("update warnings set status = 'ACTIVE', valid_from = now(), message = $2, supersedes = $3, updated_at = now() where id = $1",
                               w["id"], msg, prev)
            await audit(conn, user.id, "warning.activate", "warning", wid, {"level": w["level"], "supersedes": str(prev) if prev else None})
            if w["level"] == "CRITICAL":
                await sirens.activate_for_warning(conn, w["id"], w["station_id"], issued_by=user.id)
    return {"id": wid, "status": new_status, "approvals": len(approvers)}


@router.post("/{wid}/reject")
async def reject(wid: str, body: Reason, user: User = Depends(require("approver"))):
    async with pool().acquire() as conn, conn.transaction():
        w = await _load(conn, wid)
        try:
            new_status = sm.reject(w["status"], body.reason)
        except sm.TransitionError as e:
            raise HTTPException(409, str(e)) from e
        await conn.execute("update warnings set status = $2, rejection_reason = $3, updated_at = now() where id = $1", w["id"], new_status, body.reason)
        await audit(conn, user.id, "warning.reject", "warning", wid, {"reason": body.reason})
    return {"id": wid, "status": new_status}


@router.post("/{wid}/cancel")
async def cancel(wid: str, body: Reason, user: User = Depends(require("approver"))):
    async with pool().acquire() as conn, conn.transaction():
        w = await _load(conn, wid)
        try:
            new_status = sm.cancel(w["status"], body.reason)
        except sm.TransitionError as e:
            raise HTTPException(409, str(e)) from e
        await conn.execute("update warnings set status = $2, cancel_reason = $3, updated_at = now() where id = $1", w["id"], new_status, body.reason)
        await audit(conn, user.id, "warning.cancel", "warning", wid, {"reason": body.reason, "all_clear": True})
        await sirens.stop_for_warning(conn, w["id"], issued_by=user.id)
    return {"id": wid, "status": new_status}
