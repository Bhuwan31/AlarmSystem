"""Live check of "send to all phones": a sent area message is published once to MASS_ALERT_NTFY_TOPIC even when nobody
is subscribed in the area, and a second publication of the same message is never made. Publishes ONE message marked
SIMULATED TEST to the configured topic; deletes everything else it creates.

    docker compose --profile ml run --rm ml-train python -m tests.e2e_mass_alert
"""
import asyncio
import json
import os
import sys
import uuid

import asyncpg
import httpx

from app.config import get_settings
from app.vision import notify
from tests.e2e_visual import API, check, cleanup, make_user, results


async def main() -> None:
    topic = get_settings().mass_alert_ntfy_topic
    if not topic:
        sys.exit("MASS_ALERT_NTFY_TOPIC is not set")
    db = await asyncpg.connect(os.environ["DATABASE_URL"])
    bid = None
    try:
        _, op = await make_user(db, "Sim Operator", "operator")
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{API}/visual-disaster/broadcasts", headers=op, json={
                "target_type": "point", "latitude": 29.95, "longitude": 81.80, "radius_km": 2, "level": "WATCH",
                "title": "SIMULATED TEST — send to all phones",
                "message": "SIMULATED TEST of the all-phones channel. No real hazard. You can ignore this message."})
            out = r.json()
            bid = out.get("id")
            check("area message sent", r.status_code == 201 and out["status"] == "SENT", str(out)[:200])
            check("published to the all-phones topic although nobody lives there",
                  (out.get("delivery") or {}).get("all_phones") == "sent" and (out.get("delivery") or {}).get("recipients") == 0, str(out.get("delivery")))
            await asyncio.sleep(2)
            t = (await c.get(f"{get_settings().ntfy_server.rstrip('/')}/{topic}/json", params={"poll": "1", "since": "5m"})).text
            titles = [json.loads(x).get("title") for x in t.splitlines() if x.strip()]
            check("message is on the ntfy topic", "SIMULATED TEST — send to all phones" in titles, f"{len(titles)} recent messages")
            again = await notify.mass_send(db, f"broadcast:{bid}", "WATCH", "dup", "dup")
            check("the same message is never published twice", again is None, str(again))
    finally:
        if bid:
            await db.execute("delete from mass_alerts where ref = $1", f"broadcast:{bid}")
            await db.execute("delete from area_broadcasts where id = $1", uuid.UUID(bid))
        await db.close()
        await cleanup()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
