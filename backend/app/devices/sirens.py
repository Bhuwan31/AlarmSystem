"""Siren commands. Sirens only sound for an ACTIVE, approved CRITICAL warning (SR-13)."""
import logging

from app.config import get_settings
from app.db import audit
from app.devices import mqtt
from app.devices.signing import sign_command, to_payload

log = logging.getLogger(__name__)


async def _send(conn, device: dict, command: str, warning_id, issued_by: str, exercise: bool) -> None:
    test_mode = bool(device["test_mode"]) or exercise
    msg = sign_command(get_settings().siren_signing_key, device["id"], command, test_mode)
    await conn.execute(
        """insert into siren_commands (device_id, warning_id, command, test_mode, nonce, signature, issued_by)
           values ($1, $2, $3, $4, $5, $6, $7)""",
        device["id"], warning_id, command, test_mode, msg["nonce"], msg["signature"], issued_by)
    await audit(conn, issued_by, f"siren.{command}", "device", device["id"], {"warning_id": str(warning_id) if warning_id else None, "test_mode": test_mode})
    try:
        await mqtt.publish(f"devices/{device['id']}/command", to_payload(msg))
    except Exception:  # noqa: BLE001 — logged and visible as an un-acked command on the dashboard
        log.exception("could not publish siren command to %s", device["id"])


async def activate_for_warning(conn, warning_id, station_id: int, issued_by: str) -> int:
    w = await conn.fetchrow("select status, level, exercise from warnings where id = $1", warning_id)
    if w is None or w["status"] != "ACTIVE" or w["level"] != "CRITICAL":
        raise ValueError("sirens may only be activated by an ACTIVE CRITICAL warning")
    devices = await conn.fetch("select * from devices where kind = 'siren' and station_id = $1", station_id)
    for d in devices:
        await _send(conn, dict(d), "activate", warning_id, issued_by, w["exercise"])
    return len(devices)


async def stop_for_warning(conn, warning_id, issued_by: str) -> int:
    rows = await conn.fetch(
        """select distinct d.* from siren_commands c join devices d on d.id = c.device_id
           where c.warning_id = $1 and c.command = 'activate'""", warning_id)
    for d in rows:
        await _send(conn, dict(d), "stop", warning_id, issued_by, False)
    return len(rows)


async def self_test(conn, device_id: str, issued_by: str) -> None:
    d = await conn.fetchrow("select * from devices where id = $1 and kind = 'siren'", device_id)
    if d is None:
        raise ValueError("siren not found")
    await _send(conn, dict(d), "self_test", None, issued_by, True)
