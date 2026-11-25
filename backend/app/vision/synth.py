"""Procedural SYNTHETIC scene generator, so the full training → evaluation → inference pipeline runs without a real
photo dataset. Results on synthetic images say nothing about real-world accuracy: a model trained only on these is
recorded as `validated_for_alerts = false`, and the safety policy then treats its output as advisory only.

Each synthetic "location" fixes a scene style (horizon height, building palette, river width, camera tilt...);
each "incident" is a few shots of one scene with small changes. dataset.py splits by location and incident, so
test images come from locations never seen in training (the same leakage rules a real dataset needs).

    python -m app.vision.synth --out ml_data/vision/synthetic_v1 --size 160 --seed 7
"""
import argparse
import csv
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.vision.classes import CLASSES

COUNTS = {"normal": 900, "heavy_rain": 500, "urban_flooding": 450, "river_flooding": 400, "flash_flooding": 260,
          "road_waterlogging": 500, "rising_water": 320, "landslide": 260, "uncertain": 360}   # deliberately imbalanced
CONDITIONS = ["day", "day", "day", "overcast", "dusk", "night", "fog"]


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _jit(c, r: random.Random, s=18):
    return tuple(max(0, min(255, int(v + r.uniform(-s, s)))) for v in c)


class Scene:
    def __init__(self, size: int, loc: dict, r: random.Random):
        self.S, self.loc, self.r = size, loc, r
        self.img = Image.new("RGB", (size, size))
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self.hz = int(size * loc["horizon"] + r.uniform(-4, 4))

    # ----- building blocks -------------------------------------------------------------------------------------
    def sky(self, dark=False):
        top, bot = ((70, 80, 92), (130, 135, 140)) if dark else (self.loc["sky_top"], self.loc["sky_bot"])
        for y in range(self.hz + 1):
            self.d.line([(0, y), (self.S, y)], fill=_lerp(top, bot, y / max(self.hz, 1)))

    def ground(self, colour=None):
        c = colour or self.loc["ground"]
        for y in range(self.hz, self.S):
            t = (y - self.hz) / max(self.S - self.hz, 1)
            self.d.line([(0, y), (self.S, y)], fill=_jit(_lerp(c, tuple(min(255, v + 30) for v in c), t), self.r, 3))

    def hills(self, colour=None, scar=False):
        c = colour or self.loc["hill"]
        pts = [(0, self.hz)]
        for x in range(0, self.S + 8, 8):
            pts.append((x, self.hz - int(self.S * 0.25 * (0.5 + 0.5 * math.sin(x / self.S * math.pi * self.loc["hill_freq"] + self.loc["phase"])))))
        pts.append((self.S, self.hz))
        self.d.polygon(pts, fill=c)
        return pts

    def road(self, lines=True):
        S, hz = self.S, self.hz
        cx = S * self.loc["road_x"]
        self.d.polygon([(cx - 4, hz), (cx + 4, hz), (S * 0.95, S), (S * 0.05, S)], fill=self.loc["road"])
        if lines:
            for k in range(6):
                y0 = hz + (S - hz) * (k / 6) ** 1.3
                y1 = hz + (S - hz) * ((k + 0.5) / 6) ** 1.3
                w = 1 + (y0 - hz) / (S - hz) * 3
                self.d.line([(cx, y0), (cx, y1)], fill=(230, 230, 220), width=int(w))

    def buildings(self, n=None):
        S, hz = self.S, self.hz
        x = 0
        for _ in range(n or self.loc["n_build"]):
            w = self.r.randint(S // 10, S // 4)
            h = self.r.randint(S // 6, int(S * 0.45))
            col = _jit(self.r.choice(self.loc["build_cols"]), self.r)
            self.d.rectangle([x, hz - h, x + w, hz + 6], fill=col)
            for wy in range(hz - h + 4, hz - 4, 8):
                for wx in range(x + 3, x + w - 4, 7):
                    self.d.rectangle([wx, wy, wx + 3, wy + 4], fill=(60, 70, 85) if self.r.random() < 0.7 else (220, 210, 150))
            x += w + self.r.randint(0, 6)
            if x > S:
                break

    def trees(self, n=6, y=None):
        for _ in range(n):
            tx, ty = self.r.randint(0, self.S), (y or self.hz) + self.r.randint(-4, 10)
            rr = self.r.randint(4, 10)
            self.d.rectangle([tx - 1, ty - rr, tx + 1, ty + 4], fill=(80, 60, 40))
            self.d.ellipse([tx - rr, ty - 2 * rr, tx + rr, ty - rr // 2], fill=_jit((50, 110, 50), self.r, 25))

    def water(self, top, colour, ripple=0.4, alpha=255, turbulence=0.0, x0=0, x1=None, reflect=True):
        """Water body from row `top` to the bottom between x0..x1; ripples, reflections, foam for turbulence."""
        S = self.S
        x1 = S if x1 is None else x1
        arr = np.asarray(self.img).astype(np.float32)
        top = max(0, min(S - 1, int(top)))
        rows = S - top
        yy, xx = np.mgrid[0:rows, 0:x1 - x0]
        base = np.array(colour, dtype=np.float32)
        wave = np.sin(xx / (2 + 4 * self.r.random()) + yy * 0.9) * ripple * 18
        layer = np.broadcast_to(base, (rows, x1 - x0, 3)) + wave[..., None]
        if reflect and top > 4:                                     # mirror of what is above the waterline
            src = arr[max(0, top - rows):top, x0:x1][::-1]
            if src.shape[0] < rows:
                src = np.concatenate([src, np.repeat(src[-1:], rows - src.shape[0], 0)], 0)
            layer = 0.65 * layer + 0.35 * src[:rows]
        if turbulence > 0:
            noise = np.random.default_rng(self.r.randint(0, 10 ** 9)).random((rows, x1 - x0))
            foam = (noise > 1 - 0.25 * turbulence).astype(np.float32)
            streak = np.abs(np.sin(xx * 0.35 + yy * 0.15 + noise * 3)) > 0.93
            layer = layer * (1 - 0.6 * foam[..., None]) + 235 * 0.6 * foam[..., None]
            layer[streak] = 0.5 * layer[streak] + 0.5 * 220
        a = alpha / 255
        arr[top:, x0:x1] = (1 - a) * arr[top:, x0:x1] + a * layer
        self.img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def debris(self, n, top):
        for _ in range(n):
            x, y = self.r.randint(0, self.S), self.r.randint(int(top), self.S)
            w, h = self.r.randint(3, 12), self.r.randint(2, 5)
            self.d.polygon([(x, y), (x + w, y + self.r.randint(-2, 2)), (x + w - 2, y + h), (x - 1, y + h)],
                           fill=_jit((70, 50, 35), self.r, 20))

    def rain(self, density=1.0, angle=None):
        a = angle if angle is not None else self.r.uniform(-0.35, 0.15)
        for _ in range(int(260 * density)):
            x, y = self.r.uniform(-20, self.S), self.r.uniform(-10, self.S)
            ln = self.r.uniform(6, 16)
            self.d.line([(x, y), (x + ln * math.sin(a), y + ln * math.cos(a))], fill=(220, 225, 235, self.r.randint(60, 140)), width=1)

    # ----- conditions ------------------------------------------------------------------------------------------
    def condition(self, cond: str):
        arr = np.asarray(self.img).astype(np.float32)
        if cond == "overcast":
            arr = arr * 0.85 + 20
        elif cond == "dusk":
            arr = arr * np.array([0.85, 0.65, 0.55]) + np.array([25, 5, 0])
        elif cond == "night":
            arr = arr * 0.22
            for _ in range(self.r.randint(2, 6)):                   # street lamps
                x, y = self.r.randint(0, self.S - 1), self.r.randint(self.S // 4, self.S - 1)
                yy, xx = np.ogrid[:self.S, :self.S]
                glow = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (self.S / 14) ** 2))
                arr += glow[..., None] * np.array([120, 100, 60])
        elif cond == "fog":
            arr = arr * 0.55 + 0.45 * 200
        arr += np.random.default_rng(self.r.randint(0, 10 ** 9)).normal(0, 4, arr.shape)   # sensor noise
        self.img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        self.d = ImageDraw.Draw(self.img, "RGBA")


def _murky(r):
    return _jit(r.choice([(120, 95, 60), (135, 110, 75), (105, 90, 70), (115, 105, 85)]), r, 12)


def render(cls: str, loc: dict, cond: str, r: random.Random, size: int) -> Image.Image:
    s = Scene(size, loc, r)
    S = size
    if cls == "uncertain":
        kind = r.choice(["noise", "dark", "blur", "texture", "shapes"])
        if kind == "noise":
            a = np.random.default_rng(r.randint(0, 10 ** 9)).integers(0, 255, (S, S, 3), dtype=np.uint8)
            return Image.fromarray(a).filter(ImageFilter.GaussianBlur(r.uniform(0, 1.5)))
        if kind == "dark":
            s.sky(); s.ground(); s.buildings()
            arr = np.asarray(s.img).astype(np.float32) * r.uniform(0.02, 0.07)
            return Image.fromarray(arr.astype(np.uint8))
        if kind == "blur":
            render_cls = r.choice([c for c in CLASSES if c != "uncertain"])
            return render(render_cls, loc, "day", r, size).filter(ImageFilter.GaussianBlur(r.uniform(9, 16)))
        if kind == "texture":
            base = _jit(r.choice([(180, 160, 140), (90, 120, 160), (200, 200, 200), (60, 60, 60)]), r, 40)
            img = Image.new("RGB", (S, S), base)
            d = ImageDraw.Draw(img)
            for _ in range(r.randint(30, 120)):
                x, y = r.randint(0, S), r.randint(0, S)
                d.ellipse([x, y, x + r.randint(2, 20), y + r.randint(2, 20)], fill=_jit(base, r, 50))
            return img
        img = Image.new("RGB", (S, S), _jit((150, 150, 150), r, 90))
        d = ImageDraw.Draw(img)
        for _ in range(r.randint(3, 9)):
            x, y = r.randint(0, S), r.randint(0, S)
            d.rectangle([x, y, x + r.randint(10, 60), y + r.randint(10, 60)], fill=_jit((128, 128, 128), r, 120))
        return img

    dark = cls in ("heavy_rain", "flash_flooding") or (cls in ("urban_flooding", "river_flooding") and r.random() < 0.5)
    s.sky(dark=dark)
    if cls in ("normal", "heavy_rain", "road_waterlogging", "urban_flooding"):
        scene = loc["urban"] if cls != "urban_flooding" else True
        s.hills(); s.ground()
        if scene:
            s.buildings()
        else:
            s.trees(r.randint(3, 8))
        s.road()
        if cls == "normal":
            if r.random() < 0.3:
                s.trees(3, y=S - 10)
        elif cls == "heavy_rain":
            s.water(S * 0.82, (95, 100, 110), ripple=0.15, alpha=110, reflect=True)       # wet sheen only
            s.rain(density=r.uniform(1.2, 2.2))
            s.img = s.img.filter(ImageFilter.GaussianBlur(0.6))
            s.d = ImageDraw.Draw(s.img, "RGBA")
        elif cls == "road_waterlogging":
            for _ in range(r.randint(2, 5)):                                              # puddles on the road
                py = r.randint(s.hz + (S - s.hz) // 3, S - 6)
                pw, ph = r.randint(S // 6, S // 2), r.randint(4, 14)
                px = int(S * loc["road_x"] + r.randint(-S // 3, S // 6))
                s.d.ellipse([px, py, px + pw, py + ph], fill=(*_jit((115, 120, 130), r, 15), 225))
                s.d.line([(px + 4, py + ph // 2), (px + pw - 4, py + ph // 2)], fill=(200, 205, 215, 140), width=1)
            if r.random() < 0.5:
                s.rain(density=0.5)
        else:   # urban_flooding: murky water up to door / window level across the street
            s.water(s.hz - r.randint(-2, S // 10), _murky(r), ripple=0.5, alpha=240)
            s.debris(r.randint(0, 6), s.hz)
            if r.random() < 0.5:
                s.rain(density=0.8)
    elif cls == "river_flooding":
        s.hills(); s.ground((100, 130, 70))
        s.trees(r.randint(4, 10), y=s.hz + 6)
        s.water(s.hz + r.randint(-2, 6), _murky(r), ripple=0.35, alpha=245)            # water to the horizon
        for _ in range(r.randint(2, 6)):                                                # half-submerged trees / roofs
            x = r.randint(0, S)
            y = r.randint(s.hz + 5, S - 10)
            if r.random() < 0.5:
                s.d.ellipse([x - 7, y - 10, x + 7, y], fill=(50, 100, 45))
            else:
                s.d.polygon([(x - 10, y), (x, y - 8), (x + 10, y)], fill=(150, 60, 45))
    elif cls == "flash_flooding":
        s.hills((80, 95, 70)); s.ground((90, 80, 65))
        bank = r.randint(S // 8, S // 4)
        s.water(s.hz - 4, _murky(r), ripple=1.0, alpha=255, turbulence=r.uniform(0.6, 1.0), x0=bank // 2, x1=S - bank // 2, reflect=False)
        s.debris(r.randint(6, 18), s.hz)
        if r.random() < 0.6:
            s.rain(density=1.0)
    elif cls == "rising_water":
        s.hills(); s.ground((95, 120, 70))
        left, right = int(S * r.uniform(0.1, 0.3)), int(S * r.uniform(0.7, 0.9))
        s.d.rectangle([left - 6, s.hz, right + 6, S], fill=(110, 100, 80))              # channel banks
        s.water(s.hz + r.randint(2, 8), _murky(r), ripple=0.6, alpha=250, turbulence=0.3, x0=left, x1=right, reflect=False)
        by = s.hz + r.randint(6, 16)                                                     # bridge deck just above water
        s.d.rectangle([0, by - 4, S, by], fill=(150, 150, 150))
        for px in range(10, S, S // 4):
            s.d.rectangle([px, by, px + 4, min(S, by + 10)], fill=(130, 130, 130))
    elif cls == "landslide":
        pts = s.hills((70, 115, 60))
        s.ground((100, 125, 70))
        sx = int(S * r.uniform(0.25, 0.75))
        top = min(p[1] for p in pts) + r.randint(0, 10)
        fan = [(sx - 4, top), (sx + 4, top), (sx + r.randint(20, 40), S), (sx - r.randint(20, 40), S)]
        s.d.polygon(fan, fill=_jit((140, 105, 70), r, 15))                                # bare scar + debris fan
        for _ in range(r.randint(15, 40)):
            x, y = r.randint(sx - 35, sx + 35), r.randint(top + 10, S)
            rr = r.randint(1, 5)
            s.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=_jit((110, 100, 90), r, 25))
        if r.random() < 0.6:
            s.road(lines=False)
            s.d.polygon([(sx - 25, S - 30), (sx + 25, S - 30), (sx + 35, S), (sx - 35, S)], fill=_jit((130, 100, 70), r, 15))
        if r.random() < 0.4:
            s.rain(density=0.7)
    s.condition(cond)
    tilt = loc["tilt"] + r.uniform(-2, 2)
    return s.img.rotate(tilt, resample=Image.Resampling.BILINEAR, fillcolor=(0, 0, 0)).crop((4, 4, S - 4, S - 4)).resize((S, S))


def location_style(r: random.Random) -> dict:
    return {
        "horizon": r.uniform(0.32, 0.55), "sky_top": _jit((95, 140, 200), r, 30), "sky_bot": _jit((190, 205, 220), r, 20),
        "ground": _jit((110, 130, 80), r, 25), "hill": _jit((80, 110, 75), r, 20), "hill_freq": r.uniform(1, 4),
        "phase": r.uniform(0, 6.3), "road": _jit((95, 95, 100), r, 15), "road_x": r.uniform(0.35, 0.65),
        "n_build": r.randint(3, 8), "build_cols": [_jit(c, r, 30) for c in ((200, 190, 170), (170, 120, 100), (210, 210, 205), (150, 160, 175))],
        "tilt": r.uniform(-4, 4), "urban": r.random() < 0.6,
    }


def generate(out: Path, size: int = 160, seed: int = 7, scale: float = 1.0, n_locations: int = 120) -> Path:
    r = random.Random(seed)
    locations = {f"L{k:03d}": location_style(random.Random(seed * 1000 + k)) for k in range(n_locations)}
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for cls in CLASSES:
        n = int(COUNTS[cls] * scale)
        (out / cls).mkdir(exist_ok=True)
        k = 0
        while k < n:
            loc_id = r.choice(list(locations))
            incident = f"{cls}-{loc_id}-{r.randint(0, 10 ** 6):06d}"
            cond = r.choice(CONDITIONS)
            for _ in range(r.randint(1, 4)):                        # several shots of one incident
                if k >= n:
                    break
                img = render(cls, locations[loc_id], cond, random.Random(r.randint(0, 10 ** 9)), size)
                path = out / cls / f"{cls}_{k:05d}.png"
                img.save(path, optimize=True)
                rows.append({"path": str(path.relative_to(out)), "label": cls, "incident_id": incident, "location_id": loc_id,
                             "condition": cond, "source": "synthetic:procedural", "license": "generated (no third-party content)"})
                k += 1
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out / "manifest.csv"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="ml_data/vision/synthetic_v1")
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scale", type=float, default=1.0, help="multiply the per-class counts")
    a = ap.parse_args()
    print(generate(Path(a.out), a.size, a.seed, a.scale))
