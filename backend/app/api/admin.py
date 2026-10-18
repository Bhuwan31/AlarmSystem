"""Administration: users, deployment policies and the audit log (FR-59, FR-66, FR-67)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import User, require
from app.db import audit, pool
from app.security import hash_password

router = APIRouter(prefix="/api/v1", tags=["admin"])
ROLES = "^(viewer|operator|approver|admin)$"


class NewUser(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern=ROLES)
    password: str = Field(min_length=12, max_length=200)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=ROLES)
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=200)
    reset_mfa: bool = False


class Policies(BaseModel):
    exercise_mode: bool | None = None
    auto_publish_watch: bool | None = None
    critical_timeout_s: int | None = Field(default=None, ge=60, le=7200)
    watch_fraction: float | None = Field(default=None, ge=0.5, le=0.99)
    watch_margin_m: float | None = Field(default=None, ge=0.1, le=10)
    rise_rate_m_per_h: float | None = Field(default=None, ge=0.05, le=5)
    hold_minutes: int | None = Field(default=None, ge=0, le=720)


@router.get("/users")
async def list_users(_: User = Depends(require("admin"))):
    rows = await pool().fetch("select id, email, name, role, active, totp_secret is not null mfa, created_at, last_login_at from users order by created_at")
    return [{**dict(r), "id": str(r["id"])} for r in rows]


@router.post("/users")
async def create_user(body: NewUser, admin: User = Depends(require("admin"))):
    async with pool().acquire() as conn:
        try:
            uid = await conn.fetchval("insert into users (email, name, role, password_hash) values ($1, $2, $3, $4) returning id",
                                      body.email.lower(), body.name, body.role, hash_password(body.password))
        except Exception as e:  # unique violation
            raise HTTPException(409, "a user with this email already exists") from e
        await audit(conn, admin.id, "user.create", "user", str(uid), {"email": body.email.lower(), "role": body.role})
    return {"id": str(uid)}


@router.patch("/users/{uid}")
async def update_user(uid: str, body: UserUpdate, admin: User = Depends(require("admin"))):
    if uid == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "you cannot demote or deactivate your own account")
    async with pool().acquire() as conn:
        u = await conn.fetchrow("select id from users where id::text = $1", uid)
        if u is None:
            raise HTTPException(404, "user not found")
        if body.role is not None:
            await conn.execute("update users set role = $2 where id = $1", u["id"], body.role)
        if body.active is not None:
            await conn.execute("update users set active = $2 where id = $1", u["id"], body.active)
        if body.password:
            await conn.execute("update users set password_hash = $2 where id = $1", u["id"], hash_password(body.password))
        if body.reset_mfa:
            await conn.execute("update users set totp_secret = null, totp_pending = null where id = $1", u["id"])
        await audit(conn, admin.id, "user.update", "user", uid,
                    {"role": body.role, "active": body.active, "password_reset": bool(body.password), "mfa_reset": body.reset_mfa})
    return {"id": uid}


@router.patch("/profile/policies")
async def update_policies(body: Policies, admin: User = Depends(require("admin", mfa=False))):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "nothing to change")
    async with pool().acquire() as conn:
        row = await conn.fetchrow("update deployment_profile set policies = policies || $1::jsonb, updated_at = now() where id = 1 returning policies", changes)
        await audit(conn, admin.id, "profile.policies", "deployment_profile", "1", changes)
    return row["policies"]


@router.get("/audit")
async def audit_log(limit: int = Query(200, le=1000), action: str | None = None, actor: str | None = None,
                    _: User = Depends(require("admin"))):
    rows = await pool().fetch(
        """select a.id, a.at, a.actor, coalesce(u.email, a.actor) actor_label, a.action, a.entity, a.entity_id, a.payload, a.hash
           from audit_log a left join users u on u.id::text = a.actor
           where ($1::text is null or a.action like $1 || '%') and ($2::text is null or a.actor = $2 or u.email = $2)
           order by a.id desc limit $3""", action, actor, limit)
    return [dict(r) for r in rows]


@router.get("/audit/verify")
async def audit_verify(_: User = Depends(require("admin"))):
    """Recompute the hash chain; any edited, inserted or deleted row breaks it (FR-59)."""
    bad = await pool().fetchrow(
        """select id from (
             select id, hash, prev_hash, lag(hash) over (order by id) expected_prev,
                    encode(digest(coalesce(lag(hash) over (order by id), '') || at::text || actor || action || entity
                                  || coalesce(entity_id, '') || payload::text, 'sha256'), 'hex') expected
             from audit_log) x
           where hash <> expected or prev_hash is distinct from expected_prev
           order by id limit 1""")
    total = await pool().fetchval("select count(*) from audit_log")
    return {"rows": total, "intact": bad is None, "first_broken_id": bad["id"] if bad else None}
