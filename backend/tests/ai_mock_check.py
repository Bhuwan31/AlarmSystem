"""End-to-end check of the AI analyst and assistant without spending API credits.

A local fake of the Messages API replays a scripted conversation, so the real Anthropic SDK, the real
read-only tools and the real database are all exercised. Run inside the backend container:
    docker compose exec backend python tests/ai_mock_check.py
"""
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:8977"

REQUESTS: list[dict] = []
SCRIPT: list[dict] = []


def msg(content, stop="tool_use"):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 200}}


def tool(id_, name, inp):
    return {"type": "tool_use", "id": id_, "name": name, "input": inp}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        REQUESTS.append({"path": self.path, "beta": self.headers.get("anthropic-beta"), "body": body})
        out = json.dumps(SCRIPT.pop(0)).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


async def main():
    from app.ai import agent
    from app.db import open_pool, pool

    await open_pool()
    station = await pool().fetchval("select id from stations where kind = 'river' limit 1")

    # --- analyst: overview -> station detail -> finding + summary -> done
    SCRIPT[:] = [
        msg([tool("t1", "national_overview", {})]),
        msg([tool("t2", "get_station", {"station_id": station}), tool("t3", "data_quality", {})]),
        msg([tool("t4", "record_finding", {"area": "Test reach", "lat": 28.1, "lon": 82.8, "severity": "WATCH", "confidence": "MEDIUM",
                                           "hazard": "flood", "summary": "Mock finding.", "evidence": ["level 2.3 m at 10:00 UTC"],
                                           "recommended_action": "Monitor.", "station_ids": [station]}),
             tool("t5", "submit_summary", {"overall_level": "WATCH", "headline": "Mock headline", "summary": "Mock summary.",
                                           "data_gaps": ["Satellite rain disabled"]})]),
        msg([{"type": "text", "text": "Done."}], stop="end_turn"),
    ]
    run_id = await agent.run_analysis("manual", "test")
    row = await pool().fetchrow("select status, overall_level, headline, findings, tool_calls, error from ai_analyses where id = $1::uuid", run_id)
    print("analysis:", dict(row) | {"findings": len(row["findings"])})
    assert row["status"] == "done" and row["overall_level"] == "WATCH" and len(row["findings"]) == 1, row["error"]

    first = REQUESTS[0]
    names = [t["name"] for t in first["body"]["tools"]]
    print("tools sent:", names)
    print("beta header:", first["beta"], "| fallbacks:", first["body"].get("fallbacks"), "| cache_control:", first["body"].get("cache_control"),
          "| effort:", first["body"].get("output_config"))
    sev = next(t for t in first["body"]["tools"] if t["name"] == "record_finding")["input_schema"]["properties"]["severity"]
    print("severity schema:", sev)
    tool_results = [c for c in REQUESTS[2]["body"]["messages"][-1]["content"] if c["type"] == "tool_result"]
    print("tool results returned to model:", [(r["tool_use_id"], str(r["content"])[:80]) for r in tool_results])
    assert "record_finding" in names and "submit_summary" in names and "warnings" not in " ".join(names).replace("active_warnings", "")

    # --- assistant: geocode -> area conditions -> answer
    REQUESTS.clear()
    SCRIPT[:] = [
        msg([tool("c1", "geocode", {"place": "Biratnagar"})]),
        msg([tool("c2", "area_conditions", {"lat": 26.45, "lon": 87.27, "radius_km": 25})]),
        msg([{"type": "text", "text": "Mock answer about Biratnagar."}], stop="end_turn"),
    ]
    out = await agent.chat([{"role": "user", "content": "How is Biratnagar?"}])
    print("chat:", out)
    area = json.loads(REQUESTS[2]["body"]["messages"][-1]["content"][0]["content"][0]["text"]
                      if isinstance(REQUESTS[2]["body"]["messages"][-1]["content"][0]["content"], list)
                      else REQUESTS[2]["body"]["messages"][-1]["content"][0]["content"])
    print("area_conditions keys:", list(area), "| rivers:", len(area["rivers"]), "| weather ok:", "current" in area["weather"])
    assert out["tools_used"] == ["geocode", "area_conditions"]
    print("ALL AI CHECKS PASSED")


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8977), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    asyncio.run(main())
