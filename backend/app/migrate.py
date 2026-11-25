"""Apply supabase/migrations/*.sql to DATABASE_URL (Supabase or any PostgreSQL), each once, in order.

    docker compose run --rm --no-deps backend python -m app.migrate

Applied files are recorded in schema_migrations. A database that already has the AMHEWS tables but no
schema_migrations table (the local Docker database, which ran the files at first start) is treated as having
applied every file except the newest ones listed in NEW_SINCE_INITDB."""
import asyncio
import sys
from pathlib import Path

import asyncpg

from app.db import connect_kwargs
from app.config import get_settings

DIRS = [Path("/migrations"), Path(__file__).resolve().parents[2] / "supabase" / "migrations"]
NEW_SINCE_INITDB = {"0006_lock_data_api.sql", "0007_ai_message_proposals.sql"}


async def main() -> int:
    folder = next((d for d in DIRS if d.is_dir()), None)
    if folder is None:
        print("migrations folder not found", file=sys.stderr)
        return 1
    files = sorted(folder.glob("*.sql"))
    conn = await asyncpg.connect(get_settings().database_url, **connect_kwargs(get_settings().database_url))
    try:
        fresh = not await conn.fetchval("select to_regclass('public.schema_migrations') is not null")
        await conn.execute("create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())")
        if fresh and await conn.fetchval("select to_regclass('public.stations') is not null"):
            await conn.executemany("insert into schema_migrations (name) values ($1) on conflict do nothing",
                                   [(f.name,) for f in files if f.name not in NEW_SINCE_INITDB])
            print("existing AMHEWS database found; earlier migrations recorded as applied")
        done = {r["name"] for r in await conn.fetch("select name from schema_migrations")}
        for f in files:
            if f.name in done:
                continue
            print(f"applying {f.name} ...", flush=True)
            async with conn.transaction():
                await conn.execute(f.read_text(encoding="utf-8"))
                await conn.execute("insert into schema_migrations (name) values ($1)", f.name)
        # schema_migrations itself must not be reachable through Supabase's Data API either
        await conn.execute("alter table schema_migrations enable row level security")
        print("database is up to date")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
