"""MQTT gateway for own field devices (FR-69, FR-70, FR-74).

Topics (device id = MQTT username, enforced by broker ACL):
  devices/{id}/readings   {"ts": 1760000000, "level_m": 2.31, "rain_mm": 0.4, "battery_v": 3.9, "rssi": -71}
  devices/{id}/heartbeat  {"ts": ..., "battery_v": ..., "rssi": ..., "firmware": "gauge-1.0.0"}
  devices/{id}/ack        {"nonce": "...", "result": "sounding" | "stopped" | "self_test_ok" | "rejected"}
  devices/{id}/command    (server -> siren) signed command, see devices/signing.py
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import aiomqtt

from app import ingest
from app.adapters.base import ObservationRecord
from app.config import get_settings
from app.db import pool

log = logging.getLogger(__name__)
_client: aiomqtt.Client | None = None


async def publish(topic: str, payload: str) -> None:
    if _client is None:
        raise RuntimeError("MQTT not connected")
    await _client.publish(topic, payload, qos=1)


async def _handle(topic: str, payload: dict) -> None:
    parts = topic.split("/")
    if len(parts) != 3:
        return
    _, device_id, kind = parts
    async with pool().acquire() as conn:
        dev = await conn.fetchrow("select * from devices where id = $1", device_id)
        if dev is None:
            log.warning("message from unknown device %s", device_id)
            return
        await conn.execute(
            """update devices set last_seen_at = now(), status = 'ok',
                 battery_v = coalesce($2, battery_v), rssi_dbm = coalesce($3, rssi_dbm), firmware = coalesce($4, firmware)
               where id = $1""",
            device_id, payload.get("battery_v"), payload.get("rssi"), payload.get("firmware"))
        await conn.execute(
            "update data_quality_events set closed_at = now() where kind = 'device_fault' and closed_at is null and detail->>'device_id' = $1",
            device_id)
        if kind == "readings" and dev["station_id"] is not None:
            when = datetime.fromtimestamp(int(payload.get("ts", 0)) or datetime.now().timestamp(), tz=timezone.utc)
            station = await conn.fetchrow("select source_code, external_id from stations where id = $1", dev["station_id"])
            sim = bool(payload.get("simulated"))   # SR-12: simulator readings are flagged
            obs = []
            if payload.get("level_m") is not None:
                obs.append(ObservationRecord("device", station["external_id"], "water_level_m", float(payload["level_m"]), "m", when, payload, sim))
            if payload.get("rain_mm") is not None:
                obs.append(ObservationRecord("device", station["external_id"], "rain_1h_mm", float(payload["rain_mm"]), "mm", when, payload, sim))
            await ingest.insert_observations(conn, obs, {("device", station["external_id"]): dev["station_id"]})
            await ingest.mark_source(conn, "device", None)
        elif kind == "ack" and payload.get("nonce"):
            await conn.execute("update siren_commands set acked_at = now(), ack_payload = $2 where nonce = $1",
                               payload["nonce"], payload)


async def run_forever() -> None:
    global _client
    s = get_settings()
    while True:
        try:
            async with aiomqtt.Client(s.mqtt_host, s.mqtt_port, username=s.mqtt_username or None,
                                      password=s.mqtt_password or None, identifier="amhews-backend") as client:
                _client = client
                await client.subscribe("devices/+/readings", qos=1)
                await client.subscribe("devices/+/heartbeat", qos=1)
                await client.subscribe("devices/+/ack", qos=1)
                log.info("MQTT connected to %s:%s", s.mqtt_host, s.mqtt_port)
                async for message in client.messages:
                    try:
                        await _handle(str(message.topic), json.loads(message.payload))
                    except Exception:  # noqa: BLE001 — one bad message must not stop the gateway
                        log.exception("bad device message on %s", message.topic)
        except aiomqtt.MqttError as e:
            _client = None
            log.warning("MQTT unavailable (%s); retrying in 10 s", e)
            await asyncio.sleep(10)
