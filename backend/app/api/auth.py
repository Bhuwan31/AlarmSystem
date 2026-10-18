"""Operator login with optional TOTP two-factor (NFR-S1, SEC-01, SEC-07)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import User, current_user
from app.db import audit, pool
from app.security import (LoginThrottle, mint_token, new_totp_secret, otpauth_uri, verify_password,
                          verify_totp)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
throttle = LoginThrottle()


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    totp: str | None = Field(default=None, max_length=10)


class Code(BaseModel):
    code: str = Field(min_length=6, max_length=10)


def _public(u) -> dict:
    return {"id": str(u["id"]), "email": u["email"], "name": u["name"], "role": u["role"], "mfa_enrolled": u["totp_secret"] is not None}


@router.post("/login")
async def login(body: Login, request: Request):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    if throttle.blocked(f"e:{email}", f"ip:{ip}"):
        raise HTTPException(429, "too many failed attempts; try again in 15 minutes")
    async with pool().acquire() as conn:
        u = await conn.fetchrow("select * from users where lower(email) = $1 and active", email)
        if u is None or not verify_password(body.password, u["password_hash"]):
            throttle.fail(f"e:{email}", f"ip:{ip}")
            await audit(conn, email, "auth.login_failed", "user", None, {"ip": ip})
            raise HTTPException(401, "wrong email or password")
        mfa = False
        if u["totp_secret"]:
            if not body.totp:
                raise HTTPException(401, detail={"mfa_required": True, "message": "enter the 6-digit code from your authenticator app"})
            if not verify_totp(u["totp_secret"], body.totp):
                throttle.fail(f"e:{email}", f"ip:{ip}")
                raise HTTPException(401, detail={"mfa_required": True, "message": "wrong code"})
            mfa = True
        throttle.reset(f"e:{email}", f"ip:{ip}")
        await conn.execute("update users set last_login_at = now() where id = $1", u["id"])
        await audit(conn, str(u["id"]), "auth.login", "user", str(u["id"]), {"ip": ip, "mfa": mfa})
    return {"token": mint_token(str(u["id"]), u["email"], u["role"], mfa), "user": _public(u), "mfa": mfa}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    u = await pool().fetchrow("select * from users where id::text = $1", user.id)
    base = _public(u) if u else {"id": user.id, "email": user.email, "role": user.role, "mfa_enrolled": False}
    return {**base, "mfa_session": user.mfa}


@router.post("/totp/setup")
async def totp_setup(user: User = Depends(current_user)):
    secret = new_totp_secret()
    async with pool().acquire() as conn:
        n = await conn.execute("update users set totp_pending = $2 where id::text = $1", user.id, secret)
        if n.endswith(" 0"):
            raise HTTPException(404, "account not found")
    return {"secret": secret, "otpauth_uri": otpauth_uri(secret, user.email or user.id),
            "note": "Add this to an authenticator app, then confirm with a code."}


@router.post("/totp/verify")
async def totp_verify(body: Code, user: User = Depends(current_user)):
    async with pool().acquire() as conn:
        pending = await conn.fetchval("select totp_pending from users where id::text = $1", user.id)
        if not pending or not verify_totp(pending, body.code):
            raise HTTPException(400, "wrong code")
        await conn.execute("update users set totp_secret = totp_pending, totp_pending = null where id::text = $1", user.id)
        await audit(conn, user.id, "auth.mfa_enrolled", "user", user.id, {})
    return {"mfa_enrolled": True, "note": "Sign in again to get a two-factor session."}
