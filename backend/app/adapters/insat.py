"""INSAT-3D / 3DR / 3DS rainfall products (ISRO, distributed by MOSDAC).

MOSDAC requires a registered account and provides an official download tool. Run that tool on a
schedule with its output folder set to INSAT_INBOX_DIR; this adapter picks up new HDF5 files,
extracts rainfall over the deployment bbox, averages it onto the grid and marks each file done.

Dataset names differ between products, so they are configurable (INSAT_RAIN_DATASET etc.).
Requires the optional `h5py` package. Status: verify dataset names on the first real file.
"""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.base import AdapterDisabled, GridPoint


def _scaled(ds):
    import numpy as np
    arr = ds[()].astype("float64")
    fill = ds.attrs.get("_FillValue")
    if fill is not None:
        arr = np.where(arr == np.asarray(fill).item(), np.nan, arr)
    scale = ds.attrs.get("scale_factor")
    offset = ds.attrs.get("add_offset")
    if scale is not None:
        arr = arr * float(np.asarray(scale).item())
    if offset is not None:
        arr = arr + float(np.asarray(offset).item())
    return arr


def read_file(path: Path, bbox: list[float], rain_ds: str, lat_ds: str, lon_ds: str, agg_step: float) -> list[GridPoint]:
    import h5py
    import numpy as np
    min_lon, min_lat, max_lon, max_lat = bbox
    with h5py.File(path, "r") as f:
        rain = np.squeeze(_scaled(f[rain_ds]))
        lat = np.squeeze(_scaled(f[lat_ds]))
        lon = np.squeeze(_scaled(f[lon_ds]))
        when = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        for key in ("Acquisition_Date", "acquisition_date"):
            if key in f.attrs:
                try:
                    when = datetime.fromisoformat(str(np.asarray(f.attrs[key]).item())).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    mask = (lat >= min_lat) & (lat <= max_lat) & (lon >= min_lon) & (lon <= max_lon) & ~np.isnan(rain)
    cells: dict[tuple[float, float], list[float]] = defaultdict(list)
    for la, lo, r in zip(lat[mask], lon[mask], rain[mask]):
        key = (round((la // agg_step) * agg_step + agg_step / 2, 4), round((lo // agg_step) * agg_step + agg_step / 2, 4))
        cells[key].append(float(r))
    return [GridPoint(lat=k[0], lon=k[1], observed_at=when, precipitation_mm=round(sum(v) / len(v), 3))
            for k, v in sorted(cells.items())]


def collect(inbox: str, bbox: list[float], rain_ds: str, lat_ds: str, lon_ds: str, agg_step: float = 0.5) -> list[GridPoint]:
    if not inbox:
        raise AdapterDisabled("INSAT_INBOX_DIR not set (MOSDAC download tool output folder)")
    try:
        import h5py  # noqa: F401
    except ImportError as e:
        raise AdapterDisabled("h5py not installed; pip install h5py numpy") from e
    folder = Path(inbox)
    points: list[GridPoint] = []
    for path in sorted(folder.glob("*.h5")) + sorted(folder.glob("*.hdf5")):
        points.extend(read_file(path, bbox, rain_ds, lat_ds, lon_ds, agg_step))
        path.rename(path.with_suffix(path.suffix + ".done"))
    return points
