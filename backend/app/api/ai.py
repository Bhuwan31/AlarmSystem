"""AI analyst findings and the AI assistant (advisory only)."""
import asyncio
import time
from collections import defaultdict

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.ai import agent
from app.ai.openai_compat import ProviderError
from app.auth import User, require
from app.config import get_settings
from app.db import pool

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
_chat_log: dict[str, list[float]] = defaultdict(list)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)


@router.get("/status")
async def status():
    s = get_settings()
    last = await pool().fetchrow("select started_at, status from ai_analyses order by started_at desc limit 1")
    return {"configured": agent.configured(), "enabled": s.ai_enabled, "provider": agent.provider(), "model": agent.model(),
            "interval_minutes": agent.interval_s() // 60, "last_run_at": last["started_at"] if last else None,
            "last_status": last["status"] if last else None}


@router.get("/analyses/latest")
async def latest():
    row = await pool().fetchrow("select * from ai_analyses where status = 'done' order by started_at desc limit 1")
    running = await pool().fetchval("select exists(select 1 from ai_analyses where status = 'running' and started_at > now() - interval '20 minutes')")
    return {"analysis": dict(row) if row else None, "running": running}


@router.get("/analyses")
async def history(limit: int = Query(20, le=100)):
    rows = await pool().fetch(
        """select id, trigger, status, model, started_at, finished_at, overall_level, headline, jsonb_array_length(findings) n_findings,
                  tool_calls, input_tokens, output_tokens, error from ai_analyses order by started_at desc limit $1""", limit)
    return [dict(r) for r in rows]


@router.post("/analyses/run")
async def run_now(user: User = Depends(require("operator"))):
    if not agent.configured():
        raise HTTPException(503, "AI is not configured: add GEMINI_API_KEY (free) or ANTHROPIC_API_KEY to .env and restart the backend")
    asyncio.create_task(agent.run_analysis("manual", user.id))   # runs in the background; poll /analyses/latest
    return {"started": True}


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(require("viewer"))):
    if not agent.configured():
        raise HTTPException(503, "AI is not configured: add GEMINI_API_KEY (free) or ANTHROPIC_API_KEY to .env and restart the backend")
    if body.messages[-1].role != "user":
        raise HTTPException(400, "the last message must be from the user")
    now = time.time()
    _chat_log[user.id] = [t for t in _chat_log[user.id] if now - t < 3600]
    if len(_chat_log[user.id]) >= get_settings().ai_chat_per_hour:
        raise HTTPException(429, "question limit reached for this hour")
    _chat_log[user.id].append(now)
    try:
        return await agent.chat([m.model_dump() for m in body.messages])
    except anthropic.RateLimitError as e:
        raise HTTPException(429, "the AI service is busy; try again in a minute") from e
    except anthropic.AuthenticationError as e:
        raise HTTPException(503, "the AI API key was rejected; check ANTHROPIC_API_KEY / GEMINI_API_KEY") from e
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"AI service error ({e.status_code})") from e
    except anthropic.APIConnectionError as e:
        raise HTTPException(502, "cannot reach the AI service") from e
    except ProviderError as e:
        if e.status == 429:
            raise HTTPException(429, "the AI service is busy or the free-tier limit is reached; try again later") from e
        if e.status == 402:
            raise HTTPException(402, "the AI account has no credit left. For Gemini, create a key in a project without "
                                     "billing (free tier) at aistudio.google.com/apikey, or add credit to the project") from e
        if e.status in (401, 403):
            raise HTTPException(503, "the AI API key was rejected; check GEMINI_API_KEY / AI_API_KEY") from e
        if e.status == 0:
            raise HTTPException(502, "cannot reach the AI service") from e
        raise HTTPException(502, f"AI service error ({e.status}): {str(e)[:200]}") from e
