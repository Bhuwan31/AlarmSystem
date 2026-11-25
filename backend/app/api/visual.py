"""AI visual disaster detection API: photo observations, analysis, incidents (review, approve & send, escalate,
close), personal alert inbox and subscription, area broadcasts, model status.

Roles: any signed-in account can submit photos, manage its alert subscription and read its own alerts.
operator+ can see all observations and incidents. approver+ (admins) review, approve/send, broadcast and close.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.auth import RANK, User, current_user, require
from app.config import get_settings
from app.db import audit, pool
from app.geo_nepal import (CITIES, DISTRICTS, areas, canonical_city, canonical_district, canonical_province, nearest_district,
                           place_label)
from app.vision import imageio, notify, service
from app.vision.infer import MODELS
from app.vision.policy import RADII

router = APIRouter(prefix="/api/v1/visual-disaster", tags=["visual disaster detection"])
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _uuid(v: str) -> uuid.UUID:
    try:
        return uuid.UUID(v)
    except ValueError as e:
        raise HTTPException(404, "not found") from e


def _is_staff(user: User) -> bool:
    return RANK[user.role] >= RANK["operator"]


def _check_coords(lat: float | None, lon: float | None) -> None:
    if lat is None or lon is None:
        return
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        raise HTTPException(422, "invalid coordinates")


def _parse_ts(v: str | None, name: str) -> datetime | None:
    if not v:
        return None
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(422, f"{name} must be ISO-8601") from e
    if t.tzinfo is None:
        raise HTTPException(422, f"{name} must include a timezone offset")
    return t


# =====================================================================================================================
# observations
# =====================================================================================================================
@router.post("/observations", status_code=201)
async def create_observation(
    file: UploadFile = File(...),
    image_source: str = Form(..., pattern="^(camera|upload)$"),
    capture_timestamp: str | None = Form(None, description="camera: device clock at capture, ISO-8601 with offset"),
    client_tz_offset_min: int | None = Form(None, ge=-840, le=840, description="uploader's UTC offset, used only when EXIF time has no offset"),
    latitude: float | None = Form(None), longitude: float | None = Form(None),
    gps_accuracy_m: float | None = Form(None, ge=0, le=100000),
    location_source: str | None = Form(None, pattern="^(device_gps|manual)$"),
    user: User = Depends(current_user),
):
    """Store a photo privately, extract EXIF time/GPS and check for duplicates. Analysis starts with POST /analyze
    after the user has confirmed the location."""
    s = get_settings()
    _check_coords(latitude, longitude)
    data = await file.read(s.visual_max_upload_mb * 1024 * 1024 + 1)
    async with pool().acquire() as conn:
        n = await conn.fetchval("select count(*) from visual_observations where user_id::text = $1 and created_at > now() - interval '1 hour'", user.id)
        if n >= s.visual_uploads_per_hour:
            raise HTTPException(429, f"upload limit of {s.visual_uploads_per_hour} photos per hour reached")
    tz = timezone(timedelta(minutes=client_tz_offset_min)) if client_tz_offset_min is not None else None
    try:
        img, info = imageio.inspect(data, s.visual_max_upload_mb * 1024 * 1024, tz)
    except imageio.ImageRejected as e:
        raise HTTPException(422, str(e)) from e
    now = datetime.now(timezone.utc)
    if image_source == "camera":
        cap, cap_src = _parse_ts(capture_timestamp, "capture_timestamp"), "device_clock"
        if cap is None:
            cap_src = "unknown"
        lat, lon, acc, loc_src = latitude, longitude, gps_accuracy_m, (location_source if latitude is not None else None)
    else:
        # Upload: never assume upload time = capture time, and never use the device's current GPS as the photo's place.
        cap, cap_src = info.capture_time, info.capture_time_source
        if info.gps:
            lat, lon, acc, loc_src = info.gps[0], info.gps[1], info.gps_accuracy_m, "exif"
        elif latitude is not None and location_source == "manual":
            lat, lon, acc, loc_src = latitude, longitude, None, "manual"
        else:
            lat = lon = acc = loc_src = None
    async with pool().acquire() as conn, conn.transaction():
        dup = await service.find_duplicate(conn, info.sha256, info.dhash)
        orig, prev = service.store(data, imageio.preview_jpeg(img), EXT[info.mime])
        o = await conn.fetchrow(
            """insert into visual_observations (user_id, image_reference, preview_reference, sha256, dhash, mime_type, width, height, bytes,
                   capture_timestamp, capture_time_source, upload_timestamp, latitude, longitude, geom, gps_accuracy, location_source,
                   image_source, exif, duplicate_of, processing_status, capture_tz_offset_min)
               values ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                       case when $13::float8 is null then null else ST_SetSRID(ST_MakePoint($14, $13), 4326) end,
                       $15, $16, $17, $18, $19, $20, $21) returning *""",
            user.id, orig, prev, info.sha256, info.dhash, info.mime, info.width, info.height, info.bytes, cap, cap_src, now,
            lat, lon, acc, loc_src, image_source, info.exif, uuid.UUID(dup) if dup else None,
            "received" if lat is not None else "awaiting_location",
            int(cap.utcoffset().total_seconds() // 60) if cap is not None and cap.utcoffset() is not None else None)
        await audit(conn, user.id, "visual.submit", "visual_observation", str(o["id"]),
                    {"image_source": image_source, "capture_time_source": cap_src, "location_source": loc_src, "duplicate_of": dup})
    out = service.public_observation(o)
    out["suggested_location"] = None if lat is None else {"label": place_label(lat, lon), "district": nearest_district(lat, lon)[0]}
    return out


class AnalyzeBody(BaseModel):
    observation_id: str
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    location_source: str | None = Field(None, pattern="^(device_gps|exif|manual)$")
    gps_accuracy_m: float | None = Field(None, ge=0, le=100000)


@router.post("/analyze", status_code=202)
async def analyze(body: AnalyzeBody, user: User = Depends(current_user)):
    """Confirm (or correct) the location and queue the AI analysis. Poll GET /observations/{id} for the result."""
    oid = _uuid(body.observation_id)
    _check_coords(body.latitude, body.longitude)
    async with pool().acquire() as conn, conn.transaction():
        o = await conn.fetchrow("select * from visual_observations where id = $1 for update", oid)
        if o is None or (str(o["user_id"]) != user.id and not _is_staff(user)):
            raise HTTPException(404, "observation not found")
        if o["processing_status"] in ("queued", "processing"):
            raise HTTPException(409, "analysis already running")
        lat, lon, src, acc = o["latitude"], o["longitude"], o["location_source"], o["gps_accuracy"]
        if body.latitude is not None and body.longitude is not None:
            moved = lat is None or abs(body.latitude - lat) > 1e-5 or abs(body.longitude - lon) > 1e-5
            if moved:
                lat, lon = body.latitude, body.longitude
                src = "manual" if (body.location_source in (None, "manual") or o["image_source"] == "upload" and body.location_source != "exif") else body.location_source
                acc = body.gps_accuracy_m if src != "manual" else None
        if lat is None:
            raise HTTPException(422, "location required: allow GPS or pick the place on the map")
        o = await conn.fetchrow(
            """update visual_observations set latitude = $2, longitude = $3, geom = ST_SetSRID(ST_MakePoint($3, $2), 4326), location_source = $4,
                   gps_accuracy = $5, processing_status = 'queued', error = null where id = $1 returning *""", oid, lat, lon, src, acc)
        await audit(conn, user.id, "visual.analyse_requested", "visual_observation", str(oid), {"location_source": src})
    service.schedule(str(oid))
    return service.public_observation(o)


async def _with_pred(conn, o):
    p = await conn.fetchrow("select * from ai_predictions where observation_id = $1 order by inference_timestamp desc limit 1", o["id"])
    return service.public_observation(o, p)


@router.get("/observations")
async def list_observations(limit: int = Query(50, ge=1, le=500), mine: bool = False, status: str | None = None,
                            user: User = Depends(current_user)):
    cond, args = [], []
    if mine or not _is_staff(user):
        args.append(user.id)
        cond.append(f"user_id::text = ${len(args)}")
    if status:
        args.append(status)
        cond.append(f"processing_status = ${len(args)}")
    where = ("where " + " and ".join(cond)) if cond else ""
    async with pool().acquire() as conn:
        rows = await conn.fetch(f"select * from visual_observations {where} order by created_at desc limit {limit}", *args)
        return [await _with_pred(conn, o) for o in rows]


@router.get("/observations/{oid}")
async def get_observation(oid: str, user: User = Depends(current_user)):
    async with pool().acquire() as conn:
        o = await conn.fetchrow("select * from visual_observations where id = $1", _uuid(oid))
        if o is None or (str(o["user_id"]) != user.id and not _is_staff(user)):
            raise HTTPException(404, "observation not found")
        return await _with_pred(conn, o)


@router.get("/observations/{oid}/image")
async def observation_image(oid: str, user: User = Depends(current_user)):
    """The reviewer copy: re-encoded JPEG without EXIF/GPS. The original file is never served."""
    o = await pool().fetchrow("select user_id, preview_reference from visual_observations where id = $1", _uuid(oid))
    if o is None or (str(o["user_id"]) != user.id and not _is_staff(user)):
        raise HTTPException(404, "observation not found")
    return Response(service.file_path(o["preview_reference"]).read_bytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


# =====================================================================================================================
# incidents
# =====================================================================================================================
def _incident(i, extra: dict | None = None) -> dict:
    d = {k: i[k] for k in ("disaster_type", "incident_status", "latitude", "longitude", "location_label", "district", "province",
                           "affected_radius", "suggested_radius", "risk_level", "alert_level", "suggested_level", "report_count",
                           "max_confidence", "weather_correlation", "proposed_message", "sent_message", "verification_status",
                           "verified_by", "approved_by", "closed_by", "close_note", "exercise")}
    for k in ("first_detected_at", "last_updated_at", "verified_at", "approved_at", "closed_at"):
        d[k] = i[k].isoformat() if i[k] else None
    d["id"] = str(i["id"])
    lv = ["WATCH", "WARNING", "CRITICAL"]
    d["escalation_suggested"] = i["incident_status"] == "ACTIVE" and lv.index(i["suggested_level"]) > lv.index(i["alert_level"])
    return {**d, **(extra or {})}


@router.get("/incidents/active")
async def active_incidents():
    """Public: approved, active incidents for the map (no photos, no reporter data)."""
    rows = await pool().fetch("select * from disaster_incidents where incident_status = 'ACTIVE' order by approved_at desc")
    return [{"id": str(i["id"]), "disaster_type": i["disaster_type"], "alert_level": i["alert_level"], "risk_level": i["risk_level"],
             "latitude": i["latitude"], "longitude": i["longitude"], "affected_radius": i["affected_radius"],
             "location_label": i["location_label"], "approved_at": i["approved_at"].isoformat() if i["approved_at"] else None,
             "exercise": i["exercise"], "source": "AI-assisted visual observation, approved by an operator"} for i in rows]


@router.get("/incidents")
async def list_incidents(status: str | None = Query(None, pattern="^(PROPOSED|ACTIVE|CLOSED|REJECTED)$"),
                         limit: int = Query(100, ge=1, le=500), user: User = Depends(require("operator"))):
    rows = await pool().fetch(
        f"""select i.*, (select count(*) from emergency_notifications n where n.incident_id = i.id and n.notification_channel = 'in_app'
                         and n.notification_status in ('delivered', 'sent', 'simulated')) notified,
                   (select count(*) from alert_subscriptions s where s.consent and s.opted_out_at is null and s.home is not null
                         and ST_DWithin(s.home::geography, i.geom::geography, i.affected_radius * 1000)) in_radius
            from disaster_incidents i {"where incident_status = $1" if status else ""}
            order by case incident_status when 'PROPOSED' then 0 when 'ACTIVE' then 1 else 2 end, last_updated_at desc limit {limit}""",
        *([status] if status else []))
    return [_incident(i, {"notified": i["notified"], "users_in_radius": i["in_radius"]}) for i in rows]


async def _load_incident(conn, iid: str, lock: bool = False):
    i = await conn.fetchrow(f"select * from disaster_incidents where id = $1 {'for update' if lock else ''}", _uuid(iid))
    if i is None:
        raise HTTPException(404, "incident not found")
    return i


@router.get("/incidents/{iid}")
async def get_incident(iid: str, user: User = Depends(require("operator"))):
    async with pool().acquire() as conn:
        i = await _load_incident(conn, iid)
        obs = await conn.fetch("select * from visual_observations where incident_id = $1 order by created_at", i["id"])
        observations = [await _with_pred(conn, o) for o in obs]
        radius_counts = {}
        for r in RADII:                                       # how many subscribers each radius option would reach
            radius_counts[str(r)] = len(await notify.recipients_near(conn, i["latitude"], i["longitude"], float(r)))
        stats = await conn.fetch("""select notification_channel, notification_status, level, count(*) n from emergency_notifications
                                    where incident_id = $1 group by 1, 2, 3 order by 1, 2""", i["id"])
        history = await conn.fetch("""select at, actor, action, payload from audit_log where entity = 'disaster_incident' and entity_id = $1
                                      order by id""", iid)
    return _incident(i, {"observations": observations, "users_by_radius": radius_counts,
                         "delivery_summary": [dict(r) for r in stats],
                         "history": [{"at": h["at"].isoformat(), "actor": h["actor"], "action": h["action"], "payload": h["payload"]} for h in history],
                         "channels_configured": {c: notify.configured(c) for c in notify.CHANNELS},
                         "external_sending_enabled": get_settings().notify_external_enabled})


class VerifyBody(BaseModel):
    decision: str = Field(pattern="^(confirm|reject)$")
    note: str = Field("", max_length=500)


@router.post("/incidents/{iid}/verify")
async def verify_incident(iid: str, body: VerifyBody, user: User = Depends(require("approver"))):
    async with pool().acquire() as conn, conn.transaction():
        i = await _load_incident(conn, iid, lock=True)
        if body.decision == "reject":
            if i["incident_status"] != "PROPOSED":
                raise HTTPException(409, "only a proposed incident can be rejected; close an active one instead")
            await conn.execute("""update disaster_incidents set incident_status = 'REJECTED', verification_status = 'rejected', verified_by = $2,
                                  verified_at = now(), close_note = $3, last_updated_at = now() where id = $1""", i["id"], user.id, body.note)
        else:
            await conn.execute("""update disaster_incidents set verification_status = 'confirmed', verified_by = $2, verified_at = now(),
                                  last_updated_at = now() where id = $1""", i["id"], user.id)
        await audit(conn, user.id, f"incident.{body.decision}", "disaster_incident", iid, {"note": body.note})
        return _incident(await _load_incident(conn, iid))


class SendBody(BaseModel):
    level: str = Field(pattern="^(WATCH|WARNING|CRITICAL)$")
    radius_km: int
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=2000)
    channels: list[str] = Field(default_factory=lambda: list(notify.CHANNELS))

    @field_validator("radius_km")
    @classmethod
    def _radius(cls, v: int) -> int:
        if v not in RADII:
            raise ValueError(f"radius must be one of {RADII} km")
        return v


@router.post("/incidents/{iid}/approve-send")
async def approve_send(iid: str, body: SendBody, user: User = Depends(require("approver"))):
    """Human approval: confirm the incident, set level/radius/message, and notify subscribers inside the radius."""
    if body.level == "CRITICAL" and not user.mfa:
        raise HTTPException(403, "multi-factor authentication required to send a CRITICAL alert")
    channels = set(body.channels) & set(notify.CHANNELS)
    if "in_app" not in channels:
        channels.add("in_app")
    async with pool().acquire() as conn, conn.transaction():
        i = await _load_incident(conn, iid, lock=True)
        if i["incident_status"] not in ("PROPOSED", "ACTIVE"):
            raise HTTPException(409, f"incident is {i['incident_status']}")
        risk = {"WATCH": "MODERATE", "WARNING": "HIGH", "CRITICAL": "SEVERE"}[body.level]
        await conn.execute(
            """update disaster_incidents set incident_status = 'ACTIVE', verification_status = 'confirmed', verified_by = coalesce(verified_by, $2),
                   verified_at = coalesce(verified_at, now()), approved_by = $2, approved_at = coalesce(approved_at, now()), alert_level = $3,
                   risk_level = $4, affected_radius = $5, sent_message = $6, last_updated_at = now() where id = $1""",
            i["id"], user.id, body.level, risk, float(body.radius_km), {"title": body.title, "body": body.body})
        await audit(conn, user.id, "incident.approve", "disaster_incident", iid,
                    {"level": body.level, "radius_km": body.radius_km, "title": body.title, "previous_status": i["incident_status"]})
        i = await _load_incident(conn, iid)
        counts = await service.send_incident(conn, i, user.id, body.level, float(body.radius_km), body.title, body.body, channels)
    return {"incident": _incident(i), "delivery": counts}


class LevelBody(BaseModel):
    level: str = Field(pattern="^(WATCH|WARNING|CRITICAL)$")
    note: str = Field(min_length=3, max_length=500)


@router.post("/incidents/{iid}/level")
async def change_level(iid: str, body: LevelBody, user: User = Depends(require("approver"))):
    """Escalate or downgrade. For an ACTIVE incident an escalation must be sent with approve-send (the message changes)."""
    if body.level == "CRITICAL" and not user.mfa:
        raise HTTPException(403, "multi-factor authentication required for CRITICAL")
    async with pool().acquire() as conn, conn.transaction():
        i = await _load_incident(conn, iid, lock=True)
        if i["incident_status"] not in ("PROPOSED", "ACTIVE"):
            raise HTTPException(409, f"incident is {i['incident_status']}")
        risk = {"WATCH": "MODERATE", "WARNING": "HIGH", "CRITICAL": "SEVERE"}[body.level]
        if i["incident_status"] == "PROPOSED":
            msg = service._message(body.level, i["disaster_type"], i["location_label"], i["first_detected_at"],
                                   await service._tz(conn), i["exercise"])
            await conn.execute("""update disaster_incidents set alert_level = $2, suggested_level = $2, risk_level = $3, proposed_message = $4,
                                  last_updated_at = now() where id = $1""", i["id"], body.level, risk, msg)
        else:
            await conn.execute("update disaster_incidents set alert_level = $2, risk_level = $3, last_updated_at = now() where id = $1",
                               i["id"], body.level, risk)
        await audit(conn, user.id, "incident.level", "disaster_incident", iid, {"from": i["alert_level"], "to": body.level, "note": body.note})
        return _incident(await _load_incident(conn, iid))


class CloseBody(BaseModel):
    note: str = Field(min_length=3, max_length=500)
    send_all_clear: bool = False


@router.post("/incidents/{iid}/close")
async def close_incident(iid: str, body: CloseBody, user: User = Depends(require("approver"))):
    async with pool().acquire() as conn, conn.transaction():
        i = await _load_incident(conn, iid, lock=True)
        if i["incident_status"] in ("CLOSED", "REJECTED"):
            raise HTTPException(409, f"incident is already {i['incident_status']}")
        await conn.execute("""update disaster_incidents set incident_status = 'CLOSED', closed_by = $2, closed_at = now(), close_note = $3,
                              last_updated_at = now() where id = $1""", i["id"], user.id, body.note)
        await audit(conn, user.id, "incident.close", "disaster_incident", iid, {"note": body.note, "all_clear": body.send_all_clear})
        counts = None
        if body.send_all_clear and i["incident_status"] == "ACTIVE":
            recips = await notify.recipients_notified(conn, i["id"])
            text = (("[EXERCISE] " if i["exercise"] else "") + f"ALL CLEAR — the {i['disaster_type'].replace('_', ' ').lower()} alert for "
                    f"{i['location_label']} has ended. {body.note}\nStay careful near rivers and damaged roads.")
            counts = await notify.distribute(conn, recipients=recips, level="INFO", title="ALL CLEAR", body_for=lambda r: text,
                                             allowed_channels=set(notify.CHANNELS), incident_id=i["id"], all_clear=True)
        return {"incident": _incident(await _load_incident(conn, iid)), "all_clear": counts}


@router.get("/incidents/{iid}/notifications")
async def incident_notifications(iid: str, user: User = Depends(require("approver"))):
    rows = await pool().fetch(
        """select n.id, n.recipient_id, u.name, n.notification_channel, n.notification_status, n.level, n.distance_km, n.error,
                  n.created_at, n.sent_at, n.read_at, n.acknowledged_at
           from emergency_notifications n join users u on u.id = n.recipient_id where n.incident_id = $1 order by n.created_at, u.name""",
        _uuid(iid))
    return [{**{k: r[k] for k in ("notification_channel", "notification_status", "level", "distance_km", "error", "name")},
             "id": str(r["id"]), "recipient_id": str(r["recipient_id"]),
             **{k: (r[k].isoformat() if r[k] else None) for k in ("created_at", "sent_at", "read_at", "acknowledged_at")}} for r in rows]


# =====================================================================================================================
# my alerts and subscription
# =====================================================================================================================
@router.get("/alerts")
async def my_alerts(limit: int = Query(50, ge=1, le=200), user: User = Depends(current_user)):
    rows = await pool().fetch(
        """select n.*, i.latitude ilat, i.longitude ilon, i.affected_radius, i.disaster_type, b.target_type, b.target_value
           from emergency_notifications n left join disaster_incidents i on i.id = n.incident_id
           left join area_broadcasts b on b.id = n.broadcast_id
           where n.recipient_id::text = $1 and n.notification_channel = 'in_app' and n.notification_status <> 'suppressed'
           order by n.created_at desc limit $2""", user.id, limit)
    return [{"id": str(r["id"]), "kind": "incident" if r["incident_id"] else "broadcast",
             "incident_id": str(r["incident_id"]) if r["incident_id"] else None, "level": r["level"], "title": r["title"], "body": r["body"],
             "distance_km": r["distance_km"], "created_at": r["created_at"].isoformat(),
             "read_at": r["read_at"].isoformat() if r["read_at"] else None,
             "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
             "latitude": r["ilat"], "longitude": r["ilon"], "radius_km": r["affected_radius"], "disaster_type": r["disaster_type"],
             "target": {"type": r["target_type"], "value": r["target_value"]} if r["target_type"] else None} for r in rows]


@router.get("/alerts/unread")
async def unread(user: User = Depends(current_user)):
    n = await pool().fetchval("""select count(*) from emergency_notifications where recipient_id::text = $1 and notification_channel = 'in_app'
                                 and notification_status <> 'suppressed' and read_at is null""", user.id)
    return {"unread": n}


@router.post("/alerts/{nid}/ack")
async def ack(nid: str, user: User = Depends(current_user)):
    async with pool().acquire() as conn:
        r = await conn.fetchrow("""update emergency_notifications set acknowledged_at = coalesce(acknowledged_at, now()), read_at = coalesce(read_at, now())
                                   where id = $1 and recipient_id::text = $2 returning incident_id, broadcast_id""", _uuid(nid), user.id)
        if r is None:
            raise HTTPException(404, "alert not found")
        # acknowledging the in-app copy acknowledges the same alert on every channel
        await conn.execute("""update emergency_notifications set acknowledged_at = coalesce(acknowledged_at, now()) where recipient_id::text = $1
                              and incident_id is not distinct from $2 and broadcast_id is not distinct from $3""", user.id, r["incident_id"], r["broadcast_id"])
    return {"acknowledged": True}


@router.post("/alerts/read-all")
async def read_all(user: User = Depends(current_user)):
    await pool().execute("update emergency_notifications set read_at = now() where recipient_id::text = $1 and read_at is null", user.id)
    return {"ok": True}


@router.get("/alerts/all")
async def all_alerts(limit: int = Query(200, ge=1, le=1000), user: User = Depends(require("approver"))):
    rows = await pool().fetch(
        """select coalesce(n.incident_id::text, n.broadcast_id::text) ref, case when n.incident_id is null then 'broadcast' else 'incident' end kind,
                  n.level, n.title, n.notification_channel, n.notification_status, count(*) n, min(n.created_at) first_at,
                  count(n.acknowledged_at) acknowledged
           from emergency_notifications n group by 1, 2, 3, 4, 5, 6 order by first_at desc limit $1""", limit)
    return [{**{k: r[k] for k in ("ref", "kind", "level", "title", "notification_channel", "notification_status", "n", "acknowledged")},
             "first_at": r["first_at"].isoformat()} for r in rows]


class SubscriptionBody(BaseModel):
    consent: bool
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    home_label: str | None = Field(None, max_length=120)
    district: str | None = None
    province: str | None = None
    channels: dict[str, bool] = Field(default_factory=lambda: {"in_app": True})
    phone: str | None = Field(None, pattern=r"^\+?[0-9 ]{7,20}$")
    email: str | None = Field(None, max_length=200)


def _sub(r) -> dict:
    if r is None:
        return {"subscribed": False, "consent": False}
    return {"subscribed": bool(r["consent"] and r["opted_out_at"] is None), "consent": r["consent"],
            "consent_at": r["consent_at"].isoformat() if r["consent_at"] else None,
            "opted_out_at": r["opted_out_at"].isoformat() if r["opted_out_at"] else None,
            "latitude": r["lat"], "longitude": r["lon"], "home_label": r["home_label"], "district": r["district"],
            "province": r["province"], "channels": r["channels"], "phone": r["phone"], "email": r["email"]}


@router.get("/subscription")
async def get_subscription(user: User = Depends(current_user)):
    r = await pool().fetchrow("select *, ST_Y(home) lat, ST_X(home) lon from alert_subscriptions where user_id::text = $1", user.id)
    return _sub(r)


@router.put("/subscription")
async def put_subscription(body: SubscriptionBody, user: User = Depends(current_user)):
    if not body.consent:
        raise HTTPException(422, "consent is required to receive location-based alerts (use DELETE to opt out)")
    if body.latitude is None or body.longitude is None:
        raise HTTPException(422, "a home location is required for location-based alerts")
    _check_coords(body.latitude, body.longitude)
    district = canonical_district(body.district) if body.district else nearest_district(body.latitude, body.longitude)[0]
    if district is None:
        raise HTTPException(422, f"unknown district {body.district!r}")
    province = canonical_province(body.province) if body.province else DISTRICTS[district][0]
    channels = {c: bool(body.channels.get(c)) for c in notify.CHANNELS}
    channels["in_app"] = True
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            """insert into alert_subscriptions (user_id, consent, consent_at, opted_out_at, home, home_label, district, province, channels, phone, email, updated_at)
               values ($1::uuid, true, now(), null, ST_SetSRID(ST_MakePoint($3, $2), 4326), $4, $5, $6, $7, $8, $9, now())
               on conflict (user_id) do update set consent = true, consent_at = coalesce(alert_subscriptions.consent_at, now()), opted_out_at = null,
                   home = excluded.home, home_label = excluded.home_label, district = excluded.district, province = excluded.province,
                   channels = excluded.channels, phone = excluded.phone, email = excluded.email, updated_at = now()""",
            user.id, body.latitude, body.longitude, body.home_label or place_label(body.latitude, body.longitude), district, province,
            channels, body.phone, body.email)
        await audit(conn, user.id, "subscription.update", "user", user.id, {"district": district, "channels": channels})
        r = await conn.fetchrow("select *, ST_Y(home) lat, ST_X(home) lon from alert_subscriptions where user_id::text = $1", user.id)
    return _sub(r)


@router.delete("/subscription")
async def opt_out(user: User = Depends(current_user)):
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("""update alert_subscriptions set consent = false, opted_out_at = now(), home = null, phone = null, updated_at = now()
                              where user_id::text = $1""", user.id)
        await audit(conn, user.id, "subscription.opt_out", "user", user.id, {})
    return {"subscribed": False, "note": "Opted out. Your saved home location and phone number were deleted."}


class PushBody(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: dict[str, str]


@router.get("/channels")
async def channels():
    """Which delivery channels this server can use (in-app always; others need provider settings)."""
    return {"configured": {c: notify.configured(c) for c in notify.CHANNELS},
            "external_sending_enabled": get_settings().notify_external_enabled}


@router.get("/push/public-key")
async def push_key():
    s = get_settings()
    return {"configured": notify.configured("push"), "public_key": s.vapid_public_key or None}


@router.post("/push/subscribe")
async def push_subscribe(body: PushBody, user: User = Depends(current_user)):
    if not body.endpoint.startswith("https://") or "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(422, "invalid push subscription")
    await pool().execute("""insert into push_subscriptions (user_id, endpoint, p256dh, auth) values ($1::uuid, $2, $3, $4)
                            on conflict (endpoint) do update set user_id = excluded.user_id""",
                         user.id, body.endpoint, body.keys["p256dh"], body.keys["auth"])
    return {"ok": True}


# =====================================================================================================================
# area broadcasts (admin-composed messages)
# =====================================================================================================================
class BroadcastBody(BaseModel):
    target_type: str = Field(pattern="^(country|province|district|city|point)$")
    target_value: str | None = Field(None, max_length=80)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    radius_km: float | None = Field(None, gt=0, le=200)
    level: str = Field(pattern="^(INFO|WATCH|WARNING|CRITICAL)$")
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=2000)
    send_at: str | None = None
    valid_until: str | None = None


def _target(b: BroadcastBody) -> tuple[str | None, float | None, float | None, float | None]:
    if b.target_type == "country":
        return None, None, None, None
    if b.target_type == "province":
        v = canonical_province(b.target_value)
        if not v:
            raise HTTPException(422, "unknown province")
        return v, None, None, None
    if b.target_type == "district":
        v = canonical_district(b.target_value)
        if not v:
            raise HTTPException(422, "unknown district")
        return v, None, None, None
    if b.target_type == "city":
        v = canonical_city(b.target_value)
        if not v:
            raise HTTPException(422, "unknown city")
        _, la, lo, r = CITIES[v]
        return v, la, lo, b.radius_km or r
    if b.latitude is None or b.longitude is None or not b.radius_km:
        raise HTTPException(422, "a point target needs latitude, longitude and radius_km")
    _check_coords(b.latitude, b.longitude)
    return None, b.latitude, b.longitude, b.radius_km


@router.post("/broadcasts/preview")
async def preview_broadcast(body: BroadcastBody, user: User = Depends(require("approver"))):
    value, la, lo, r = _target(body)
    async with pool().acquire() as conn:
        rec = await notify.recipients_for_target(conn, body.target_type, value, la, lo, r)
    return {"recipients": len(rec), "target_value": value, "latitude": la, "longitude": lo, "radius_km": r}


@router.post("/broadcasts", status_code=201)
async def create_broadcast(body: BroadcastBody, user: User = Depends(require("approver"))):
    if body.level == "CRITICAL" and not user.mfa:
        raise HTTPException(403, "multi-factor authentication required for a CRITICAL broadcast")
    value, la, lo, r = _target(body)
    now = datetime.now(timezone.utc)
    send_at = _parse_ts(body.send_at, "send_at") or now
    valid_until = _parse_ts(body.valid_until, "valid_until")
    if send_at < now - timedelta(minutes=5):
        raise HTTPException(422, "send_at is in the past")
    if valid_until and valid_until <= send_at:
        raise HTTPException(422, "valid_until must be after send_at")
    async with pool().acquire() as conn, conn.transaction():
        exercise = await service._exercise(conn)
        b = await conn.fetchrow(
            """insert into area_broadcasts (target_type, target_value, center, radius_km, level, title, message, send_at, valid_until, exercise, created_by)
               values ($1, $2, case when $3::float8 is null then null else ST_SetSRID(ST_MakePoint($4, $3), 4326) end, $5, $6, $7, $8, $9, $10, $11, $12)
               returning id""", body.target_type, value, la, lo, r, body.level, body.title, body.message, send_at, valid_until, exercise, user.id)
        await audit(conn, user.id, "broadcast.create", "area_broadcast", str(b["id"]),
                    {"target": body.target_type, "value": value, "radius_km": r, "level": body.level, "send_at": send_at.isoformat()})
    result = None
    if send_at <= now + timedelta(seconds=30):
        result = await service.send_broadcast(b["id"])
    return {"id": str(b["id"]), "status": "SENT" if result else "SCHEDULED", "delivery": result, "send_at": send_at.isoformat()}


_BCAST_FIELDS = ("target_type", "target_value", "radius_km", "level", "title", "message", "status", "exercise", "recipients",
                 "created_by", "error", "lat", "lon", "source", "area_label", "hazard", "ai_reason", "original_level",
                 "original_title", "original_message", "original_radius_km", "reviewed_by", "review_note", "cancelled_by")
_BCAST_TIMES = ("send_at", "valid_until", "created_at", "sent_at", "reviewed_at", "updated_at")


def _bcast(b) -> dict:
    out = {"id": str(b["id"]), **{k: b[k] for k in _BCAST_FIELDS}, **{k: (b[k].isoformat() if b[k] else None) for k in _BCAST_TIMES}}
    out["ai_analysis_id"] = str(b["ai_analysis_id"]) if b["ai_analysis_id"] else None
    names = {"reviewed_by": "reviewer_name", "created_by": "creator_name", "cancelled_by": "canceller_name"}
    for k, n in names.items():                       # show people's names, not account ids ("ai_analyst" stays as is)
        if n in b.keys() and b[n]:
            out[k] = b[n]
    if out["created_by"] == "ai_analyst":
        out["created_by"] = "AI analyst"
    out["edited"] = b["source"] == "ai_analyst" and (b["message"] != b["original_message"] or b["title"] != b["original_title"]
                                                    or b["level"] != b["original_level"] or b["radius_km"] != b["original_radius_km"])
    return out


@router.get("/broadcasts")
async def list_broadcasts(limit: int = Query(100, ge=1, le=500),
                          status: str | None = Query(None, pattern="^(PROPOSED|SCHEDULED|SENDING|SENT|CANCELLED|FAILED|REJECTED)$"),
                          user: User = Depends(require("approver"))):
    rows = await pool().fetch(
        """select b.*, ST_Y(b.center) lat, ST_X(b.center) lon, ru.name reviewer_name, cu.name creator_name, xu.name canceller_name
           from area_broadcasts b left join users ru on ru.id::text = b.reviewed_by left join users cu on cu.id::text = b.created_by
                left join users xu on xu.id::text = b.cancelled_by
           where ($2::text is null or b.status = $2) order by coalesce(b.updated_at, b.created_at) desc limit $1""", limit, status)
    return [_bcast(b) for b in rows]


@router.get("/broadcasts/pending")
async def pending_broadcasts(user: User = Depends(require("approver"))):
    """AI-drafted messages waiting for a decision: polled by every approver screen for the banner and alert sound."""
    rows = await pool().fetch(
        """select id, level, title, area_label, hazard, coalesce(updated_at, created_at) at from area_broadcasts
           where status = 'PROPOSED' order by case level when 'CRITICAL' then 0 when 'WARNING' then 1 else 2 end, created_at desc limit 20""")
    return {"count": len(rows), "items": [{"id": str(r["id"]), "level": r["level"], "title": r["title"], "area_label": r["area_label"],
                                           "hazard": r["hazard"], "at": r["at"].isoformat()} for r in rows]}


class DraftEdit(BaseModel):
    level: str | None = Field(None, pattern="^(INFO|WATCH|WARNING|CRITICAL)$")
    title: str | None = Field(None, min_length=3, max_length=120)
    message: str | None = Field(None, min_length=10, max_length=2000)
    radius_km: float | None = Field(None, gt=0, le=200)


class DraftSend(DraftEdit):
    send_at: str | None = None
    valid_until: str | None = None


class DraftReject(BaseModel):
    note: str | None = Field(None, max_length=500)


async def _apply_edit(conn, bid, body: DraftEdit, statuses: tuple[str, ...]):
    b = await conn.fetchrow("select * from area_broadcasts where id = $1 for update", bid)
    if b is None:
        raise HTTPException(404, "message not found")
    if b["status"] not in statuses:
        raise HTTPException(409, f"message is {b['status'].lower()}")
    if b["target_type"] != "point" and body.radius_km is not None:
        raise HTTPException(422, "only a map-point message has a radius")
    return await conn.fetchrow(
        """update area_broadcasts set level = coalesce($2, level), title = coalesce($3, title), message = coalesce($4, message),
             radius_km = coalesce($5, radius_km), updated_at = now() where id = $1 returning *""",
        bid, body.level, body.title, body.message, body.radius_km)


@router.patch("/broadcasts/{bid}")
async def edit_broadcast(bid: str, body: DraftEdit, user: User = Depends(require("approver"))):
    """Save changes to a draft (waiting or rejected) without sending it."""
    async with pool().acquire() as conn, conn.transaction():
        b = await _apply_edit(conn, _uuid(bid), body, ("PROPOSED", "REJECTED"))
        await audit(conn, user.id, "broadcast.edit", "area_broadcast", bid, body.model_dump(exclude_none=True))
    return {"id": bid, "status": b["status"]}


@router.post("/broadcasts/{bid}/approve")
async def approve_broadcast(bid: str, body: DraftSend, user: User = Depends(require("approver"))):
    """Approve a draft (waiting or previously rejected) with any edits, and send it now or at send_at."""
    now = datetime.now(timezone.utc)
    send_at = _parse_ts(body.send_at, "send_at") or now
    if send_at < now - timedelta(minutes=5):
        raise HTTPException(422, "send_at is in the past")
    valid_until = _parse_ts(body.valid_until, "valid_until") or send_at + timedelta(hours=12)
    if valid_until <= send_at:
        raise HTTPException(422, "valid_until must be after send_at")
    async with pool().acquire() as conn, conn.transaction():
        b = await _apply_edit(conn, _uuid(bid), body, ("PROPOSED", "REJECTED"))
        if b["level"] == "CRITICAL" and not user.mfa:
            raise HTTPException(403, "multi-factor authentication required for a CRITICAL message")
        exercise = await service._exercise(conn)
        await conn.execute(
            """update area_broadcasts set status = 'SCHEDULED', send_at = $2, valid_until = $3, exercise = $4, reviewed_by = $5,
                 reviewed_at = now() where id = $1""", b["id"], send_at, valid_until, exercise, user.id)
        await audit(conn, user.id, "broadcast.approve", "area_broadcast", bid,
                    {"level": b["level"], "radius_km": b["radius_km"], "send_at": send_at.isoformat(), "was": b["status"],
                     "edited": b["message"] != b["original_message"] or b["title"] != b["original_title"]})
    result = None
    if send_at <= now + timedelta(seconds=30):
        result = await service.send_broadcast(_uuid(bid))
    return {"id": bid, "status": "SENT" if result else "SCHEDULED", "delivery": result, "send_at": send_at.isoformat()}


@router.post("/broadcasts/{bid}/reject")
async def reject_broadcast(bid: str, body: DraftReject, user: User = Depends(require("approver"))):
    """Reject a draft. It stays in the history (with who, when and why) and can still be edited and sent later."""
    async with pool().acquire() as conn, conn.transaction():
        r = await conn.fetchval(
            """update area_broadcasts set status = 'REJECTED', reviewed_by = $2, reviewed_at = now(), review_note = $3, updated_at = now()
               where id = $1 and status = 'PROPOSED' returning id""", _uuid(bid), user.id, body.note)
        if r is None:
            raise HTTPException(409, "only a waiting draft can be rejected")
        await audit(conn, user.id, "broadcast.reject", "area_broadcast", bid, {"note": body.note})
    return {"id": bid, "status": "REJECTED"}


@router.post("/broadcasts/{bid}/cancel")
async def cancel_broadcast(bid: str, user: User = Depends(require("approver"))):
    async with pool().acquire() as conn, conn.transaction():
        r = await conn.fetchval("update area_broadcasts set status = 'CANCELLED', cancelled_by = $2 where id = $1 and status = 'SCHEDULED' returning id",
                                _uuid(bid), user.id)
        if r is None:
            raise HTTPException(409, "only a scheduled broadcast can be cancelled")
        await audit(conn, user.id, "broadcast.cancel", "area_broadcast", bid, {})
    return {"id": bid, "status": "CANCELLED"}


# =====================================================================================================================
# reference data and model status
# =====================================================================================================================
@router.get("/geo/areas")
async def geo_areas():
    return areas()


@router.get("/geo/locate")
async def geo_locate(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    d, p, km = nearest_district(lat, lon)
    return {"label": place_label(lat, lon), "district": d, "province": p, "km_to_district_hq": round(km, 1)}


@router.get("/model/status")
async def model_status():
    MODELS.load()
    m = MODELS.meta
    runs = await pool().fetch("""select model_name, model_version, dataset_version, validated_for_alerts, created_at,
                                        test_metrics from model_training_runs order by created_at desc limit 10""")
    out = {"available": MODELS.cnn is not None, "model_version": MODELS.version,
           "classes": m.get("classes"), "actions": m.get("actions"), "img_size": m.get("img_size"),
           "cnn": m.get("cnn"), "dqn": m.get("dqn"), "dataset": {k: m.get("dataset", {}).get(k) for k in ("version", "images", "synthetic_only", "counts")} if m else None,
           "trained_at": m.get("created_at"), "error": m.get("error"),
           "safety": "The models only propose. Every alert is reviewed and approved by an authorised person before it is sent; "
                     "an image alone cannot establish current rainfall; CRITICAL needs independent corroboration.",
           "runs": [{"model_name": r["model_name"], "model_version": r["model_version"], "dataset_version": r["dataset_version"],
                     "validated_for_alerts": r["validated_for_alerts"], "created_at": r["created_at"].isoformat(),
                     "headline": {k: r["test_metrics"].get(k) for k in ("macro_f1", "accuracy", "flood_or_landslide_recall")} if r["model_name"] == "visual_cnn"
                     else {k: (r["test_metrics"].get("agent") or {}).get(k) for k in ("events_detected", "missed_events", "false_alarm_rate_quiet", "mean_reward")}}
                    for r in runs]}
    try:
        import json as _json
        met = _json.loads((MODELS.art / "vision_metrics.json").read_text(encoding="utf-8"))
        out["metrics"] = {"cnn_test": {k: met["cnn"]["test"][k] for k in ("accuracy", "macro_f1", "ece", "flood_or_landslide_recall",
                                                                           "flood_or_landslide_precision", "per_class", "confusion_matrix",
                                                                           "accuracy_by_condition")},
                          "cnn_validation": {k: met["cnn"]["validation"][k] for k in ("accuracy", "macro_f1")},
                          "agent_test": met["dqn"]["test"], "learning_curve": met["dqn"]["learning_curve"], "cnn_history": met["cnn"]["history"]}
    except (OSError, KeyError, ValueError):
        out["metrics"] = None
    return out
