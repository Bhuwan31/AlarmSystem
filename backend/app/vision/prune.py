"""Delete photo files that no database row references any more (e.g. after deleting test data).

    docker compose --profile ml run --rm ml-train python -m app.vision.prune            # dry run
    docker compose --profile ml run --rm ml-train python -m app.vision.prune --delete
"""
import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

from app.config import get_settings


async def main(delete: bool) -> None:
    root = Path(get_settings().visual_storage_dir)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        refs = set()
        for r in await conn.fetch("select image_reference, preview_reference from visual_observations"):
            refs.update((r["image_reference"], r["preview_reference"]))
    finally:
        await conn.close()
    orphans = [p for p in root.rglob("*") if p.is_file() and str(p.relative_to(root)) not in refs]
    for p in orphans:
        if delete:
            p.unlink()
    print(f"{len(orphans)} unreferenced files{' deleted' if delete else ' (dry run; add --delete)'}; {len(refs)} referenced")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    asyncio.run(main(ap.parse_args().delete))
