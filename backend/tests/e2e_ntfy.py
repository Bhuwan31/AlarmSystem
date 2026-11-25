"""Real phone-channel check: a simulated resident with a random ntfy topic receives (1) the test message and (2) an
approved warning, read back from the ntfy server. Sends two short test messages to a throwaway topic on NTFY_SERVER.

    docker compose --profile ml run --rm ml-train python -m tests.e2e_ntfy
"""
import asyncio
import os
import secrets
import sys
import uuid

import asyncpg
import httpx

from app.config import get_settings
from tests.e2e_visual import API, check, cleanup, make_user, offset, results


async def ntfy_messages(c: httpx.AsyncClient, topic: str) -> list[dict]:
    import json
    r = await c.get(f"{get_settings().ntfy_server.rstrip('/')}/{topic}/json", params={"poll": "1", "since": "10m"})
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


async def main() -> None:
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    topic = "amhews-e2e-" + secrets.token_hex(8)
    wid = None
    try:
        st = await db.fetchrow(
            """select s.id, s.name, ST_Y(s.geom) lat, ST_X(s.geom) lon from stations s
               where s.kind = 'river' and not exists (select 1 from warnings w where w.station_id = s.id and w.status in ('PROPOSED', 'ACTIVE'))
                 and not exists (select 1 from alert_subscriptions a join users u on u.id = a.user_id
                                 where u.email not like '%@sim.amhews.test' and ST_DWithin(a.home::geography, s.geom::geography, 40000))
               order by s.id limit 1""")
        _, admin = await make_user(db, "Sim Approver", "admin")
        _, me = await make_user(db, "Sim Phone Owner", "viewer")
        lat, lon = offset(st["lat"], st["lon"], 3)
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.put(f"{API}/visual-disaster/subscription", headers=me, json={
                "consent": True, "latitude": lat, "longitude": lon, "channels": {"in_app": True, "ntfy": True}, "ntfy_topic": topic})
            check("resident saves ntfy topic", r.status_code == 200 and r.json()["ntfy_topic"] == topic, str(r.status_code))
            r = await c.post(f"{API}/visual-disaster/subscription/test", headers=me)
            check("test endpoint sends to the phone", r.status_code == 200 and r.json()["results"]["ntfy"]["status"] == "sent", str(r.json())[:200])

            r = await c.post(f"{API}/warnings", headers=admin, json={"station_id": st["id"], "level": "WARNING", "valid_hours": 2, "note": "SIMULATED ntfy test"})
            wid = r.json()["id"]
            r = await c.post(f"{API}/warnings/{wid}/approve", headers=admin)
            res = r.json().get("residents") or {}
            check("approved warning sent to the phone channel", res.get("sent") == 1, str(res))
            await asyncio.sleep(2)
            msgs = await ntfy_messages(c, topic)
            titles = [m.get("title") for m in msgs if m.get("event") == "message"]
            check("ntfy server has the test message", "AMHEWS test alert" in titles, str(titles))
            warn = next((m for m in msgs if m.get("title", "").startswith("FLOOD WARNING")), None)
            check("ntfy server has the warning, top priority (vibrates), Nepali text intact",
                  warn is not None and warn.get("priority") == 5 and "बाढी" in warn.get("message", ""), str(warn)[:200])
            r = await c.post(f"{API}/warnings/{wid}/cancel", headers=admin, json={"reason": "SIMULATED test finished"})
            check("all-clear also sent to the phone", (r.json().get("residents") or {}).get("sent") == 1, str(r.json())[:160])
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
