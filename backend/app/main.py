import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, devices, public, shelters, warnings
from app.config import get_settings
from app.db import close_pool, open_pool, pool
from app.devices import mqtt
from app.security import hash_password
from app.jobs import build_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("engineio.client", "socketio.client", "apscheduler.executors.default"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    await open_pool()
    await _bootstrap_admin()
    scheduler, mqtt_task = None, None
    if s.enable_scheduler:
        scheduler = build_scheduler()
        scheduler.start()
        mqtt_task = asyncio.create_task(mqtt.run_forever())
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    if mqtt_task:
        mqtt_task.cancel()
    await close_pool()


async def _bootstrap_admin() -> None:
    s = get_settings()
    if not (s.admin_email and s.admin_password):
        return
    async with pool().acquire() as conn:
        if await conn.fetchval("select count(*) from users") == 0:
            await conn.execute("insert into users (email, name, role, password_hash) values ($1, 'Administrator', 'admin', $2)",
                               s.admin_email.lower(), hash_password(s.admin_password))
            logging.getLogger(__name__).info("created first admin account %s", s.admin_email)


app = FastAPI(title="AMHEWS API", version="0.1.0", lifespan=lifespan,
              description="Adaptive Multi-Hazard Early Warning and Evacuation Support System")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(public.router)
app.include_router(warnings.router)
app.include_router(devices.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(shelters.router)


@app.get("/health")
async def health():
    await pool().fetchval("select 1")
    return {"status": "ok"}
