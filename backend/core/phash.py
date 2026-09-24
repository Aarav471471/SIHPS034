"""Perceptual hashing for evidence de-duplication -- spec core/phash.py.

SHA-256 catches byte-identical resubmissions.  It does not catch the same
photograph re-encoded, resized, or lightly recompressed -- which is exactly what
happens when an officer's phone re-saves an image, or when someone tries to pass
one shelf photo off as several separate inspections.

A perceptual hash closes that gap: visually similar images land within a small
Hamming distance of each other regardless of encoding.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger("metrix.phash")

try:
    import imagehash
    from PIL import Image

    _AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _AVAILABLE = False


@dataclass
class DuplicateMatch:
    is_duplicate: bool
    distance: int
    matched_hash: str | None = None
    reason: str | None = None


def compute_phash(image_bytes: bytes) -> str | None:
    """64-bit perceptual hash as a 16-character hex string.

    Uses pHash (DCT-based) rather than aHash: it survives brightness and
    contrast shifts, which are unavoidable across different phone cameras
    photographing the same pack under shop lighting.
    """
    if not _AVAILABLE:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return str(imagehash.phash(img.convert("RGB"), hash_size=8))
    except Exception as exc:
        logger.warning("Perceptual hash failed: %s", exc)
        return None


def hamming_distance(a: str, b: str) -> int:
    """Bit distance between two hex-encoded hashes. 64 (max) if unparseable."""
    if not a or not b or len(a) != len(b):
        return 64
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 64


def find_duplicate(
    candidate: str | None,
    existing: list[str],
    threshold: int | None = None,
) -> DuplicateMatch:
    """Check a new image's hash against previously accepted ones.

    Threshold is configurable because the right value is a policy decision:
    too tight and a legitimate re-shoot of the same panel is rejected, too loose
    and two genuinely different packs of the same SKU collide.
    """
    limit = threshold if threshold is not None else settings.PHASH_DUPLICATE_DISTANCE
    if not candidate:
        return DuplicateMatch(is_duplicate=False, distance=64)

    best_hash, best_distance = None, 64
    for other in existing:
        d = hamming_distance(candidate, other)
        if d < best_distance:
            best_distance, best_hash = d, other

    if best_distance <= limit:
        return DuplicateMatch(
            is_duplicate=True,
            distance=best_distance,
            matched_hash=best_hash,
            reason=(
                f"Perceptually identical to an image already in evidence "
                f"(Hamming distance {best_distance} <= {limit})"
            ),
        )
    return DuplicateMatch(is_duplicate=False, distance=best_distance, matched_hash=best_hash)


def similarity_percent(a: str, b: str) -> float:
    """Human-facing similarity, 0-100."""
    return round((1 - hamming_distance(a, b) / 64) * 100, 1)
