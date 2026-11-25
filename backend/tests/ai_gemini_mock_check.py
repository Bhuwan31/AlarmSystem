"""End-to-end check of the Gemini / OpenAI-compatible AI path without an API key.

A local fake of the chat-completions API replays a scripted conversation, so the real tool loop, the real
read-only tools and the real database are exercised. Run inside the backend container:
    docker compose cp backend/tests/ai_gemini_mock_check.py backend:/app/
    docker compose exec backend python /app/ai_gemini_mock_check.py
"""
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
    os.environ.pop(k, None)
os.environ.update(AI_PROVIDER="openai_compat", AI_BASE_URL="http://127.0.0.1:8978/", AI_API_KEY="test-key", AI_MODEL="gemini-test")

REQUESTS: list[dict] = []
SCRIPT: list = []


def reply(content=None, calls=None):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = [{"id": f"call_{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)},
                              "extra_content": {"google": {"thought_signature": f"sig-{n}"}}} for i, (n, a) in enumerate(calls)]
    return {"choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 100}}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        REQUESTS.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
        item = SCRIPT.pop(0)
        status, out = (item if isinstance(item, tuple) else (200, item))
        data = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        if status == 429:
            self.send_header("retry-after", "1")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


async def main():
    from app.ai import agent
    from app.db import open_pool, pool

    await open_pool()
    print("provider:", agent.provider(), "| configured:", agent.configured(), "| model:", agent.model())
    station = await pool().fetchval("select id from stations where kind = 'river' limit 1")

    # --- analyst: a rate-limit retry, overview + station, then finding + summary (loop stops after submit_summary)
    SCRIPT[:] = [
        (429, {"error": {"message": "quota"}}),
        reply(calls=[("national_overview", {})]),
        reply(calls=[("get_station", {"station_id": station}), ("list_river_stations", {"min_index": 0.5, "limit": 5})]),
        reply(calls=[("record_finding", {"area": "Test reach", "lat": 28.1, "lon": 82.8, "severity": "WATCH", "confidence": "MEDIUM",
                                         "hazard": "flood", "summary": "Mock finding.", "evidence": ["level 2.3 m"],
                                         "recommended_action": "Monitor.", "station_ids": [station]}),
                     ("submit_summary", {"overall_level": "WATCH", "headline": "Mock headline", "summary": "Mock summary.",
                                         "data_gaps": ["Satellite rain disabled"]})]),
    ]
    run_id = await agent.run_analysis("manual", "test")
    row = await pool().fetchrow("select status, model, overall_level, headline, findings, tool_calls, input_tokens, error from ai_analyses where id = $1::uuid", run_id)
    print("analysis:", dict(row) | {"findings": len(row["findings"])})
    assert row["status"] == "done" and row["overall_level"] == "WATCH" and len(row["findings"]) == 1 and row["tool_calls"] == 5, row["error"]
    assert not SCRIPT, "loop should stop after submit_summary"

    first = REQUESTS[1]["body"]
    print("path:", REQUESTS[1]["path"], "| auth:", REQUESTS[1]["auth"][:13], "| reasoning_effort:", first.get("reasoning_effort"))
    print("tools sent:", [t["function"]["name"] for t in first["tools"]])
    schema = json.dumps([t["function"]["parameters"] for t in first["tools"]])
    assert "anyOf" not in schema and "additionalProperties" not in schema and '"title"' not in schema, "schema not cleaned"
    basin = next(t for t in first["tools"] if t["function"]["name"] == "list_river_stations")["function"]["parameters"]["properties"]["basin"]
    print("optional param schema:", basin)
    sent = REQUESTS[2]["body"]["messages"]
    echoed = sent[2]["tool_calls"][0].get("extra_content")
    print("thought signature echoed:", echoed)
    assert echoed == {"google": {"thought_signature": "sig-national_overview"}}
    tool_msg = sent[3]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_0" and "rivers" in tool_msg["content"]
    print("tool result to model:", tool_msg["content"][:100])

    # --- assistant: geocode -> area_conditions -> answer
    REQUESTS.clear()
    SCRIPT[:] = [
        reply(calls=[("geocode", {"place": "Biratnagar"})]),
        reply(calls=[("area_conditions", {"lat": 26.45, "lon": 87.27, "radius_km": 25})]),
        reply(content="Mock answer about Biratnagar."),
    ]
    out = await agent.chat([{"role": "user", "content": "How is Biratnagar?"}])
    print("chat:", out)
    area = json.loads(REQUESTS[2]["body"]["messages"][-1]["content"])
    print("area_conditions keys:", list(area))
    assert out == {"answer": "Mock answer about Biratnagar.", "tools_used": ["geocode", "area_conditions"]}

    # --- bad key is reported, not crashed
    from app.ai.openai_compat import ProviderError
    SCRIPT[:] = [(401, [{"error": {"message": "API key not valid"}}])]
    try:
        await agent.chat([{"role": "user", "content": "hi"}])
        raise AssertionError("expected ProviderError")
    except ProviderError as e:
        print("bad key ->", e.status, str(e))
        assert e.status == 401

    await pool().execute("delete from ai_analyses where requested_by = 'test'")
    print("ALL GEMINI-PATH CHECKS PASSED")


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8978), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    asyncio.run(main())
