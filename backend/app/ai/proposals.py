"""Turn the AI analyst's findings into draft area messages for approvers (status PROPOSED).

Nothing here sends anything: a draft only reaches people after an approver presses Send. One draft per risk area and
hazard: a new finding within DEDUP_KM of a waiting draft updates it (if the approver has not edited it yet) instead of
adding another, so the queue does not fill with repeats every analysis run."""
import logging

from app.db import audit
from app.geo_nepal import place_label

log = logging.getLogger(__name__)

RADIUS_KM = {"WATCH": 5.0, "WARNING": 10.0, "CRITICAL": 15.0}
RANK = {"WATCH": 1, "WARNING": 2, "CRITICAL": 3}
PUBLIC_HAZARDS = {"flood", "heavy_rain", "heat", "wind", "cold", "other"}     # data_gap is for operators, not the public
DEDUP_KM = 10.0
HAZARD_NAME = {"flood": "Flood", "heavy_rain": "Heavy rain", "heat": "Extreme heat", "wind": "Strong wind",
               "cold": "Extreme cold", "other": "Hazard"}
ADVICE = {
    "flood": {"WATCH": "Stay away from river banks and low-lying areas, keep an emergency bag ready and follow updates.",
              "WARNING": "Avoid rivers, streams and flooded roads. Move people, animals and valuables to higher ground and be ready to evacuate.",
              "CRITICAL": "Move to higher ground or a safe shelter NOW. Do not walk or drive through flood water. Follow instructions from police and local officials."},
    "heavy_rain": {"WATCH": "Heavy rain is possible. Avoid steep slopes and river crossings and keep updated.",
                   "WARNING": "Heavy rain may cause flooding and landslides. Avoid travel near rivers and steep slopes.",
                   "CRITICAL": "Very heavy rain is causing danger. Move away from rivers and unstable slopes now."},
    "heat": {"WATCH": "Drink water often and avoid hard work in the midday sun.",
             "WARNING": "Stay in the shade, drink water often and check on elderly people and children.",
             "CRITICAL": "Dangerous heat. Stay indoors or in shade during the day and seek help for anyone feeling unwell."},
}
GENERIC = {"WATCH": "Stay alert and follow updates from local authorities.",
           "WARNING": "Take precautions now and be ready to act on instructions from local authorities.",
           "CRITICAL": "Act now to protect yourself and follow instructions from police and local officials."}


def compose(f: dict) -> tuple[str, str]:
    """Title and resident-facing message. Uses the AI's own public message when it wrote one."""
    level, hazard, area = f["severity"], f.get("hazard", "other"), f.get("area") or "your area"
    title = f"{level} — {HAZARD_NAME.get(hazard, 'Hazard')} — {area}"[:120]
    text = (f.get("public_message") or "").strip()
    if len(text) < 20:
        advice = ADVICE.get(hazard, GENERIC).get(level, GENERIC[level])
        text = f"{HAZARD_NAME.get(hazard, 'Hazard')} risk in and around {area}. {f.get('summary', '').strip()} {advice}"
    return title, text.strip()[:2000]


async def propose(conn, run_id, findings: list[dict], exercise: bool) -> int:
    """Create or refresh drafts for WATCH+ public-hazard findings. Returns the number of new drafts."""
    created = 0
    for f in findings:
        level, hazard = f.get("severity"), f.get("hazard")
        lat, lon = f.get("lat"), f.get("lon")
        if level not in RADIUS_KM or hazard not in PUBLIC_HAZARDS or lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        title, message = compose(f)
        radius = RADIUS_KM[level]
        reason = {k: f.get(k) for k in ("summary", "evidence", "confidence", "recommended_action", "station_ids")}
        label = f.get("area") or place_label(lat, lon)
        existing = await conn.fetchrow(
            """select id, level, message, original_message from area_broadcasts
               where status = 'PROPOSED' and source = 'ai_analyst' and hazard = $1
                 and ST_DWithin(center::geography, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, $4 * 1000)
               order by created_at desc limit 1""", hazard, lat, lon, DEDUP_KM)
        if existing:
            untouched = existing["message"] == existing["original_message"]
            if untouched and RANK[level] >= RANK.get(existing["level"], 0):
                await conn.execute(
                    """update area_broadcasts set level = $2, title = $3, message = $4, radius_km = $5, original_level = $2,
                         original_title = $3, original_message = $4, original_radius_km = $5, ai_reason = $6, ai_analysis_id = $7,
                         area_label = $8, updated_at = now() where id = $1""",
                    existing["id"], level, title, message, radius, reason, run_id, label)
            else:
                await conn.execute("update area_broadcasts set ai_reason = $2, ai_analysis_id = $3, updated_at = now() where id = $1",
                                   existing["id"], reason, run_id)
            continue
        bid = await conn.fetchval(
            """insert into area_broadcasts (target_type, center, radius_km, level, title, message, send_at, status, exercise, created_by,
                   source, area_label, hazard, ai_analysis_id, ai_reason, original_level, original_title, original_message, original_radius_km)
               values ('point', ST_SetSRID(ST_MakePoint($2, $1), 4326), $3, $4, $5, $6, now(), 'PROPOSED', $7, 'ai_analyst',
                   'ai_analyst', $8, $9, $10, $11, $4, $5, $6, $3) returning id""",
            lat, lon, radius, level, title, message, exercise, label, hazard, run_id, reason)
        await audit(conn, "ai_analyst", "broadcast.propose", "area_broadcast", str(bid),
                    {"level": level, "hazard": hazard, "area": label, "radius_km": radius, "analysis": str(run_id)})
        created += 1
    return created
