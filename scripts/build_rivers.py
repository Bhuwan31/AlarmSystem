"""Build the river layers used by the dashboard map.

Inputs (download first, not committed):
  ne_50m_rivers_lake_centerlines.geojson  Natural Earth (public domain)  - world rivers
  osm_rivers.json                         OpenStreetMap via Overpass (ODbL) - rivers around the deployment:
      [out:json];way["waterway"="river"](25.8,79.5,30.9,88.7);out geom tags;
  countries.geojson                       datasets/geo-countries (Natural Earth derived)

Outputs (frontend/public/geo):
  rivers_world.geojson   world rivers, scalerank kept for zoom-dependent display
  rivers_nepal.geojson   every named river that flows through Nepal, including its stretches in
                         neighbouring countries, with `countries` in flow order (e.g. "China → Nepal → India")

Usage: python scripts/build_rivers.py <input_dir> <output_dir> [ISO3=NPL]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import linemerge
from shapely.prepared import prep

sys.stdout.reconfigure(encoding="utf-8")
src, out = Path(sys.argv[1]), Path(sys.argv[2])
iso3 = sys.argv[3] if len(sys.argv) > 3 else "NPL"
MIN_KM = 25          # drop short streams
SIMPLIFY_DEG = 0.0015


def rnd(geom):
    def r(c):
        return [round(c[0], 4), round(c[1], 4)]
    g = mapping(geom)
    if g["type"] == "LineString":
        g["coordinates"] = [r(c) for c in g["coordinates"]]
    else:
        g["coordinates"] = [[r(c) for c in line] for line in g["coordinates"]]
    return g


# --- world rivers (Natural Earth 50m) -------------------------------------------------------
ne = json.load(open(src / "ne_50m_rivers_lake_centerlines.geojson", encoding="utf-8"))
world = []
for f in ne["features"]:
    if not f["geometry"]:
        continue
    p = f["properties"]
    world.append({"type": "Feature", "properties": {"name": p.get("name_en") or p.get("name"), "scalerank": p.get("scalerank", 9)},
                  "geometry": rnd(shape(f["geometry"]).simplify(0.01))})
(out / "rivers_world.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": world}, separators=(",", ":")), encoding="utf-8")
print(f"world rivers: {len(world)}")

# --- countries --------------------------------------------------------------------------------
countries = {}
for f in json.load(open(src / "countries.geojson", encoding="utf-8"))["features"]:
    code = f["properties"].get("ISO3166-1-Alpha-3")
    if code in {"NPL", "CHN", "IND", "BGD", "BTN"}:
        countries[code] = (f["properties"].get("name"), prep(shape(f["geometry"])), shape(f["geometry"]))
home_name, home_prep, home_geom = countries[iso3]

# --- OSM rivers around the deployment --------------------------------------------------------
osm = json.load(open(src / "osm_rivers.json", encoding="utf-8"))
by_name = defaultdict(list)
for el in osm["elements"]:
    tags = el.get("tags", {})
    name = tags.get("name:en") or tags.get("name")
    if not name or len(el.get("geometry", [])) < 2:
        continue
    by_name[name].append(LineString([(p["lon"], p["lat"]) for p in el["geometry"]]))

features = []
for name, lines in by_name.items():
    # linemerge keeps the drawing direction (OSM waterways are drawn downstream); no noding, so flow order survives
    merged = lines[0] if len(lines) == 1 else linemerge(MultiLineString(lines))
    if merged.length * 100 < MIN_KM:          # ~100 km per degree at these latitudes
        continue
    if not home_prep.intersects(merged):
        continue
    parts = list(merged.geoms) if isinstance(merged, MultiLineString) else [merged]
    # country sequence along the longest part, in OSM drawing order (= flow direction for waterways)
    main = max(parts, key=lambda g: g.length)
    seq = []
    for i in range(0, 101, 2):
        pt = main.interpolate(i / 100, normalized=True)
        for code, (cname, cprep, _) in countries.items():
            if cprep.contains(pt):
                if not seq or seq[-1] != cname:
                    seq.append(cname)
                break
    crosses = len({s for s in seq}) > 1
    features.append({"type": "Feature",
                     "properties": {"name": name, "length_km": round(merged.length * 100), "countries": " → ".join(seq) or home_name,
                                    "transboundary": crosses},
                     "geometry": rnd(merged.simplify(SIMPLIFY_DEG))})

features.sort(key=lambda f: -f["properties"]["length_km"])
(out / "rivers_nepal.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
print(f"{iso3} rivers: {len(features)} ({sum(f['properties']['transboundary'] for f in features)} transboundary)")
for f in features[:15]:
    print(f"  {f['properties']['name']}: {f['properties']['length_km']} km, {f['properties']['countries']}")
