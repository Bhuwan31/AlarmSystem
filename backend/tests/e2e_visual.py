"""End-to-end test of photo → AI → policy → incident → approval → location-aware notifications, against the RUNNING
stack, with SIMULATED users only (emails end in @sim.amhews.test). Everything it creates is deleted at the end.

    docker compose --profile ml run --rm ml-train python -m tests.e2e_visual            # API at http://backend:8000

Needs DATABASE_URL and JWT_SECRET (from .env) to create the simulated accounts and sign their tokens, and a prepared
visual dataset (ml_data/vision/datasets/*) for test photos the model has never seen.
"""
import asyncio
import csv
import io
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx
from PIL import Image

from app.geo_nepal import haversine_km
from app.security import hash_password, mint_token
from app.vision.imageio import exif_bytes_for_test

API = os.environ.get("E2E_API", "http://backend:8000") + "/api/v1"
NPT = timezone(timedelta(hours=5, minutes=45))
SITE = (27.6950, 85.3070)                                  # Kathmandu, near the Bagmati at Teku
TAG = "@sim.amhews.test"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}", flush=True)


def offset(lat: float, lon: float, km_north: float, km_east: float = 0.0) -> tuple[float, float]:
    import math
    return lat + km_north / 111.32, lon + km_east / (111.32 * math.cos(math.radians(lat)))


def test_photos(n: int = 6) -> list[Path]:
    base = Path("ml_data/vision/datasets")
    ds = sorted(base.glob("*/manifest.csv"), key=lambda p: p.stat().st_mtime)
    if not ds:
        sys.exit("no prepared dataset: run python -m app.vision.train_all first")
    with open(ds[-1], newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test" and r["label"] in ("urban_flooding", "river_flooding")]
    rows.sort(key=lambda r: (r["label"] != "urban_flooding", r["path"]))
    return [Path(r["path"]) for r in rows[:n]]


def jpeg_with_exif(path: Path, lat: float, lon: float, when: datetime) -> bytes:
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, "JPEG", quality=92, exif=exif_bytes_for_test(lat, lon, when, accuracy_m=8))
    return buf.getvalue()


async def make_user(conn, name: str, role: str) -> tuple[str, dict]:
    uid = await conn.fetchval("insert into users (email, name, role, password_hash) values ($1, $2, $3, $4) returning id::text",
                              f"{name.lower().replace(' ', '.')}.{uuid.uuid4().hex[:6]}{TAG}", name, role, hash_password(uuid.uuid4().hex))
    return uid, {"Authorization": f"Bearer {mint_token(uid, name, role, False)}"}


async def cleanup() -> None:
    """Delete every simulated user (…@sim.amhews.test) and the photos, incidents, broadcasts and alerts they produced."""
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        ids = [r["id"] for r in await db.fetch(f"select id from users where email like '%{TAG}'")]
        incs = [r["incident_id"] for r in await db.fetch(
            "select distinct incident_id from visual_observations where user_id = any($1::uuid[]) and incident_id is not null", ids)]
        await db.execute("update visual_observations set incident_id = null where incident_id = any($1::uuid[])", incs)
        await db.execute("delete from disaster_incidents where id = any($1::uuid[])", incs)
        await db.execute("delete from area_broadcasts where created_by = any($1::text[])", [str(i) for i in ids])
        refs = await db.fetch("select image_reference, preview_reference from visual_observations where user_id = any($1::uuid[])", ids)
        await db.execute("delete from visual_observations where user_id = any($1::uuid[])", ids)
        await db.execute("delete from users where id = any($1::uuid[])", ids)
    finally:
        await db.close()
    removed = 0
    from app.vision.service import file_path
    for r in refs:
        for ref in (r["image_reference"], r["preview_reference"]):
            try:
                file_path(ref).unlink()
                removed += 1
            except (OSError, ValueError):
                pass
    print(f"cleaned up {len(ids)} simulated users, {len(incs)} incidents, {len(refs)} photos ({removed} files)")


