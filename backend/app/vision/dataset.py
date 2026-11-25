"""Dataset preparation and versioning for the visual model.

Input: one or more source folders, each with a manifest.csv (columns below) — or, for a folder without a manifest,
one sub-folder per class (`<root>/<class>/*.jpg`), in which case each file is its own incident and location.

    path,label,incident_id,location_id,condition,source,license
    flood/ktm_2024_07_06_a.jpg,urban_flooding,ktm-2024-07-06,kathmandu-balkhu,day,own photo,CC BY 4.0

Rules
  * every row must carry provenance (source, license); rows with an unknown label are refused
  * exact duplicate files (sha256) are dropped, keeping the first
  * TEST = whole locations held out (generalisation to unseen places); VAL = whole incidents held out from the rest;
    no incident or location is split across sets (no leakage between near-identical shots)
  * the dataset version is `<name>-<first 10 hex of sha256(manifest)>`, so any change produces a new version

    python -m app.vision.dataset --name synthetic --source ml_data/vision/synthetic_v1 --out ml_data/vision/datasets
    python -m app.vision.dataset --name real --source /data/my_photos --source ml_data/vision/synthetic_v1 ...
"""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.vision.classes import CLASSES

FIELDS = ["path", "label", "incident_id", "location_id", "condition", "source", "license"]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class Row:
    path: str          # absolute path
    label: str
    incident_id: str
    location_id: str
    condition: str
    source: str
    license: str
    split: str = ""
    sha256: str = ""


def _read_source(root: Path) -> list[Row]:
    rows: list[Row] = []
    man = root / "manifest.csv"
    if man.exists():
        with open(man, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(Row(path=str((root / r["path"]).resolve()), label=r["label"].strip(),
                                incident_id=r.get("incident_id") or r["path"], location_id=r.get("location_id") or r["path"],
                                condition=r.get("condition") or "unknown", source=r.get("source") or "",
                                license=r.get("license") or ""))
    else:
        for cls_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for p in sorted(cls_dir.iterdir()):
                if p.suffix.lower() in IMAGE_EXT:
                    rows.append(Row(path=str(p.resolve()), label=cls_dir.name, incident_id=p.stem, location_id=p.stem,
                                    condition="unknown", source=f"folder:{root.name}", license="unknown"))
    return rows


def assign_splits(rows: list[Row], seed: int = 13, test_frac: float = 0.15, val_frac: float = 0.15) -> None:
    """Group-aware split: locations → test, then incidents → val, rest → train."""
    rng = random.Random(seed)
    locs = sorted({r.location_id for r in rows})
    rng.shuffle(locs)
    test_locs = set(locs[:max(1, int(len(locs) * test_frac))])
    rest_inc = sorted({r.incident_id for r in rows if r.location_id not in test_locs})
    rng.shuffle(rest_inc)
    val_inc = set(rest_inc[:max(1, int(len(rest_inc) * val_frac / (1 - test_frac)))])
    for r in rows:
        r.split = "test" if r.location_id in test_locs else "val" if r.incident_id in val_inc else "train"


def prepare(name: str, sources: list[Path], out: Path, seed: int = 13) -> Path:
    rows: list[Row] = []
    for s in sources:
        rows += _read_source(s)
    bad = [r for r in rows if r.label not in CLASSES]
    if bad:
        raise SystemExit(f"{len(bad)} rows have unknown labels, e.g. {bad[0].label!r}; allowed: {CLASSES}")
    missing = [r for r in rows if not r.source or not r.license]
    if missing:
        raise SystemExit(f"{len(missing)} rows lack source/license provenance, e.g. {missing[0].path}")
    seen, unique = set(), []
    for r in rows:
        r.sha256 = hashlib.sha256(Path(r.path).read_bytes()).hexdigest()
        if r.sha256 not in seen:
            seen.add(r.sha256)
            unique.append(r)
    assign_splits(unique, seed)
    body = "\n".join(f"{r.sha256},{r.label},{r.split}" for r in sorted(unique, key=lambda r: r.sha256))
    version = f"{name}-{hashlib.sha256(body.encode()).hexdigest()[:10]}"
    d = out / version
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS + ["split", "sha256"])
        for r in unique:
            w.writerow([r.path, r.label, r.incident_id, r.location_id, r.condition, r.source, r.license, r.split, r.sha256])
    counts = {sp: dict(Counter(r.label for r in unique if r.split == sp)) for sp in ("train", "val", "test")}
    card = {
        "version": version, "name": name, "sources": [str(s) for s in sources], "images": len(unique),
        "duplicates_dropped": len(rows) - len(unique), "counts": counts,
        "conditions": dict(Counter(r.condition for r in unique)),
        "provenance": dict(Counter(r.source for r in unique)),
        "synthetic_only": all(r.source.startswith("synthetic") for r in unique),
        "split_rule": "test = held-out locations; val = held-out incidents; no group crosses sets", "seed": seed,
    }
    (d / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return d


def load(dataset_dir: Path) -> tuple[list[Row], dict]:
    rows = []
    with open(dataset_dir / "manifest.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(Row(**{k: r[k] for k in FIELDS}, split=r["split"], sha256=r["sha256"]))
    return rows, json.loads((dataset_dir / "card.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--source", action="append", required=True, type=Path)
    ap.add_argument("--out", default="ml_data/vision/datasets", type=Path)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    print(prepare(a.name, a.source, a.out, a.seed))
