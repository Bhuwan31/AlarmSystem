"""Siren command signing (SR-13, SEC-10).

Each siren holds its own key, derived as HMAC(master_key, device_id) and flashed at provisioning.
The server re-derives it, so the master key never leaves the backend and one leaked device key
cannot command other sirens. Devices reject commands older than MAX_AGE_S or with a reused nonce.
"""
import hashlib
import hmac
import json
import secrets
import time

MAX_AGE_S = 120


def device_key(master_key: str, device_id: str) -> bytes:
    return hmac.new(master_key.encode(), device_id.encode(), hashlib.sha256).digest()


def canonical(device_id: str, command: str, test_mode: bool, nonce: str, issued_at: int) -> bytes:
    return f"{device_id}|{command}|{int(test_mode)}|{nonce}|{issued_at}".encode()


def sign_command(master_key: str, device_id: str, command: str, test_mode: bool,
                 issued_at: int | None = None, nonce: str | None = None) -> dict:
    issued_at = issued_at or int(time.time())
    nonce = nonce or secrets.token_hex(8)
    sig = hmac.new(device_key(master_key, device_id), canonical(device_id, command, test_mode, nonce, issued_at),
                   hashlib.sha256).hexdigest()
    return {"device_id": device_id, "command": command, "test_mode": test_mode,
            "nonce": nonce, "issued_at": issued_at, "signature": sig}


def verify_command(key: bytes, msg: dict, now: int | None = None, seen_nonces: set[str] | None = None) -> bool:
    """Reference implementation of what the siren firmware does."""
    now = now or int(time.time())
    if abs(now - int(msg["issued_at"])) > MAX_AGE_S:
        return False
    if seen_nonces is not None and msg["nonce"] in seen_nonces:
        return False
    expected = hmac.new(key, canonical(msg["device_id"], msg["command"], bool(msg["test_mode"]), msg["nonce"],
                                       int(msg["issued_at"])), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, msg["signature"])


def to_payload(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"))
