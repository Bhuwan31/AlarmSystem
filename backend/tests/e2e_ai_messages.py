"""End-to-end test of AI-drafted area messages against the RUNNING stack, with simulated users only.

AI findings -> drafts (PROPOSED) -> pending list -> edit -> approve & send -> delivered to residents in the radius;
reject -> kept in history -> can still be sent; repeat findings update a draft instead of adding one; data gaps and
NORMAL findings make no draft; CRITICAL needs two-factor. Everything created is deleted at the end.

    docker compose --profile ml run --rm ml-train python -m tests.e2e_ai_messages
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

import asyncpg
import httpx

from app.ai import proposals
from app.db import _init_connection
from tests.e2e_visual import API, TAG, check, cleanup, make_user, offset, results

SITE = (27.700, 85.320)            # Kathmandu
OTHER = (28.200, 83.990)           # Pokhara, far away


async def main() -> None:
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    await _init_connection(db)                                    # same JSON handling as the app's pool
    run_id = await db.fetchval("insert into ai_analyses (trigger, status, model) values ('manual', 'done', 'e2e-sim') returning id")
    try:
        _, admin = await make_user(db, "Sim Approver", "admin")
        near = offset(*SITE, 3)                                   # 3 km away: inside 10 km
        far = offset(*SITE, 25)                                   # 25 km away: outside
        async with httpx.AsyncClient(timeout=60) as c:
            for name, (lat, lon) in {"Near": near, "Far": far}.items():
                _, h = await make_user(db, f"Sim Resident {name}", "viewer")
                r = await c.put(f"{API}/visual-disaster/subscription", headers=h,
                                json={"consent": True, "latitude": lat, "longitude": lon, "district": "Kathmandu"})
                check(f"resident {name} subscribed", r.status_code == 200, str(r.status_code))

            findings = [
                {"area": "Bagmati at Teku", "lat": SITE[0], "lon": SITE[1], "severity": "WARNING", "hazard": "flood", "confidence": "MEDIUM",
                 "summary": "River level rising fast after 60 mm of rain in 6 hours.", "evidence": ["Teku gauge 4.1 m, +0.6 m/h"],
                 "recommended_action": "Prepare evacuation of riverside settlements.",
                 "public_message": "The Bagmati river near Teku is rising quickly after heavy rain. Stay away from the river bank and be ready to move to higher ground."},
                {"area": "Seti at Pokhara", "lat": OTHER[0], "lon": OTHER[1], "severity": "WATCH", "hazard": "heavy_rain", "confidence": "LOW",
                 "summary": "Heavy rain forecast overnight.", "evidence": [], "recommended_action": "Monitor."},
                {"area": "West Rapti", "lat": 28.0, "lon": 82.5, "severity": "WARNING", "hazard": "data_gap", "summary": "Gauge offline."},
                {"area": "Koshi", "lat": 26.8, "lon": 87.2, "severity": "NORMAL", "hazard": "flood", "summary": "Normal."},
            ]
            async with db.transaction():
                n = await proposals.propose(db, run_id, findings, exercise=True)
            check("AI findings -> drafts (only WATCH+ public hazards)", n == 2, f"{n} drafts")
            async with db.transaction():
                n2 = await proposals.propose(db, run_id, findings[:1], exercise=True)
            check("repeat finding updates the waiting draft instead of adding one", n2 == 0, f"{n2} new")

            r = await c.get(f"{API}/visual-disaster/broadcasts/pending", headers=admin)
            pend = r.json()
            check("pending list for the banner/sound", r.status_code == 200 and pend["count"] >= 2 and pend["items"][0]["level"] == "WARNING",
                  f"{pend.get('count')} waiting, first {pend['items'][0]['level'] if pend.get('items') else None}")
            drafts = {d["area_label"]: d for d in pend["items"]}
            teku, pokhara = drafts["Bagmati at Teku"]["id"], drafts["Seti at Pokhara"]["id"]
            lst = {b["id"]: b for b in (await c.get(f"{API}/visual-disaster/broadcasts?status=PROPOSED", headers=admin)).json()}
            check("AI's own resident message used", "rising quickly" in lst[teku]["message"])
            check("template message when the AI wrote none", "Heavy rain risk in and around Seti at Pokhara" in lst[pokhara]["message"])
            check("what the AI saw is attached", lst[teku]["ai_reason"]["evidence"] == ["Teku gauge 4.1 m, +0.6 m/h"])

            r = await c.patch(f"{API}/visual-disaster/broadcasts/{teku}", headers=admin,
                              json={"message": "EDITED: Bagmati at Teku is rising. Move away from the river bank now.", "radius_km": 10})
            b = next(x for x in (await c.get(f"{API}/visual-disaster/broadcasts?status=PROPOSED", headers=admin)).json() if x["id"] == teku)
            check("edit saved, AI original kept", r.status_code == 200 and b["edited"] and b["message"].startswith("EDITED")
                  and "rising quickly" in b["original_message"])

            r = await c.post(f"{API}/visual-disaster/broadcasts/{teku}/approve", headers=admin, json={"level": "CRITICAL"})
            check("CRITICAL refused without two-factor", r.status_code == 403, str(r.status_code))
            r = await c.post(f"{API}/visual-disaster/broadcasts/{teku}/approve", headers=admin, json={})
            out = r.json()
            check("approve & send now", r.status_code == 200 and out["status"] == "SENT", str(out)[:160])
            sent = (await c.get(f"{API}/visual-disaster/broadcasts?status=SENT", headers=admin)).json()
            s = next(x for x in sent if x["id"] == teku)
            check("sent to residents inside the radius only", s["recipients"] == 1, f"{s['recipients']} recipient(s)")
            check("history records approver and time", s["reviewed_by"] and s["reviewed_at"] and s["sent_at"])
            body = await db.fetchval("select body from emergency_notifications where broadcast_id = $1 limit 1", uuid.UUID(teku))
            check("delivered text is the edited message", body is not None and "EDITED: Bagmati" in body and "EXERCISE" in body)
            r = await c.post(f"{API}/visual-disaster/broadcasts/{teku}/approve", headers=admin, json={})
            check("a sent message cannot be sent twice", r.status_code == 409, str(r.status_code))

            r = await c.post(f"{API}/visual-disaster/broadcasts/{pokhara}/reject", headers=admin, json={"note": "Forecast only, not needed yet"})
            rej = next((x for x in (await c.get(f"{API}/visual-disaster/broadcasts?status=REJECTED", headers=admin)).json() if x["id"] == pokhara), None)
            check("reject keeps it in history with note", r.status_code == 200 and rej and rej["review_note"] == "Forecast only, not needed yet")
            pend = (await c.get(f"{API}/visual-disaster/broadcasts/pending", headers=admin)).json()
            check("rejected draft leaves the waiting list", all(i["id"] != pokhara for i in pend["items"]))
            async with db.transaction():
                n3 = await proposals.propose(db, run_id, findings[1:2], exercise=True)
            check("a rejected area can be drafted again by a later analysis", n3 == 1, f"{n3}")
            r = await c.post(f"{API}/visual-disaster/broadcasts/{pokhara}/approve", headers=admin,
                             json={"send_at": (datetime.now().astimezone() + timedelta(hours=2)).isoformat()})
            check("rejected draft can still be scheduled later", r.status_code == 200 and r.json()["status"] == "SCHEDULED", str(r.json())[:120])

            _, viewer = await make_user(db, "Sim Viewer", "viewer")
            r = await c.get(f"{API}/visual-disaster/broadcasts/pending", headers=viewer)
            check("residents cannot see drafts", r.status_code == 403, str(r.status_code))
    finally:
        ids = await db.fetch("select id from area_broadcasts where ai_analysis_id = $1", run_id)
        await db.execute("delete from area_broadcasts where id = any($1::uuid[])", [r["id"] for r in ids])
        await db.execute("delete from ai_analyses where id = $1", run_id)
        await db.close()
        await cleanup()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
