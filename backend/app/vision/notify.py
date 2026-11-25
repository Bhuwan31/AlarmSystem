"""Location-aware notification distribution over the available channels, with deduplication, cooldown, rate limits
and per-recipient delivery records (emergency_notifications).

Channels
  in_app  always available (the row itself is the inbox entry)
  email   SMTP, when SMTP_HOST is set
  sms     Twilio REST API, when TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM are set
  push    Web Push, when VAPID keys are set and the pywebpush package is installed
  ntfy    phone notification through the free ntfy app (NTFY_SERVER, default https://ntfy.sh), to the resident's own topic
External channels are SIMULATED (recorded as 'simulated', nothing leaves the server) until NOTIFY_EXTERNAL_ENABLED=true,
so the whole flow can be tested with simulated users first.
"""
import asyncio
import json
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.geo_nepal import canonical_city, canonical_district, canonical_province, CITIES

log = logging.getLogger(__name__)
CHANNELS = ("in_app", "ntfy", "push", "sms", "email")
LEVEL_RANK = {"INFO": 0, "WATCH": 1, "WARNING": 2, "CRITICAL": 3}

HAZARD_WORDS = {"FLOOD": "flooding", "FLASH_FLOOD": "flash flooding", "RIVER_FLOOD": "river flooding",
                "LANDSLIDE": "a landslide", "HEAVY_RAIN": "heavy rainfall"}
ADVICE = {
    "FLOOD": "Avoid flooded roads and underpasses. Do not walk or drive through moving water. Move to higher floors or higher ground if water rises.",
    "FLASH_FLOOD": "Move away from streams and river banks now. Flash floods rise in minutes. Go to higher ground and do not cross moving water.",
    "RIVER_FLOOD": "Keep away from the river bank and bridges. Prepare to move to higher ground and follow instructions from local officials.",
    "LANDSLIDE": "Stay away from steep slopes and the debris area. Avoid travel on the affected road. Watch for cracks, falling rocks or muddy water.",
    "HEAVY_RAIN": "Heavy rain may cause local flooding. Avoid low-lying roads and stay informed.",
}
LEVEL_WORD = {"WATCH": "FLOOD WATCH", "WARNING": "FLOOD WARNING", "CRITICAL": "CRITICAL FLOOD ALERT"}


@dataclass
class Recipient:
    user_id: str
    email: str | None
    phone: str | None
    channels: dict
    distance_km: float | None
    ntfy_topic: str | None = None


def incident_title(level: str, disaster_type: str) -> str:
    if disaster_type == "LANDSLIDE":
        return {"WATCH": "LANDSLIDE WATCH", "WARNING": "LANDSLIDE WARNING", "CRITICAL": "CRITICAL LANDSLIDE ALERT"}[level]
    return LEVEL_WORD[level]


