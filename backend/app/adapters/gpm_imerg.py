"""NASA GPM IMERG Early Run half-hourly precipitation over the deployment bbox.

Data: GES DISC product GPM_3IMERGHHE (0.1 deg, 30 min, available about 4 h after observation).
Access: requires a free NASA Earthdata account; set EARTHDATA_TOKEN (Earthdata bearer token).
Uses the OPeNDAP ASCII subset service so no HDF5 library is needed.

Status: implemented against the documented GES DISC URL layout; verify on the first run with a
real token (product version tag may change, see IMERG_VERSION_TAG).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.base import AdapterDisabled, GridPoint

BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3"
RES = 0.1


def granule_url(product: str, version_tag: str, start: datetime) -> str:
    end = start + timedelta(minutes=29, seconds=59)
    minutes = start.hour * 60 + start.minute
    name = (f"3B-HHR-E.MS.MRG.3IMERG.{start:%Y%m%d}-S{start:%H%M%S}-E{end:%H%M%S}."
            f"{minutes:04d}.{version_tag}.HDF5")
    return f"{BASE}/{product}/{start:%Y}/{start.timetuple().tm_yday:03d}/{name}"


def index_window(bbox: list[float]) -> tuple[int, int, int, int]:
    min_lon, min_lat, max_lon, max_lat = bbox
    idx = lambda v: int(v / RES + 1e-6)  # noqa: E731 — guard against 116.3/0.1 = 1162.999...
    return idx(min_lon + 180), idx(max_lon + 180), idx(min_lat + 90), idx(max_lat + 90)


def parse_ascii(text: str, lon0: int, lat0: int, observed_at: datetime, agg_step: float) -> list[GridPoint]:
    """Parse `precipitation[t][lon][lat]` ASCII rows and average onto an agg_step grid (mm/h)."""
    cells: dict[tuple[float, float], list[float]] = defaultdict(list)
    for line in text.splitlines():
        if not line.startswith("precipitation["):
            continue
        head, _, rest = line.partition(",")
        idx = [int(x) for x in head.replace("precipitation", "").strip("[]").split("][")]
        lon_i = lon0 + idx[1]
        lon = -180 + (lon_i + 0.5) * RES
        for k, raw in enumerate(rest.split(",")):
            raw = raw.strip()
            if not raw:
                continue
            v = float(raw)
            if v < 0:          # fill value
                continue
            lat = -90 + (lat0 + k + 0.5) * RES
            key = (round((lat // agg_step) * agg_step + agg_step / 2, 4), round((lon // agg_step) * agg_step + agg_step / 2, 4))
            cells[key].append(v)
    return [GridPoint(lat=lat, lon=lon, observed_at=observed_at, precipitation_mm=round(sum(vs) / len(vs), 3))
            for (lat, lon), vs in sorted(cells.items())]


async def fetch(bbox: list[float], token: str, product: str, version_tag: str,
                agg_step: float = 0.5, now: datetime | None = None) -> list[GridPoint]:
    if not token:
        raise AdapterDisabled("EARTHDATA_TOKEN not set")
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(hours=4)).replace(second=0, microsecond=0)
    start = start.replace(minute=0 if start.minute < 30 else 30)
    lon0, lon1, lat0, lat1 = index_window(bbox)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
        for _ in range(6):   # walk back up to 3 h to the newest published granule
            url = f"{granule_url(product, version_tag, start)}.ascii?precipitation[0:0][{lon0}:{lon1}][{lat0}:{lat1}]"
            resp = await client.get(url)
            if resp.status_code == 404:
                start -= timedelta(minutes=30)
                continue
            resp.raise_for_status()
            return parse_ascii(resp.text, lon0, lat0, start, agg_step)
    return []
