"""Visual disaster pipeline: store → analyse (CNN → evidence → agent → safety policy) → group into an incident with a
suggested message → (human approval) → location-aware distribution. Also area broadcasts composed by admins."""
import asyncio
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.db import audit, pool
from app.geo_nepal import nearest_district, place_label
from app.vision import context, notify, policy
from app.vision import state as S
from app.vision.classes import FLOOD_FAMILY, LABELS, disaster_type
from app.vision.imageio import hamming
from app.vision.infer import MODELS, ModelUnavailable

log = logging.getLogger(__name__)
LEVELS = ["NONE", "WATCH", "WARNING", "CRITICAL"]
RISK_OF = {"WATCH": "MODERATE", "WARNING": "HIGH", "CRITICAL": "SEVERE"}
_sem = asyncio.Semaphore(2)
_tasks: set[asyncio.Task] = set()


def _root() -> Path:
    p = Path(get_settings().visual_storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def store(data: bytes, preview: bytes, ext: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    rel = Path(f"{now:%Y}/{now:%m}")
    (_root() / rel).mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    orig, prev = rel / f"{name}.{ext}", rel / f"{name}_preview.jpg"
    (_root() / orig).write_bytes(data)
    (_root() / prev).write_bytes(preview)
    return str(orig), str(prev)


def file_path(ref: str) -> Path:
    p = (_root() / ref).resolve()
    if _root().resolve() not in p.parents:
        raise ValueError("bad image reference")
    return p


async def find_duplicate(conn, sha: str, dh: str) -> str | None:
    exact = await conn.fetchval("select id from visual_observations where sha256 = $1 order by created_at limit 1", sha)
    if exact:
        return str(exact)
    for r in await conn.fetch("select id, dhash from visual_observations where created_at > now() - interval '7 days' and duplicate_of is null"):
        if hamming(r["dhash"], dh) <= 4:
            return str(r["id"])
    return None


def _local(ts: datetime | None, offset_min: int | None) -> str | None:
    """ISO-8601 in the photo's own UTC offset when known (else UTC) — timezone information is always present."""
    if ts is None:
        return None
    return (ts.astimezone(timezone(timedelta(minutes=offset_min))) if offset_min is not None else ts).isoformat()


def public_observation(o, pred=None) -> dict:
    return {
        "image_id": str(o["id"]), "image_url": f"/api/v1/visual-disaster/observations/{o['id']}/image",
        "capture_timestamp": _local(o["capture_timestamp"], o["capture_tz_offset_min"]),
        "capture_time_source": o["capture_time_source"],
        "upload_timestamp": o["upload_timestamp"].isoformat(),
        "latitude": o["latitude"], "longitude": o["longitude"], "gps_accuracy_meters": o["gps_accuracy"],
        "location_source": o["location_source"], "image_source": o["image_source"],
        "user_id": str(o["user_id"]) if o["user_id"] else None, "processing_status": o["processing_status"],
        "error": o["error"], "duplicate_of": str(o["duplicate_of"]) if o["duplicate_of"] else None,
        "incident_id": str(o["incident_id"]) if o["incident_id"] else None,
        "exif": o["exif"], "width": o["width"], "height": o["height"],
        "analysis": public_prediction(o, pred) if pred else None,
    }


def public_prediction(o, p) -> dict:
    return {
        "classification": p["predicted_class"], "classification_label": LABELS.get(p["predicted_class"], p["predicted_class"]),
        "visual_confidence": round(p["visual_confidence"], 3), "class_probabilities": p["class_probabilities"],
        "risk_level": p["risk_level"], "alert_level": p["alert_level"], "recommended_action": p["policy_action"],
        "agent_action": p["dqn_action"], "location": {"latitude": o["latitude"], "longitude": o["longitude"]},
        "analysis_timestamp": p["inference_timestamp"].isoformat(), "weather_correlation": p["weather_correlation"],
        "alert_eligible": p["alert_eligible"], "evidence": p["evidence"], "reasons": p["reasons"], "model_version": p["model_version"],
    }


# ---------------------------------------------------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------------------------------------------------
def schedule(obs_id: str) -> None:
    t = asyncio.create_task(_run(obs_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _run(obs_id: str) -> None:
    async with _sem:
        try:
            await analyze(obs_id)
        except Exception as e:  # noqa: BLE001
            log.exception("analysis of %s failed", obs_id)
            await pool().execute("update visual_observations set processing_status = 'failed', error = $2 where id = $1", uuid.UUID(obs_id), str(e)[:300])


async def requeue_stuck() -> None:
    rows = await pool().fetch("select id from visual_observations where processing_status in ('queued', 'processing')")
    for r in rows:
        schedule(str(r["id"]))


async def analyze(obs_id: str) -> dict:
    oid = uuid.UUID(obs_id)
    async with pool().acquire() as conn:
        o = await conn.fetchrow("update visual_observations set processing_status = 'processing', error = null where id = $1 returning *", oid)
    img = Image.open(io.BytesIO(file_path(o["image_reference"]).read_bytes()))
    model_ok, cls, conf, probs, emb_proj = True, "uncertain", 0.0, None, None
    try:
        res = await asyncio.to_thread(MODELS.classify, img)
        cls, conf, probs, emb_proj = res["class"], res["confidence"], res["probs"], res["emb_proj"]
    except ModelUnavailable as e:
        model_ok = False
        log.warning("%s", e)
    now = datetime.now(timezone.utc)
    age_h, future_min = context.time_checks(o["capture_timestamp"], now)
    async with pool().acquire() as conn:
        facts, ctx = await context.gather(conn, oid, o["latitude"], o["longitude"], o["capture_timestamp"], o["user_id"])
        tz = await _tz(conn)
    ev = context.to_evidence(facts, ctx, o, age_h, future_min, model_ok)
    agent_action, q = None, None
    if model_ok:
        from zoneinfo import ZoneInfo
        local = (o["capture_timestamp"] or o["upload_timestamp"]).astimezone(ZoneInfo(tz))
        sctx = {**ctx, "hour": local.hour + local.minute / 60, "doy": local.timetuple().tm_yday, "manual": o["location_source"] == "manual",
                "accuracy_m": o["gps_accuracy"], "age_h": age_h if age_h is not None else 1.0,
                "alert": min(3, ctx["prior_level"]), "steps_since": 0}
        try:
            agent_action, q = MODELS.advise(S.build(probs, emb_proj, sctx))
        except ModelUnavailable:
            pass
    d = policy.evaluate(cls, conf, ev, agent_action, MODELS.dqn_validated)
    facts["reliability"] = {"age_hours": round(age_h, 2) if age_h is not None else None, "future_minutes": round(future_min, 1),
                            "capture_time_source": o["capture_time_source"], "location_source": o["location_source"],
                            "gps_accuracy_m": o["gps_accuracy"], "duplicate_of": ev.duplicate_of}
    facts["suggested_radius_km"] = d.radius_km
    facts["corroborated"] = d.corroborated
    facts["agent_mode"] = "active" if MODELS.dqn_validated else "advisory (not validated)"
    probs_d = {c: round(float(p), 4) for c, p in zip(MODELS.meta.get("classes", []), probs)} if probs is not None else {}
    async with pool().acquire() as conn, conn.transaction():
        p = await conn.fetchrow(
            """insert into ai_predictions (observation_id, predicted_class, class_probabilities, visual_confidence, dqn_action, dqn_q_values,
                   policy_action, risk_level, alert_level, alert_eligible, weather_correlation, evidence, reasons, model_version)
               values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) returning *""",
            oid, cls, probs_d, conf, agent_action, q, d.policy_action, d.risk_level, d.alert_level, d.eligible,
            d.weather_correlation, facts, d.reasons, MODELS.version)
        incident_id = None
        if d.eligible:
            incident_id = await group_incident(conn, o, cls, conf, d)
        status = "rejected" if ev.duplicate_of else "done"
        o = await conn.fetchrow("update visual_observations set processing_status = $2, incident_id = $3 where id = $1 returning *",
                                oid, status, incident_id)
        await audit(conn, "system:visual-ai", "visual.analyse", "visual_observation", obs_id,
                    {"class": cls, "confidence": round(conf, 3), "agent": agent_action, "policy": d.policy_action,
                     "level": d.alert_level, "eligible": d.eligible, "incident": str(incident_id) if incident_id else None,
                     "model": MODELS.version})
    return public_observation(o, p)


async def _exercise(conn) -> bool:
    prof = await conn.fetchrow("select policies, timezone from deployment_profile where id = 1")
    return bool((prof["policies"] or {}).get("exercise_mode", True)) if prof else True


async def _tz(conn) -> str:
    return await conn.fetchval("select timezone from deployment_profile where id = 1") or "UTC"


def _message(level: str, dtype: str, label: str, when: datetime, tz: str, exercise: bool) -> dict:
    body = notify.incident_body(level, RISK_OF[level], dtype, label, when, tz, None, exercise)
    body = body.replace("Source:", "Distance: {distance} from your saved location\nSource:", 1)
    return {"title": notify.incident_title(level, dtype), "body": body}


async def group_incident(conn, o, cls: str, conf: float, d: policy.Decision):
    """Attach to an open nearby incident of the same family, or propose a new one. Returns the incident id."""
    s = get_settings()
    family = ("flood",) if cls in FLOOD_FAMILY else ("landslide",)
    open_inc = await conn.fetch(
        """select * from disaster_incidents where incident_status in ('PROPOSED', 'ACTIVE')
             and last_updated_at > now() - make_interval(secs => $4 * 3600)
             and ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3 * 1000)
           order by geom::geography <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography""",
        o["latitude"], o["longitude"], s.visual_group_km, s.visual_group_hours)
    match = next((i for i in open_inc if (("landslide",) if i["disaster_type"] == "LANDSLIDE" else ("flood",)) == family), None)
    level = d.alert_level
    tz = await _tz(conn)
    when = o["capture_timestamp"] or o["upload_timestamp"]
    if match:
        new_sugg = max(match["suggested_level"], level, key=LEVELS.index)
        dtype = match["disaster_type"] if LEVELS.index(match["suggested_level"]) >= LEVELS.index(level) else disaster_type(cls)
        upd = {"suggested_level": new_sugg, "suggested_radius": max(match["suggested_radius"], d.radius_km)}
        if match["incident_status"] == "PROPOSED":                 # proposal follows the evidence until a person acts
            upd.update(alert_level=new_sugg, risk_level=RISK_OF[new_sugg], affected_radius=upd["suggested_radius"],
                       proposed_message=_message(new_sugg, dtype, match["location_label"], match["first_detected_at"], tz, match["exercise"]),
                       disaster_type=dtype)
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(upd))
        await conn.execute(f"""update disaster_incidents set {sets}, report_count = report_count + 1,
                               max_confidence = greatest(max_confidence, ${len(upd) + 2}), weather_correlation = ${len(upd) + 3},
                               last_updated_at = now() where id = $1""", match["id"], *upd.values(), conf, d.weather_correlation)
        await audit(conn, "system:visual-ai", "incident.update", "disaster_incident", str(match["id"]),
                    {"observation": str(o["id"]), "suggested_level": new_sugg,
                     "escalation_suggested": match["incident_status"] == "ACTIVE" and LEVELS.index(new_sugg) > LEVELS.index(match["alert_level"])})
        return match["id"]
    label = place_label(o["latitude"], o["longitude"])
    district, province, _ = nearest_district(o["latitude"], o["longitude"])
    exercise = await _exercise(conn)
    dtype = disaster_type(cls)
    iid = await conn.fetchval(
        """insert into disaster_incidents (disaster_type, latitude, longitude, geom, location_label, district, province, affected_radius,
               suggested_radius, risk_level, alert_level, suggested_level, max_confidence, weather_correlation, proposed_message, exercise,
               first_detected_at)
           values ($1, $2, $3, ST_SetSRID(ST_MakePoint($3, $2), 4326), $4, $5, $6, $7, $7, $8, $9, $9, $10, $11, $12, $13, $14) returning id""",
        dtype, o["latitude"], o["longitude"], label, district, province, float(d.radius_km), d.risk_level, level, conf,
        d.weather_correlation, _message(level, dtype, label, when, tz, exercise), exercise, when)
    await audit(conn, "system:visual-ai", "incident.propose", "disaster_incident", str(iid),
                {"observation": str(o["id"]), "type": dtype, "level": level, "radius_km": d.radius_km})
    return iid


# ---------------------------------------------------------------------------------------------------------------------
# approval and distribution
# ---------------------------------------------------------------------------------------------------------------------
async def send_incident(conn, inc, actor: str, level: str, radius_km: float, title: str, body: str, channels: set[str]) -> dict:
    recips = await notify.recipients_near(conn, inc["latitude"], inc["longitude"], radius_km)

    def body_for(r: notify.Recipient) -> str:
        dist = f"{r.distance_km:.1f} km" if r.distance_km is not None else "unknown"
        return body.replace("{distance}", dist)
    counts = await notify.distribute(conn, recipients=recips, level=level, title=title, body_for=body_for,
                                     allowed_channels=channels, incident_id=inc["id"])
    await audit(conn, actor, "incident.notify", "disaster_incident", str(inc["id"]),
                {"level": level, "radius_km": radius_km, "channels": sorted(channels), "result": counts})
    return counts


def area_body(message: str, level: str, exercise: bool, valid_until: datetime | None, tz: str) -> str:
    lines = ["[EXERCISE — this is a test, not a real event]"] if exercise else []
    lines.append(message.strip())
    if valid_until:
        from zoneinfo import ZoneInfo
        lines.append(f"Valid until: {valid_until.astimezone(ZoneInfo(tz)).strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("Issued by an authorised operator of this early-warning system. This is not an official government "
                 "emergency announcement unless stated by the authority.")
    return "\n".join(lines)


async def send_broadcast(bid) -> dict:
    async with pool().acquire() as conn, conn.transaction():
        b = await conn.fetchrow("update area_broadcasts set status = 'SENDING' where id = $1 and status = 'SCHEDULED' returning *, "
                                "ST_Y(center) clat, ST_X(center) clon", bid)
        if b is None:
            return {"skipped": "not scheduled"}
    try:
        async with pool().acquire() as conn, conn.transaction():
            recips = await notify.recipients_for_target(conn, b["target_type"], b["target_value"], b["clat"], b["clon"], b["radius_km"])
            tz = await _tz(conn)
            body = area_body(b["message"], b["level"], b["exercise"], b["valid_until"], tz)
            lvl = b["level"] if b["level"] != "INFO" else "INFO"
            counts = await notify.distribute(conn, recipients=recips, level=lvl, title=b["title"], body_for=lambda r: body,
                                             allowed_channels=set(notify.CHANNELS), broadcast_id=b["id"], all_clear=b["all_clear"])
            await conn.execute("update area_broadcasts set status = 'SENT', sent_at = now(), recipients = $2 where id = $1", b["id"], len(recips))
            await audit(conn, b["created_by"], "broadcast.send", "area_broadcast", str(b["id"]), {"result": counts})
        return counts
    except Exception as e:
        log.exception("broadcast %s failed", bid)
        await pool().execute("update area_broadcasts set status = 'FAILED', error = $2 where id = $1", bid, str(e)[:300])
        raise


async def send_due_broadcasts() -> None:
    for r in await pool().fetch("select id from area_broadcasts where status = 'SCHEDULED' and send_at <= now() order by send_at"):
        try:
            await send_broadcast(r["id"])
        except Exception:  # noqa: BLE001 - recorded on the row
            pass


# ---------------------------------------------------------------------------------------------------------------------
# approved warnings -> residents
# ---------------------------------------------------------------------------------------------------------------------
WARNING_RADIUS_KM = {"WATCH": 5.0, "WARNING": 10.0, "CRITICAL": 15.0}


async def queue_warning_broadcast(conn, w, actor: str, all_clear: bool = False, reason: str | None = None):
    """Inside the approve/cancel transaction: record the area message for an activated warning (or its all-clear).
    The caller sends it with send_broadcast() after the transaction commits. Returns the message id, or None when
    there is nothing to send (an all-clear for a warning that never reached anyone)."""
    from app.warnings.templates import TEMPLATES
    st = await conn.fetchrow("select name, ST_Y(geom) lat, ST_X(geom) lon from stations where id = $1", w["station_id"])
    if st is None:
        return None
    place = st["name"]
    if all_clear:
        prev = await conn.fetchrow("""select radius_km from area_broadcasts where warning_id = $1 and not all_clear and status = 'SENT'
                                      order by sent_at desc limit 1""", w["id"])
        if prev is None:
            return None
        level, radius, title = "INFO", prev["radius_km"], f"ALL CLEAR — {place}"[:120]
        message = (f"The {w['level']} flood warning for {place} has been cancelled. The danger has passed; stay careful near "
                   f"rivers and follow local officials." + (f" Reason: {reason}" if reason else "") +
                   f"\nबाढी चेतावनी रद्द गरिएको छ – {place}: खतरा टरेको छ। नदी नजिक सावधान रहनुहोस्।")
        valid_until = datetime.now(timezone.utc) + timedelta(hours=6)
    else:
        level, radius = w["level"], WARNING_RADIUS_KM.get(w["level"], 10.0)
        title = {"WATCH": "FLOOD WATCH", "WARNING": "FLOOD WARNING", "CRITICAL": "EVACUATE NOW"}.get(level, level) + f" — {place}"
        message = TEMPLATES[level]["en"].format(place=place) + "\n" + TEMPLATES[level]["ne"].format(place=place)
        valid_until = w["valid_until"]
    bid = await conn.fetchval(
        """insert into area_broadcasts (target_type, center, radius_km, level, title, message, send_at, valid_until, status, exercise,
               created_by, source, area_label, warning_id, all_clear, reviewed_by, reviewed_at)
           values ('point', ST_SetSRID(ST_MakePoint($2, $1), 4326), $3, $4, $5, $6, now(), $7, 'SCHEDULED', $8, $9, 'warning', $10, $11,
               $12, $9, now()) returning id""",
        st["lat"], st["lon"], radius, level, title[:120], message[:2000], valid_until, w["exercise"], actor, place, w["id"], all_clear)
    await audit(conn, actor, "warning.notify_residents", "area_broadcast", str(bid),
                {"warning": str(w["id"]), "level": level, "radius_km": radius, "all_clear": all_clear})
    return bid
