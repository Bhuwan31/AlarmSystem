"""Image validation, EXIF time/GPS extraction, duplicate hashes and model preprocessing (Pillow + numpy only)."""
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

ALLOWED = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_PIXELS = 40_000_000           # decompression-bomb guard
MIN_SIDE = 64
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# EXIF tag numbers
_EXIF_IFD, _GPS_IFD = 0x8769, 0x8825
_DATETIME_ORIGINAL, _OFFSET_ORIGINAL, _DATETIME = 0x9003, 0x9011, 0x0132
_MAKE, _MODEL = 0x010F, 0x0110


class ImageRejected(ValueError):
    pass


@dataclass
class ImageInfo:
    mime: str
    width: int
    height: int
    bytes: int
    sha256: str
    dhash: str
    exif: dict = field(default_factory=dict)
    capture_time: datetime | None = None
    capture_time_source: str = "unknown"          # exif | exif_assumed_tz | unknown
    gps: tuple[float, float] | None = None
    gps_accuracy_m: float | None = None


def validate(data: bytes, max_bytes: int) -> Image.Image:
    if len(data) == 0:
        raise ImageRejected("empty file")
    if len(data) > max_bytes:
        raise ImageRejected(f"file is larger than {max_bytes // (1024 * 1024)} MB")
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()                                        # structural check; image must be reopened after verify
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError as e:
        raise ImageRejected("image has too many pixels") from e
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise ImageRejected("not a readable image") from e
    if fmt not in ALLOWED:
        raise ImageRejected(f"unsupported format {fmt}; use JPEG, PNG or WebP")
    if min(img.size) < MIN_SIDE:
        raise ImageRejected(f"image is too small (minimum {MIN_SIDE} px per side)")
    return img


def _rational(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        if isinstance(v, tuple) and len(v) == 2 and v[1]:
            return v[0] / v[1]
        raise


def _dms(values, ref) -> float | None:
    try:
        d, m, s = (_rational(x) for x in values)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    deg = d + m / 60 + s / 3600
    return -deg if str(ref).upper() in ("S", "W") else deg


def _parse_offset(s: str | None) -> timezone | None:
    if not s:
        return None
    s = s.strip()
    try:
        sign = -1 if s[0] == "-" else 1
        hh, mm = s.lstrip("+-").split(":")
        return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    except (ValueError, IndexError):
        return None


def read_exif(img: Image.Image, client_tz: timezone | None = None) -> dict:
    """Capture time (with timezone) and GPS from EXIF. Returns {} entries for what is missing; never guesses GPS."""
    out: dict = {}
    try:
        ex = img.getexif()
    except Exception:  # noqa: BLE001 - malformed EXIF must not fail the upload
        return out
    if not ex:
        return out
    try:
        sub = ex.get_ifd(_EXIF_IFD)
    except Exception:  # noqa: BLE001
        sub = {}
    raw_dt = sub.get(_DATETIME_ORIGINAL) or ex.get(_DATETIME)
    if raw_dt:
        try:
            naive = datetime.strptime(str(raw_dt).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
            tz = _parse_offset(sub.get(_OFFSET_ORIGINAL))
            if tz is not None:
                out["capture_time"], out["capture_time_source"] = naive.replace(tzinfo=tz), "exif"
            elif client_tz is not None:
                # Camera stored local time without an offset: assume the uploader's timezone and say so.
                out["capture_time"], out["capture_time_source"] = naive.replace(tzinfo=client_tz), "exif_assumed_tz"
            out["raw_datetime"] = str(raw_dt)
        except ValueError:
            pass
    for tag, key in ((_MAKE, "camera_make"), (_MODEL, "camera_model")):
        if ex.get(tag):
            out[key] = str(ex.get(tag)).strip("\x00 ")[:60]
    try:
        gps = ex.get_ifd(_GPS_IFD)
    except Exception:  # noqa: BLE001
        gps = {}
    if gps and 2 in gps and 4 in gps:
        lat, lon = _dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E"))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
            out["gps"] = (round(lat, 6), round(lon, 6))
            if 31 in gps:                                   # GPSHPositioningError, metres
                try:
                    out["gps_accuracy_m"] = round(_rational(gps[31]), 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            elif 11 in gps:                                 # GPSDOP → rough metres (DOP × 5 m)
                try:
                    out["gps_accuracy_m"] = round(_rational(gps[11]) * 5, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
    return out


def dhash(img: Image.Image, size: int = 8) -> str:
    g = ImageOps.exif_transpose(img).convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def inspect(data: bytes, max_bytes: int, client_tz: timezone | None = None) -> tuple[Image.Image, ImageInfo]:
    img = validate(data, max_bytes)
    meta = read_exif(img, client_tz)
    info = ImageInfo(mime=ALLOWED[img.format], width=img.width, height=img.height, bytes=len(data),
                     sha256=hashlib.sha256(data).hexdigest(), dhash=dhash(img),
                     capture_time=meta.get("capture_time"), capture_time_source=meta.get("capture_time_source", "unknown"),
                     gps=meta.get("gps"), gps_accuracy_m=meta.get("gps_accuracy_m"))
    info.exif = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in meta.items()}
    return img, info


def preview_jpeg(img: Image.Image, max_side: int = 1280) -> bytes:
    """Re-encoded copy for reviewers: orientation applied, EXIF (incl. GPS) stripped."""
    im = ImageOps.exif_transpose(img).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)   # fixed constants, not ImageNet weights
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def to_array(img: Image.Image, size: int) -> np.ndarray:
    """Model input (3, size, size) float32: orientation fixed, centre-cropped square, resized, normalised."""
    im = ImageOps.exif_transpose(img).convert("RGB")
    im = ImageOps.fit(im, (size, size), Image.Resampling.BILINEAR)
    a = np.asarray(im, dtype=np.float32) / 255.0
    return ((a - MEAN) / STD).transpose(2, 0, 1).copy()


def exif_bytes_for_test(lat: float, lon: float, when: datetime, accuracy_m: float | None = None) -> bytes:
    """EXIF block with GPS and DateTimeOriginal (+offset), for tests and the end-to-end simulation."""
    ex = Image.Exif()
    sub = ex.get_ifd(_EXIF_IFD)
    sub[_DATETIME_ORIGINAL] = when.strftime("%Y:%m:%d %H:%M:%S")
    off = when.utcoffset() or timedelta(0)
    mins = int(off.total_seconds() // 60)
    sub[_OFFSET_ORIGINAL] = f"{'+' if mins >= 0 else '-'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"

    from PIL.TiffImagePlugin import IFDRational

    def dms(v):
        v = abs(v)
        d = int(v)
        m = int((v - d) * 60)
        s = round(((v - d) * 60 - m) * 60 * 100)
        return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(s, 100))
    gps = ex.get_ifd(_GPS_IFD)
    gps[1], gps[2] = ("N" if lat >= 0 else "S"), dms(lat)
    gps[3], gps[4] = ("E" if lon >= 0 else "W"), dms(lon)
    if accuracy_m is not None:
        gps[31] = IFDRational(int(accuracy_m * 10), 10)
    return ex.tobytes()


_ = ExifTags  # keep the import for readers looking up tag numbers
