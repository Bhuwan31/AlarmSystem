"""End-to-end: an approved warning reaches residents near its station; cancelling it sends an all-clear.
Runs against the RUNNING stack with simulated users only; uses a river station that has no open warnings and no real
subscribers nearby, and deletes everything it created.

    docker compose --profile ml run --rm ml-train python -m tests.e2e_warning_delivery
"""
import asyncio
import os
import uuid
import sys

import asyncpg
import httpx

from tests.e2e_visual import API, check, cleanup, make_user, offset, results


async def main() -> None:
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    wid = None
    try:
        st = await db.fetchrow(
            """select s.id, s.name, ST_Y(s.geom) lat, ST_X(s.geom) lon from stations s
               where s.kind = 'river' and not exists (select 1 from warnings w where w.station_id = s.id and w.status in ('PROPOSED', 'ACTIVE'))
                 and not exists (select 1 from alert_subscriptions a join users u on u.id = a.user_id
                                 where u.email not like '%@sim.amhews.test' and ST_DWithin(a.home::geography, s.geom::geography, 40000))
               order by s.id limit 1""")
        check("found a quiet river station", st is not None, st["name"] if st else "")
        _, admin = await make_user(db, "Sim Approver", "admin")
        _, oper = await make_user(db, "Sim Operator", "operator")
        async with httpx.AsyncClient(timeout=60) as c:
            people = {}
            for name, km in {"Near": 4, "Far": 30}.items():
                uid, h = await make_user(db, f"Sim Resident {name}", "viewer")
                lat, lon = offset(st["lat"], st["lon"], km)
                r = await c.put(f"{API}/visual-disaster/subscription", headers=h, json={"consent": True, "latitude": lat, "longitude": lon})
                people[name] = (uid, h)
                check(f"resident {name} ({km} km) subscribed", r.status_code == 200, str(r.status_code))

            r = await c.post(f"{API}/warnings", headers=oper, json={"station_id": st["id"], "level": "WARNING", "valid_hours": 3,
                                                                   "note": "SIMULATED e2e test"})
            wid = r.json().get("id")
            check("operator proposes a WARNING", r.status_code == 200 and wid, str(r.status_code))
            r = await c.post(f"{API}/warnings/{wid}/approve", headers=people["Far"][1])
            check("a resident cannot approve", r.status_code == 403, str(r.status_code))
            r = await c.post(f"{API}/warnings/{wid}/draft-message", headers=oper)
            d = r.json()
            check("AI writes the residents' message (English + Nepali)", r.status_code == 200 and d["source"] in ("ai", "template")
                  and any("ऀ" <= ch <= "ॿ" for ch in d["message"]), f"source={d.get('source')} model={d.get('model')}")
            edited_title = f"FLOOD WARNING – {st['name']}"
            edited = ("EDITED BY OPERATOR: SIMULATED test, the river is rising. Move animals and valuables to higher ground now.\n"
                      "बाढी चेतावनी: नदी बढ्दैछ। पशु र सामान अग्लो ठाउँमा सार्नुहोस्।")
            r = await c.post(f"{API}/warnings/{wid}/approve", headers=oper, json={"title": edited_title, "message": edited})
            out = r.json()
            res = out.get("residents") or {}
            check("operator approves and activates it", r.status_code == 200 and out["status"] == "ACTIVE", str(out)[:200])
            check("sent to residents within 10 km only", res.get("recipients") == 1 and res.get("delivered") == 1, str(res))

            inbox = (await c.get(f"{API}/visual-disaster/alerts", headers=people["Near"][1])).json()
            check("near resident has it in the app inbox", any(st["name"] in a["title"] and "FLOOD WARNING" in a["title"] for a in inbox),
                  inbox[0]["title"] if inbox else "empty")
            check("residents get exactly the operator's edited text", bool(inbox) and "EDITED BY OPERATOR" in inbox[0]["body"]
                  and "बाढी" in inbox[0]["body"] and "EXERCISE" in inbox[0]["body"])
            src = await db.fetchval("select resident_message_source from warnings where id = $1::uuid", wid)
            check("warning records that the message was edited", src == "edited", str(src))
            far = (await c.get(f"{API}/visual-disaster/alerts", headers=people["Far"][1])).json()
            check("far resident got nothing", far == [], f"{len(far)} alerts")

            hist = (await c.get(f"{API}/visual-disaster/broadcasts?status=SENT", headers=admin)).json()
            check("recorded in Area messages history", any(b["source"] == "warning" and b["area_label"] == st["name"] for b in hist))

            r = await c.post(f"{API}/warnings/{wid}/cancel", headers=admin, json={"reason": "SIMULATED water level falling"})
            res = r.json().get("residents") or {}
            check("cancel sends an all-clear to the same people", r.status_code == 200 and res.get("recipients") == 1 and res.get("delivered") == 1, str(r.json())[:200])
            inbox = (await c.get(f"{API}/visual-disaster/alerts", headers=people["Near"][1])).json()
            check("all-clear in the inbox", any(a["title"].startswith("ALL CLEAR") for a in inbox))
    finally:
        if wid:
            bids = [r["id"] for r in await db.fetch("select id from area_broadcasts where warning_id = $1", uuid.UUID(wid))]
            await db.execute("delete from area_broadcasts where id = any($1::uuid[])", bids)
            await db.execute("delete from warning_approvals where warning_id = $1::uuid", wid)
            await db.execute("delete from warnings where id = $1::uuid", wid)
        await db.close()
        await cleanup()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