def incident_body(level: str, risk: str, disaster_type: str, location: str, reported: datetime, tz: str,
                  distance_km: float | None, exercise: bool, extra: str | None = None) -> str:
    local = reported.astimezone(ZoneInfo(tz))
    lines = []
    if exercise:
        lines.append("[EXERCISE — this is a test, not a real event]")
    lines += [f"Potential {HAZARD_WORDS.get(disaster_type, 'flooding')} detected near your area.",
              f"Location: {location}", f"Risk level: {risk}",
              f"Reported: {local.strftime('%Y-%m-%d %H:%M')} ({local.strftime('%z')[:3]}:{local.strftime('%z')[3:]} {tz})"]
    if distance_km is not None:
        lines.append(f"Distance: {distance_km:.1f} km from your saved location")
    lines.append(ADVICE.get(disaster_type, ADVICE["FLOOD"]))
    if extra:
        lines.append(extra)
    lines += ["Source: AI-assisted visual observation, reviewed and approved by an authorised operator.",
              "This alert is not an official government emergency announcement."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------------
# recipients
# ---------------------------------------------------------------------------------------------------------------------
_BASE = """select s.user_id::text uid, coalesce(s.email, u.email) email, s.phone, s.channels, s.ntfy_topic {dist}
           from alert_subscriptions s join users u on u.id = s.user_id
           where s.consent and s.opted_out_at is null and u.active"""


def _rows(rows) -> list[Recipient]:
    return [Recipient(r["uid"], r["email"], r["phone"], r["channels"] or {"in_app": True},
                      round(r["km"], 2) if "km" in r.keys() and r["km"] is not None else None, r["ntfy_topic"]) for r in rows]


async def recipients_near(conn, lat: float, lon: float, radius_km: float) -> list[Recipient]:
    q = _BASE.format(dist=", ST_Distance(s.home::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) / 1000 km") + \
        " and s.home is not null and ST_DWithin(s.home::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3 * 1000) order by km"
    return _rows(await conn.fetch(q, lat, lon, radius_km))


async def recipients_notified(conn, incident_id) -> list[Recipient]:
    """People who already received an alert for this incident (for updates and the all-clear)."""
    q = _BASE.format(dist=", min(n.distance_km) km").replace("from alert_subscriptions s", "from alert_subscriptions s join emergency_notifications n on n.recipient_id = s.user_id")
    q += " and n.incident_id = $1 and n.notification_status in ('delivered', 'sent', 'simulated') group by s.user_id, u.email, s.email, s.phone, s.channels, s.ntfy_topic"
    return _rows(await conn.fetch(q, incident_id))


async def recipients_for_target(conn, target_type: str, value: str | None, lat: float | None, lon: float | None,
                                radius_km: float | None) -> list[Recipient]:
    if target_type == "country":
        return _rows(await conn.fetch(_BASE.format(dist="")))
    if target_type == "province":
        return _rows(await conn.fetch(_BASE.format(dist="") + " and lower(s.province) = lower($1)", canonical_province(value) or value))
    if target_type == "district":
        return _rows(await conn.fetch(_BASE.format(dist="") + " and lower(s.district) = lower($1)", canonical_district(value) or value))
    if target_type == "city":
        c = canonical_city(value)
        if c is None:
            raise ValueError(f"unknown city {value!r}")
        _, clat, clon, r = CITIES[c]
        return await recipients_near(conn, clat, clon, radius_km or r)
    if target_type == "point":
        return await recipients_near(conn, lat, lon, radius_km)
    raise ValueError(f"unknown target type {target_type!r}")


def resolve_channels(r: Recipient, allowed: set[str]) -> list[str]:
    ch = [c for c in CHANNELS if c in allowed and (r.channels or {}).get(c)]
    if "in_app" in allowed and "in_app" not in ch:
        ch.insert(0, "in_app")                                     # the inbox copy is always kept
    if "sms" in ch and not r.phone:
        ch.remove("sms")
    if "email" in ch and not r.email:
        ch.remove("email")
    if "ntfy" in ch and not r.ntfy_topic:
        ch.remove("ntfy")
    return ch


# ---------------------------------------------------------------------------------------------------------------------
# channels
# ---------------------------------------------------------------------------------------------------------------------
def configured(channel: str) -> bool:
    s = get_settings()
    if channel == "in_app":
        return True
    if channel == "email":
        return bool(s.smtp_host and s.smtp_from)
    if channel == "sms":
        return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from)
    if channel == "ntfy":
        return bool(s.ntfy_server)
    if channel == "push":
        if not (s.vapid_private_key and s.vapid_subject):
            return False
        try:
            import pywebpush  # noqa: F401
        except ImportError:
            return False
        return True
    return False


def _send_email(to: str, title: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, title
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password)
        smtp.send_message(msg)


async def _send_sms(to: str, title: str, body: str) -> None:
    s = get_settings()
    text = f"{title}\n{body}"[:1500]
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                              data={"From": s.twilio_from, "To": to, "Body": text}, auth=(s.twilio_account_sid, s.twilio_auth_token))
        r.raise_for_status()


NTFY_PRIORITY = {"CRITICAL": 5, "WARNING": 5, "WATCH": 4, "INFO": 4}       # 4 = vibrate + pop-up; 5 = long vibration, over other apps
NTFY_TAGS = {"CRITICAL": ["rotating_light"], "WARNING": ["warning"], "WATCH": ["droplet"], "INFO": ["information_source"]}


async def send_ntfy(topic: str, title: str, body: str, level: str = "INFO") -> None:
    """Publish to an ntfy topic (JSON form, so titles and Nepali text keep their characters)."""
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.ntfy_token}"} if s.ntfy_token else {}
    payload = {"topic": topic, "title": title[:250], "message": body[:3500], "priority": NTFY_PRIORITY.get(level, 3),
               "tags": NTFY_TAGS.get(level, [])}
    if s.public_app_url:
        payload["click"] = s.public_app_url
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(s.ntfy_server.rstrip("/") + "/", headers=headers, json=payload)
        r.raise_for_status()


