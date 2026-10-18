"""Mint a development JWT for testing operator endpoints locally (never use in production).

Usage: python scripts/dev_token.py <user-id> <role: viewer|operator|approver|admin> [--mfa]
In production, tokens come from Supabase Auth and roles are set in app_metadata by an admin.
"""
import sys
import time
from pathlib import Path

import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings

if len(sys.argv) < 3:
    sys.exit(__doc__)
user, role = sys.argv[1], sys.argv[2]
claims = {
    "sub": user, "email": f"{user}@example.test", "aud": get_settings().jwt_audience,
    "app_metadata": {"role": role}, "aal": "aal2" if "--mfa" in sys.argv else "aal1",
    "iat": int(time.time()), "exp": int(time.time()) + 3600,
}
print(jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256"))
