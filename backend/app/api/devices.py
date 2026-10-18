"""Field device registry and siren self-test (FR-69, FR-70, FR-75)."""
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import User, require
from app.config import get_settings
from app.db import audit, pool
from app.devices import sirens
from app.devices.signing import device_key

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class NewDevice(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,40}$")
    kind: str = Field(pattern="^(gauge|siren)$")
    name: str = Field(min_length=3, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    station_id: int | None = None          # siren: river reach it covers
    warning_level: float | None = None     # gauge: thresholds for its own reach
    danger_level: float | None = None


@router.get("")
async def list_devices():
    rows = await pool().fetch(
        """select id, kind, name, ST_X(geom) lon, ST_Y(geom) lat, station_id, firmware, battery_v, rssi_dbm,
                  last_seen_at, status, test_mode from devices order by id""")
    return [dict(r) for r in rows]


@router.post("")
async def register(body: NewDevice, user: User = Depends(require("admin"))):
    secret = secrets.token_urlsafe(24)
    async with pool().acquire() as conn, conn.transaction():
        station_id = body.station_id
        if body.kind == "gauge":
            profile = await conn.fetchrow("select policies from deployment_profile where id = 1")
            wf = float(profile["policies"].get("watch_fraction", 0.8))
            station_id = await conn.fetchval(
                """insert into stations (source_code, external_id, kind, name, geom, watch_level, warning_level, danger_level, meta)
                   values ('device', $1, 'device_river', $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5, $6, $7, '{}')
                   on conflict (source_code, external_id) do update set name = excluded.name returning id""",
                body.id, body.name, body.lon, body.lat,
                body.warning_level * wf if body.warning_level else None, body.warning_level, body.danger_level)
        try:
            await conn.execute(
                """insert into devices (id, kind, name, geom, station_id, secret_hash)
                   values ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326), $6, $7)""",
                body.id, body.kind, body.name, body.lon, body.lat, station_id, hashlib.sha256(secret.encode()).hexdigest())
        except Exception as e:  # unique violation
            raise HTTPException(409, f"could not register device: {e}") from e
        await audit(conn, user.id, "device.register", "device", body.id, body.model_dump())
    out = {"id": body.id, "mqtt_username": body.id, "mqtt_password": secret, "station_id": station_id,
           "note": "Shown once. Add to the broker password file and flash to the device."}
    if body.kind == "siren":
        out["command_key_hex"] = device_key(get_settings().siren_signing_key, body.id).hex()
    return out


@router.post("/{device_id}/self-test")
async def siren_self_test(device_id: str, user: User = Depends(require("operator"))):
    async with pool().acquire() as conn, conn.transaction():
        try:
            await sirens.self_test(conn, device_id, issued_by=user.id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
    return {"device_id": device_id, "command": "self_test"}
