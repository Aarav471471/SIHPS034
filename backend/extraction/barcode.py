"""Barcode detection -- spec extraction/barcode.py.

A decoded barcode is the strongest identity signal on a pack: it links this
physical article to the product catalogue, to its verified MRP, and to the
price-history series the gouging radar runs on.  Without it, a consumer scan
has nothing to compare against.

pyzbar is preferred (it decodes the widest range of symbologies) with OpenCV's
built-in detector as a fallback, since pyzbar needs the native libzbar library
that is not present everywhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("metrix.barcode")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False

try:
    from pyzbar import pyzbar

    # Importing succeeds even when libzbar is missing; decoding is the real test.
    pyzbar.decode(np.zeros((8, 8), dtype=np.uint8))
    _PYZBAR = True
except Exception:  # pragma: no cover - optional native dependency
    _PYZBAR = False


@dataclass
class BarcodeResult:
    data: str | None
    symbology: str | None
    bbox: tuple[int, int, int, int] | None
    decoder: str
    confidence: float = 0.0
    checksum_valid: bool | None = None
    note: str = ""

    @property
    def found(self) -> bool:
        return bool(self.data)


def _preprocess_variants(image: np.ndarray) -> list[np.ndarray]:
    """Progressively harder attempts at making a barcode readable.

    Shelf photographs are the difficult case: the code may be small, low
    contrast, slightly rotated, or printed on a curved surface. Trying a few
    cheap variants recovers a meaningful share of otherwise-failed scans.
    """
    if not _CV2:
        return [image]
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    variants = [gray]

    variants.append(cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray))
    _t, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)
    variants.append(cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 9
    ))

    # Upscale: thin bars in a distant photo fall below the decoder's resolution.
    if max(gray.shape) < 1600:
        variants.append(cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC))

    sharpened = cv2.addWeighted(gray, 1.6, cv2.GaussianBlur(gray, (0, 0), 3), -0.6, 0)
    variants.append(sharpened)
    return variants


def _decode_pyzbar(image: np.ndarray) -> BarcodeResult | None:
    for variant in _preprocess_variants(image):
        try:
            found = pyzbar.decode(variant)
        except Exception as exc:
            logger.debug("pyzbar decode error: %s", exc)
            return None
        for sym in found:
            try:
                data = sym.data.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if not data:
                continue
            r = sym.rect
            scale = image.shape[1] / variant.shape[1] if variant.shape[1] else 1.0
            return BarcodeResult(
                data=data,
                symbology=sym.type,
                bbox=(int(r.left * scale), int(r.top * scale),
                      int(r.width * scale), int(r.height * scale)),
                decoder="pyzbar",
                confidence=0.99,   # a decoded symbol carries its own checksum
                note=f"Decoded {sym.type} symbol",
            )
    return None


def _decode_opencv(image: np.ndarray) -> BarcodeResult | None:
    if not _CV2:
        return None
    try:
        detector = cv2.barcode.BarcodeDetector()
    except AttributeError:
        return None

    for variant in _preprocess_variants(image):
        src = cv2.cvtColor(variant, cv2.COLOR_GRAY2BGR) if variant.ndim == 2 else variant
        try:
            ok, decoded, types, points = detector.detectAndDecodeWithType(src)
        except Exception as exc:
            logger.debug("OpenCV barcode error: %s", exc)
            continue
        if not ok or not decoded:
            continue
        for i, data in enumerate(decoded):
            if not data:
                continue
            bbox = None
            if points is not None and len(points) > i:
                pts = np.array(points[i]).reshape(-1, 2)
                scale = image.shape[1] / variant.shape[1] if variant.shape[1] else 1.0
                x, y = int(pts[:, 0].min() * scale), int(pts[:, 1].min() * scale)
                w = int((pts[:, 0].max() - pts[:, 0].min()) * scale)
                h = int((pts[:, 1].max() - pts[:, 1].min()) * scale)
                bbox = (x, y, max(1, w), max(1, h))
            return BarcodeResult(
                data=str(data).strip(),
                symbology=str(types[i]) if types is not None and len(types) > i else "UNKNOWN",
                bbox=bbox,
                decoder="opencv",
                confidence=0.95,
                note="Decoded by the OpenCV barcode detector",
            )
    return None


def detect(image: np.ndarray) -> BarcodeResult:
    """Find and decode the first readable barcode on a surface."""
    from extraction.gs1_validator import validate_ean

    for decoder, fn in (("pyzbar", _decode_pyzbar if _PYZBAR else None),
                        ("opencv", _decode_opencv)):
        if fn is None:
            continue
        try:
            result = fn(image)
        except Exception as exc:
            logger.warning("%s decoder raised: %s", decoder, exc)
            continue
        if result and result.found:
            check = validate_ean(result.data)
            result.checksum_valid = check.checksum_valid
            if check.checksum_valid is False:
                # A failed check digit means the digits were misread, or the
                # symbol is counterfeit. Either way it must not be trusted as
                # a product identity.
                result.confidence = min(result.confidence, 0.4)
                result.note += " -- check digit FAILED; identity not trustworthy"
            return result

    return BarcodeResult(
        data=None, symbology=None, bbox=None,
        decoder="pyzbar" if _PYZBAR else "opencv",
        note=(
            "No barcode located on this surface"
            if _PYZBAR or _CV2
            else "No barcode decoder available (install pyzbar with libzbar)"
        ),
    )


def decoder_status() -> dict:
    return {
        "pyzbar": _PYZBAR,
        "opencv_barcode": _CV2 and hasattr(cv2, "barcode"),
        "preferred": "pyzbar" if _PYZBAR else ("opencv" if _CV2 else "none"),
    }
