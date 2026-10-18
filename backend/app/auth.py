"""JWT verification compatible with Supabase Auth (HS256 project secret).

Role comes from app_metadata.role (set by an admin), never from user-editable metadata.
Roles: viewer < operator < approver < admin.
"""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

RANK = {"viewer": 0, "operator": 1, "approver": 2, "admin": 3}
_bearer = HTTPBearer(auto_error=False)


@dataclass
class User:
    id: str
    email: str | None
    role: str
    mfa: bool


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    s = get_settings()
    try:
        claims = jwt.decode(creds.credentials, s.jwt_secret, algorithms=["HS256"], audience=s.jwt_audience)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    role = (claims.get("app_metadata") or {}).get("role", "viewer")
    return User(id=claims["sub"], email=claims.get("email"), role=role if role in RANK else "viewer",
                mfa=claims.get("aal") == "aal2")


def require(role: str, mfa: bool = False):
    def dep(user: User = Depends(current_user)) -> User:
        if RANK[user.role] < RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {role}")
        if mfa and not user.mfa:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "multi-factor authentication required")
        return user
    return dep
