"""Password hashing (scrypt), TOTP two-factor codes (RFC 6238) and token minting. Standard library only."""
import base64
import hashlib
import hmac
import secrets
import struct
import time

import jwt

from app.config import get_settings

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **SCRYPT)
    return hmac.compare_digest(h.hex(), hash_hex)


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    now = at if at is not None else time.time()
    code = (code or "").strip().replace(" ", "")
    return any(hmac.compare_digest(totp_code(secret, now + d * 30), code) for d in (-1, 0, 1))


def otpauth_uri(secret: str, email: str, issuer: str = "AMHEWS") -> str:
    return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&digits=6&period=30"


def mint_token(user_id: str, email: str, role: str, mfa: bool, hours: int = 8) -> str:
    """Same claim layout as Supabase Auth, so the backend can switch to Supabase without code changes."""
    s = get_settings()
    now = int(time.time())
    claims = {"sub": user_id, "email": email, "aud": s.jwt_audience, "app_metadata": {"role": role},
              "aal": "aal2" if mfa else "aal1", "iat": now, "exp": now + hours * 3600}
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


class LoginThrottle:
    """SEC-07: back off after repeated failures per email and per client IP."""

    def __init__(self, max_failures: int = 5, window_s: int = 900):
        self.max, self.window = max_failures, window_s
        self.failures: dict[str, list[float]] = {}

    def blocked(self, *keys: str) -> bool:
        now = time.time()
        for k in keys:
            recent = [t for t in self.failures.get(k, []) if now - t < self.window]
            self.failures[k] = recent
            if len(recent) >= self.max:
                return True
        return False

    def fail(self, *keys: str) -> None:
        for k in keys:
            self.failures.setdefault(k, []).append(time.time())

    def reset(self, *keys: str) -> None:
        for k in keys:
            self.failures.pop(k, None)