async def _send_push(conn, user_id: str, title: str, body: str) -> None:
    from pywebpush import webpush  # type: ignore[import-not-found]
    s = get_settings()
    subs = await conn.fetch("select endpoint, p256dh, auth from push_subscriptions where user_id::text = $1", user_id)
    if not subs:
        raise RuntimeError("no push subscription registered")
    for sub in subs:
        await asyncio.to_thread(webpush, {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                                json.dumps({"title": title, "body": body[:300]}), vapid_private_key=s.vapid_private_key,
                                vapid_claims={"sub": s.vapid_subject})


async def deliver(conn, channel: str, r: Recipient, title: str, body: str, level: str = "INFO") -> tuple[str, str | None]:
    """Returns (status, error)."""
    if channel == "in_app":
        return "delivered", None
    if not configured(channel):
        return "skipped_unconfigured", f"{channel} is not configured on this server"
    if not get_settings().notify_external_enabled:
        log.info("SIMULATED %s to user %s: %s", channel, r.user_id, title)
        return "simulated", None
    try:
        if channel == "email":
            await asyncio.to_thread(_send_email, r.email, title, body)
        elif channel == "sms":
            await _send_sms(r.phone, title, body)
        elif channel == "push":
            await _send_push(conn, r.user_id, title, body)
        elif channel == "ntfy":
            await send_ntfy(r.ntfy_topic, title, body, level)
        return "sent", None
    except Exception as e:  # noqa: BLE001 - a failed channel must not stop the others
        log.warning("%s delivery to %s failed: %s", channel, r.user_id, e)
        return "failed", str(e)[:300]


# ---------------------------------------------------------------------------------------------------------------------
# distribution
# ---------------------------------------------------------------------------------------------------------------------
async def suppression_reason(conn, r: Recipient, level: str, incident_id: str | None, all_clear: bool = False) -> str | None:
    s = get_settings()
    if all_clear:
        return None                                                # an all-clear always reaches people who were warned
    if incident_id:
        prev = await conn.fetchrow(
            """select max(case level when 'CRITICAL' then 3 when 'WARNING' then 2 when 'WATCH' then 1 else 0 end) lvl, max(created_at) at
               from emergency_notifications where incident_id = $1 and recipient_id::text = $2 and notification_status <> 'suppressed'""",
            incident_id, r.user_id)
        if prev and prev["at"] is not None and LEVEL_RANK[level] <= (prev["lvl"] or 0):
            age_min = (datetime.now(timezone.utc) - prev["at"]).total_seconds() / 60
            if age_min < s.notify_cooldown_min or LEVEL_RANK[level] < (prev["lvl"] or 0):
                return "already notified about this incident at the same or a higher level"
    if level != "CRITICAL":
        n = await conn.fetchval("""select count(*) from emergency_notifications where recipient_id::text = $1 and notification_channel = 'in_app'
                                   and notification_status <> 'suppressed' and created_at > now() - interval '24 hours'""", r.user_id)
        if n >= s.notify_max_per_day:
            return f"daily limit of {s.notify_max_per_day} alerts reached"
    return None


async def distribute(conn, *, recipients: list[Recipient], level: str, title: str, body_for, allowed_channels: set[str],
                     incident_id: str | None = None, broadcast_id: str | None = None, all_clear: bool = False) -> dict:
    """Insert one row per recipient × channel and deliver. body_for(recipient) → text. Returns counts by status."""
    counts: dict[str, int] = {}
    for r in recipients:
        body = body_for(r)
        why = await suppression_reason(conn, r, level, incident_id, all_clear)
        for ch in resolve_channels(r, allowed_channels):
            # Record first (the unique index rejects duplicates), then deliver: a duplicate is never sent twice.
            nid = await conn.fetchval(
                """insert into emergency_notifications (incident_id, broadcast_id, recipient_id, notification_channel, notification_status,
                       level, title, body, distance_km, error)
                   values ($1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, $10) on conflict do nothing returning id""",
                incident_id, broadcast_id, r.user_id, ch, "suppressed" if why else "queued", level, title, body, r.distance_km, why)
            if nid is None:
                counts["duplicate_skipped"] = counts.get("duplicate_skipped", 0) + 1
                continue
            status = "suppressed"
            if not why:
                status, err = await deliver(conn, ch, r, title, body, level)
                await conn.execute("""update emergency_notifications set notification_status = $2, error = $3,
                                      sent_at = case when $2 in ('delivered', 'sent', 'simulated') then now() end where id = $1""",
                                   nid, status, err)
            counts[status] = counts.get(status, 0) + 1
    counts["recipients"] = len(recipients)
    return counts
