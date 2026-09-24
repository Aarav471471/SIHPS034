"""EXIF orientation correction -- spec preprocessing/exif.py.

Phone cameras record the sensor image unrotated and store the intended
orientation as an EXIF tag.  Libraries that ignore that tag see a sideways
photograph, which wrecks contour analysis and makes every bounding box wrong.

Correcting orientation first -- and recording what was applied -- is what keeps
the crop coordinates in the final legal notice trustworthy.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("metrix.exif")

try:
    from PIL import ExifTags, Image, ImageOps

    _PIL = True
except ImportError:  # pragma: no cover
    _PIL = False

# EXIF orientation tag -> (rotation degrees CCW, mirrored)
ORIENTATION_MAP: dict[int, tuple[int, bool]] = {
    1: (0, False),
    2: (0, True),
    3: (180, False),
    4: (180, True),
    5: (270, True),
    6: (270, False),
    7: (90, True),
    8: (90, False),
}


@dataclass
class ExifResult:
    image: np.ndarray                 # RGB ndarray, upright
    orientation_tag: int | None
    rotation_applied: int
    mirrored: bool
    original_size: tuple[int, int]    # (w, h) as stored
    corrected_size: tuple[int, int]   # (w, h) after correction
    captured_at: str | None = None
    gps: tuple[float, float] | None = None
    camera: str | None = None


def _rational(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return value[0] / value[1]
        except Exception:
            return 0.0


def _gps_from_exif(exif: dict) -> tuple[float, float] | None:
    """Decode GPSInfo into signed decimal degrees.

    Worth having: a photograph carrying its own coordinates is independent
    corroboration of where an inspection happened, separate from whatever the
    client app reported.
    """
    gps = exif.get("GPSInfo")
    if not isinstance(gps, dict):
        return None
    try:
        tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        lat_dms, lat_ref = tags.get("GPSLatitude"), tags.get("GPSLatitudeRef")
        lng_dms, lng_ref = tags.get("GPSLongitude"), tags.get("GPSLongitudeRef")
        if not (lat_dms and lng_dms):
            return None

        def to_deg(dms) -> float:
            d, m, s = (_rational(x) for x in dms)
            return d + m / 60 + s / 3600

        lat, lng = to_deg(lat_dms), to_deg(lng_dms)
        if str(lat_ref).upper().startswith("S"):
            lat = -lat
        if str(lng_ref).upper().startswith("W"):
            lng = -lng
        return round(lat, 7), round(lng, 7)
    except Exception as exc:
        logger.debug("GPS EXIF decode failed: %s", exc)
        return None


def correct_orientation(image_bytes: bytes) -> ExifResult:
    """Load bytes into an upright RGB ndarray, reporting what was applied."""
    if not _PIL:
        raise RuntimeError("Pillow is required for image ingestion")

    with Image.open(io.BytesIO(image_bytes)) as img:
        original_size = img.size

        orientation_tag = None
        captured_at = None
        camera = None
        gps = None
        try:
            raw = img.getexif()
            if raw:
                exif = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()}
                orientation_tag = exif.get("Orientation")
                captured_at = exif.get("DateTimeOriginal") or exif.get("DateTime")
                make, model = exif.get("Make"), exif.get("Model")
                camera = " ".join(str(x).strip() for x in (make, model) if x) or None
                # GPSInfo needs the dedicated IFD accessor on modern Pillow
                try:
                    gps_ifd = raw.get_ifd(0x8825)
                    if gps_ifd:
                        exif["GPSInfo"] = dict(gps_ifd)
                except Exception:
                    pass
                gps = _gps_from_exif(exif)
        except Exception as exc:
            logger.debug("EXIF read failed: %s", exc)

        # exif_transpose applies the tag correctly for all 8 orientations,
        # including the mirrored ones people forget about.
        upright = ImageOps.exif_transpose(img) or img
        upright = upright.convert("RGB")
        corrected_size = upright.size
        arr = np.asarray(upright, dtype=np.uint8)

    rotation, mirrored = ORIENTATION_MAP.get(orientation_tag or 1, (0, False))

    return ExifResult(
        image=arr,
        orientation_tag=orientation_tag,
        rotation_applied=rotation,
        mirrored=mirrored,
        original_size=original_size,
        corrected_size=corrected_size,
        captured_at=str(captured_at) if captured_at else None,
        gps=gps,
        camera=camera,
    )


def to_bytes(image: np.ndarray, fmt: str = "PNG", quality: int = 95) -> bytes:
    """Encode an RGB ndarray back to bytes for storage."""
    if not _PIL:
        raise RuntimeError("Pillow is required for image encoding")
    buf = io.BytesIO()
    pil = Image.fromarray(image.astype(np.uint8))
    if fmt.upper() in ("JPG", "JPEG"):
        pil.save(buf, format="JPEG", quality=quality, optimize=True)
    else:
        pil.save(buf, format=fmt.upper())
    return buf.getvalue()