KEEP = "--keep" in sys.argv


async def main() -> None:
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    created_obs: list[str] = []
    incident_id = None
    broadcast_ids: list[str] = []
    try:
        reporter, H_rep = await make_user(db, "Sim Reporter", "viewer")
        reporter2, H_rep2 = await make_user(db, "Sim Reporter Two", "viewer")
        approver, H_app = await make_user(db, "Sim Approver", "approver")
        H_app_mfa = {"Authorization": f"Bearer {mint_token(approver, 'Sim Approver', 'approver', True)}"}
        # residents at known distances from the site (km north / east)
        layout = {"A 0.5km": (0.5, 0, "Kathmandu", True), "B 2.5km": (0, 2.5, "Kathmandu", True), "C 4km": (-4, 0, "Lalitpur", True),
                  "D 8km": (8, 0, "Kathmandu", True), "E Chitwan": None, "F 0.8km no consent": (0.8, 0, "Kathmandu", False)}
        res: dict[str, tuple[str, dict, tuple]] = {}
        async with httpx.AsyncClient(timeout=60) as c:
            for name, spec in layout.items():
                uid, h = await make_user(db, f"Sim Resident {name}", "viewer")
                if spec is None:
                    lat, lon, district, consent = 27.683, 84.435, "Chitwan", True
                else:
                    lat, lon = offset(*SITE, spec[0], spec[1])
                    district, consent = spec[2], spec[3]
                res[name] = (uid, h, (lat, lon))
                if consent:
                    r = await c.put(f"{API}/visual-disaster/subscription", headers=h, json={
                        "consent": True, "latitude": lat, "longitude": lon, "district": district,
                        "channels": {"in_app": True, "sms": True, "email": True}, "phone": "+977 9800000000"})
                    check(f"subscribe {name}", r.status_code == 200 and r.json()["subscribed"], r.text[:120] if r.status_code != 200 else "")
            r = await c.put(f"{API}/visual-disaster/subscription", headers=res["F 0.8km no consent"][1],
                            json={"consent": False, "latitude": SITE[0], "longitude": SITE[1]})
            check("subscription without consent is refused", r.status_code == 422)

            # ---- 1. upload a photo with EXIF time + GPS ------------------------------------------------------------
            photos = test_photos()
            now = datetime.now(NPT)
            o = None
            for p in photos:
                data = jpeg_with_exif(p, *SITE, now - timedelta(minutes=12))
                r = await c.post(f"{API}/visual-disaster/observations", headers=H_rep, data={"image_source": "upload", "client_tz_offset_min": "345"},
                                 files={"file": ("flood.jpg", data, "image/jpeg")})
                assert r.status_code == 201, r.text
                o = r.json()
                created_obs.append(o["image_id"])
                check("EXIF GPS extracted", o["location_source"] == "exif" and abs(o["latitude"] - SITE[0]) < 1e-4, f"{o['latitude']},{o['longitude']}")
                check("EXIF capture time with timezone", o["capture_time_source"] == "exif" and o["capture_timestamp"].endswith("+05:45"), o["capture_timestamp"])
                check("upload time recorded separately", o["upload_timestamp"] != o["capture_timestamp"])
                r = await c.post(f"{API}/visual-disaster/analyze", headers=H_rep, json={"observation_id": o["image_id"]})
                check("analysis queued (202)", r.status_code == 202)
                t0 = time.time()
                while time.time() - t0 < 120:
                    o = (await c.get(f"{API}/visual-disaster/observations/{o['image_id']}", headers=H_rep)).json()
                    if o["processing_status"] in ("done", "failed", "rejected"):
                        break
                    await asyncio.sleep(1)
                a = o["analysis"]
                print(f"      photo {p.name}: {a['classification']} {a['visual_confidence']:.2f} agent={a['agent_action']} "
                      f"policy={a['recommended_action']} level={a['alert_level']} weather={a['weather_correlation']} eligible={a['alert_eligible']}")
                check("CNN + agent + policy produced a result", o["processing_status"] == "done" and a["agent_action"] in
                      ("NO_ALERT", "MONITOR", "ISSUE_WATCH", "ISSUE_WARNING", "ISSUE_CRITICAL_ALERT", "REQUEST_ADDITIONAL_EVIDENCE"))
                if a["alert_eligible"]:
                    break
            check("a flood photo became an alert proposal", o and o["analysis"]["alert_eligible"] and o["incident_id"],
                  "" if o and o["incident_id"] else "model did not flag any test photo")
            if not (o and o["incident_id"]):
                return
            incident_id = o["incident_id"]
            ev = o["analysis"]["evidence"]
            check("weather / river data looked up for the photo's place and time", any(ev.get(k) for k in ("gauges", "model", "river")),
                  f"gauges={ev.get('gauges')} model={ev.get('model')} river={ev.get('river')}")
            check("weather never fabricated", o["analysis"]["weather_correlation"] in ("confirmed", "contradicted", "inconclusive", "supported_by_model", "unavailable"))

            # ---- 2. duplicate submission ---------------------------------------------------------------------------
            r = await c.post(f"{API}/visual-disaster/observations", headers=H_rep2, data={"image_source": "upload"},
                             files={"file": ("same.jpg", data, "image/jpeg")})
            dup = r.json()
            created_obs.append(dup["image_id"])
            check("duplicate photo detected", dup["duplicate_of"] is not None)

            # ---- 3. second report from the camera (device GPS + device clock) joins the incident ----------------------
            cam = io.BytesIO()
            Image.open(photos[-1]).convert("RGB").transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(cam, "JPEG")
            lat2, lon2 = offset(*SITE, 0.3, 0.2)
            r = await c.post(f"{API}/visual-disaster/observations", headers=H_rep2, files={"file": ("camera.jpg", cam.getvalue(), "image/jpeg")},
                             data={"image_source": "camera", "capture_timestamp": datetime.now(NPT).isoformat(), "latitude": str(lat2),
                                   "longitude": str(lon2), "gps_accuracy_m": "12", "location_source": "device_gps"})
            o2 = r.json()
            created_obs.append(o2["image_id"])
            check("camera photo keeps device GPS and clock", o2["location_source"] == "device_gps" and o2["capture_time_source"] == "device_clock"
                  and o2["gps_accuracy_meters"] == 12)
            await c.post(f"{API}/visual-disaster/analyze", headers=H_rep2, json={"observation_id": o2["image_id"]})
            for _ in range(120):
                o2 = (await c.get(f"{API}/visual-disaster/observations/{o2['image_id']}", headers=H_rep2)).json()
                if o2["processing_status"] in ("done", "failed", "rejected"):
                    break
                await asyncio.sleep(1)
            a2 = o2["analysis"]
            print(f"      camera photo: {a2['classification']} {a2['visual_confidence']:.2f} level={a2['alert_level']} eligible={a2['alert_eligible']}")
            if a2["alert_eligible"]:
                check("nearby report grouped into the same incident", o2["incident_id"] == incident_id)

            # ---- 4. reporters cannot see incidents; approver reviews the proposal ------------------------------------
            check("viewer cannot list incidents", (await c.get(f"{API}/visual-disaster/incidents", headers=H_rep)).status_code == 403)
            inc = (await c.get(f"{API}/visual-disaster/incidents/{incident_id}", headers=H_app)).json()
            check("incident PROPOSED, not sent", inc["incident_status"] == "PROPOSED" and inc["sent_message"] is None)
            check("suggested message present", "{distance}" in inc["proposed_message"]["body"] and "not an official government" in inc["proposed_message"]["body"])
            print(f"      proposal: {inc['alert_level']} {inc['disaster_type']} radius {inc['suggested_radius']} km, users by radius {inc['users_by_radius']}")
            nothing = await db.fetchval("select count(*) from emergency_notifications where incident_id = $1", uuid.UUID(incident_id))
            check("no notification before approval", nothing == 0)

            # ---- 5. approve & send at 3 km ----------------------------------------------------------------------------
            level = inc["alert_level"] if inc["alert_level"] != "CRITICAL" else "WARNING"
            r = await c.post(f"{API}/visual-disaster/incidents/{incident_id}/approve-send", headers=H_app, json={
                "level": level, "radius_km": 3, "title": inc["proposed_message"]["title"], "body": inc["proposed_message"]["body"],
                "channels": ["in_app", "sms", "email", "push"]})
            check("approve & send", r.status_code == 200, r.text[:200])
            print(f"      delivery: {r.json().get('delivery')}")
            got = {row["recipient_id"]: row for row in await db.fetch(
                "select recipient_id::text, body, distance_km from emergency_notifications where incident_id = $1 and notification_channel = 'in_app'",
                uuid.UUID(incident_id))}
            inside = {n for n, (uid, _, (la, lo)) in res.items() if haversine_km(la, lo, *SITE) <= 3 and n != "F 0.8km no consent"}
            check("residents inside 3 km notified", all(res[n][0] in got for n in inside), f"inside={sorted(inside)}")
            check("residents outside 3 km not notified", not any(res[n][0] in got for n in ("C 4km", "D 8km", "E Chitwan")))
            check("no notification without consent", res["F 0.8km no consent"][0] not in got)
            a_row = got.get(res["A 0.5km"][0])
            check("distance filled in per recipient", a_row is not None and "Distance: 0.5 km" in a_row["body"] and "{distance}" not in a_row["body"],
                  a_row["body"].split("\n")[4] if a_row else "")
            ch = dict(await db.fetch("""select notification_channel, notification_status from emergency_notifications
                                        where incident_id = $1 and recipient_id::text = $2""", uuid.UUID(incident_id), res["A 0.5km"][0]))
            check("unconfigured SMS / e-mail / push recorded, not faked", all(ch.get(k) in ("skipped_unconfigured", "simulated") for k in ("sms", "email")), str(ch))

            # ---- 6. dedup: sending again does not notify twice ---------------------------------------------------------
            n_before = await db.fetchval("select count(*) from emergency_notifications where incident_id = $1", uuid.UUID(incident_id))
            r = await c.post(f"{API}/visual-disaster/incidents/{incident_id}/approve-send", headers=H_app, json={
                "level": level, "radius_km": 3, "title": "again", "body": inc["proposed_message"]["body"]})
            n_after = await db.fetchval("select count(*) from emergency_notifications where incident_id = $1", uuid.UUID(incident_id))
            check("duplicate alert suppressed", r.status_code == 200 and n_after == n_before, str(r.json().get("delivery")))

            # ---- 7. CRITICAL needs MFA; escalation reaches people again --------------------------------------------------
            body = {"level": "CRITICAL", "radius_km": 3, "title": "CRITICAL FLOOD ALERT", "body": inc["proposed_message"]["body"]}
            check("CRITICAL without MFA refused", (await c.post(f"{API}/visual-disaster/incidents/{incident_id}/approve-send", headers=H_app, json=body)).status_code == 403)
            r = await c.post(f"{API}/visual-disaster/incidents/{incident_id}/approve-send", headers=H_app_mfa, json=body)
            crit = await db.fetchval("""select count(*) from emergency_notifications where incident_id = $1 and level = 'CRITICAL'
                                        and notification_channel = 'in_app' and notification_status = 'delivered'""", uuid.UUID(incident_id))
            check("escalation to CRITICAL delivered", r.status_code == 200 and crit == len(inside), f"{crit} delivered")

            # ---- 8. resident inbox + acknowledgement -----------------------------------------------------------------
            inbox = (await c.get(f"{API}/visual-disaster/alerts", headers=res["A 0.5km"][1])).json()
            check("resident sees alerts in inbox", len(inbox) >= 2 and inbox[0]["level"] == "CRITICAL")
            r = await c.post(f"{API}/visual-disaster/alerts/{inbox[0]['id']}/ack", headers=res["A 0.5km"][1])
            ack = await db.fetchval("select count(*) from emergency_notifications where incident_id = $1 and recipient_id::text = $2 and acknowledged_at is not null",
                                    uuid.UUID(incident_id), res["A 0.5km"][0])
            check("acknowledgement recorded", r.status_code == 200 and ack > 0)

            # ---- 9. admin area message: district now, point scheduled ----------------------------------------------
            r = await c.post(f"{API}/visual-disaster/broadcasts/preview", headers=H_app, json={
                "target_type": "district", "target_value": "Kathmandu", "level": "WATCH", "title": "Test", "message": "Simulated district message."})
            exp = sum(1 for n, s in layout.items() if s and s[2] == "Kathmandu" and s[3])
            check("district recipient count", r.json()["recipients"] >= exp, str(r.json()))
            r = await c.post(f"{API}/visual-disaster/broadcasts", headers=H_app, json={
                "target_type": "district", "target_value": "Kathmandu", "level": "WATCH", "title": "E2E district message",
                "message": "Simulated message to Kathmandu district (end-to-end test).", "valid_until": (datetime.now(NPT) + timedelta(hours=2)).isoformat()})
            b = r.json()
            broadcast_ids.append(b["id"])
            got_b = {x["recipient_id"] for x in await db.fetch("select recipient_id::text from emergency_notifications where broadcast_id = $1", uuid.UUID(b["id"]))}
            check("district broadcast sent to the district only", b["status"] == "SENT" and res["A 0.5km"][0] in got_b and res["E Chitwan"][0] not in got_b
                  and res["C 4km"][0] not in got_b)
            r = await c.post(f"{API}/visual-disaster/broadcasts", headers=H_app, json={
                "target_type": "point", "latitude": SITE[0], "longitude": SITE[1], "radius_km": 1, "level": "INFO", "title": "E2E scheduled",
                "message": "Simulated scheduled message (end-to-end test).", "send_at": (datetime.now(NPT) + timedelta(seconds=50)).isoformat()})
            sb = r.json()
            broadcast_ids.append(sb["id"])
            check("broadcast scheduled", sb["status"] == "SCHEDULED")
            for _ in range(36):
                st = await db.fetchval("select status from area_broadcasts where id = $1", uuid.UUID(sb["id"]))
                if st == "SENT":
                    break
                await asyncio.sleep(5)
            n_sched = await db.fetchval("select count(*) from emergency_notifications where broadcast_id = $1 and notification_channel = 'in_app'", uuid.UUID(sb["id"]))
            check("scheduled broadcast sent by the scheduler", st == "SENT" and n_sched == 1, f"status={st}, recipients={n_sched}")

            # ---- 10. close with all-clear; opt-out ------------------------------------------------------------------
            r = await c.post(f"{API}/visual-disaster/incidents/{incident_id}/close", headers=H_app, json={"note": "Water receded (simulation).", "send_all_clear": True})
            ac = await db.fetchval("""select count(*) from emergency_notifications where incident_id = $1 and level = 'INFO' and notification_channel = 'in_app'""",
                                   uuid.UUID(incident_id))
            check("closed with all-clear to those warned", r.status_code == 200 and ac == len(inside), f"{ac} all-clear")
            r = await c.delete(f"{API}/visual-disaster/subscription", headers=res["B 2.5km"][1])
            home = await db.fetchval("select home is null and not consent from alert_subscriptions where user_id::text = $1", res["B 2.5km"][0])
            check("opt-out deletes location and stops alerts", r.status_code == 200 and home)
            hist = await db.fetchval("select count(*) from audit_log where entity = 'disaster_incident' and entity_id = $1", incident_id)
            check("audit trail recorded", hist >= 5, f"{hist} entries")
    finally:
        await db.close()
        if KEEP:
            print("--keep: simulated data left in place; remove it with: python -m tests.e2e_visual --cleanup")
        else:
            await cleanup()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(cleanup() if "--cleanup" in sys.argv else main())
