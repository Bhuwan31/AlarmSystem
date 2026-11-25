"""Tool-calling loop for OpenAI-compatible chat APIs (Google Gemini, and others via AI_BASE_URL).

Uses the same read-only tool objects as the Claude path: each tool's JSON schema is sent as a
function declaration and each call is validated and executed with tool.call(args).
"""
import asyncio
import json
import logging
from typing import Callable

import httpx

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
BUSY = (429, 500, 502, 503, 504)   # overloaded / rate-limited: worth retrying, or switching to the fallback model


class ProviderError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


def _clean(schema):
    """Reduce a pydantic JSON schema to the subset Gemini function declarations accept."""
    if isinstance(schema, list):
        return [_clean(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    if "anyOf" in schema:  # Optional[X] -> X
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        if len(options) == 1:
            merged = {**options[0], **{k: v for k, v in schema.items() if k not in ("anyOf", "default", "title")}}
            return _clean(merged)
    return {k: _clean(v) for k, v in schema.items() if k not in ("title", "default", "additionalProperties", "$schema")}


def _function(tool) -> dict:
    d = tool.to_dict()
    return {"type": "function", "function": {"name": d["name"], "description": d.get("description", ""),
                                             "parameters": _clean(d["input_schema"])}}


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float = 180):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    async def complete(self, body: dict, attempts: int = 6) -> dict:
        """POST /chat/completions with back-off on rate limits and server errors (free tiers hit 429 often)."""
        last = attempts - 1
        for attempt in range(attempts):
            try:
                r = await self._http.post("chat/completions", json=body)
            except httpx.TransportError as e:
                if attempt == last:
                    raise ProviderError(0, f"cannot reach the AI service ({type(e).__name__})") from e
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in BUSY and attempt < last:
                wait = float(r.headers.get("retry-after") or min(60, 5 * 2 ** attempt))
                log.info("AI provider returned %s; retrying in %.0f s", r.status_code, wait)
                await asyncio.sleep(wait)
                continue
            try:
                detail = r.json()
                detail = detail[0] if isinstance(detail, list) else detail
                msg = detail.get("error", {}).get("message") or r.text
            except ValueError:
                msg = r.text
            raise ProviderError(r.status_code, msg[:300])
        raise ProviderError(429, "rate limit")


async def run(client: Client, *, model: str, system: str, history: list[dict], tools: list, max_iterations: int,
              max_tokens: int, effort: str | None = None, stop_after: Callable[[str], bool] | None = None,
              fallback_model: str | None = None, on_fallback: Callable[[], None] | None = None) -> dict:
    """Run the model with tools. If the main model stays busy (overloaded or rate-limited) after a few quick retries,
    start the whole run again on `fallback_model` — a fresh start, because a conversation cannot move between models
    midway (Gemini ties its thought signatures to the model). `on_fallback` lets the caller discard partial results.
    The returned dict says which model produced the answer."""
    if fallback_model and fallback_model != model:
        try:
            return await _run(client, model, system, history, tools, max_iterations, max_tokens, effort, stop_after, attempts=3)
        except ProviderError as e:
            if e.status not in BUSY:
                raise
            log.warning("AI model %s is busy (%s); switching to fallback model %s", model, e.status, fallback_model)
            if on_fallback:
                on_fallback()
    else:
        fallback_model = model
    return await _run(client, fallback_model, system, history, tools, max_iterations, max_tokens, effort, stop_after)


async def _run(client: Client, model: str, system: str, history: list[dict], tools: list, max_iterations: int,
               max_tokens: int, effort: str | None, stop_after: Callable[[str], bool] | None, attempts: int = 6) -> dict:
    by_name = {t.to_dict()["name"]: t for t in tools}
    messages = [{"role": "system", "content": system}, *history]
    body_base = {"model": model, "tools": [_function(t) for t in tools], "max_tokens": max_tokens}
    if effort:
        body_base["reasoning_effort"] = {"low": "low", "medium": "medium"}.get(effort, "high")
    used: list[str] = []
    usage = {"input": 0, "output": 0}
    text, finish = "", None
    for _ in range(max_iterations):
        resp = await client.complete({**body_base, "messages": messages}, attempts=attempts)
        u = resp.get("usage") or {}
        usage["input"] += u.get("prompt_tokens") or 0
        usage["output"] += u.get("completion_tokens") or 0
        choice = resp["choices"][0]
        msg, finish = choice["message"], choice.get("finish_reason")
        text = msg.get("content") or ""
        calls = msg.get("tool_calls") or []
        # Keep the assistant turn exactly as returned (Gemini needs its thought signatures echoed back).
        messages.append({k: v for k, v in msg.items() if v is not None})
        if not calls:
            break
        stop = False
        for c in calls:
            name = c["function"]["name"]
            used.append(name)
            tool = by_name.get(name)
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
                result = await tool.call(args) if tool else f"Error: unknown tool {name}"
            except Exception as e:  # noqa: BLE001 — return the error to the model so it can correct itself
                result = f"Error: {type(e).__name__}: {str(e)[:300]}"
            messages.append({"role": "tool", "tool_call_id": c.get("id", name), "content": result if isinstance(result, str) else json.dumps(result, default=str)})
            stop = stop or bool(stop_after and stop_after(name))
        if stop:
            break
    return {"text": text.strip(), "model": model, "tools_used": used, "input_tokens": usage["input"], "output_tokens": usage["output"], "finish_reason": finish}
