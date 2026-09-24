"""Cylindrical surface unwrapping -- spec preprocessing/cylindrical_unwarp.py.

Bottles, jars, tins and pouches carry their mandatory declarations on a curved
label.  Photographed flat, the text compresses horizontally towards the silhouette
edges: characters near the rim can be half the width of those at the centre.

Two things break as a result. OCR accuracy collapses at the edges, and font-height
measurement -- which Rule 11 enforcement depends on -- reads short exactly where
the label curves away.

The correction models the visible label as the front half of a cylinder and
inverts the projection.  A point at angle theta on the cylinder appears at
x = R*sin(theta); unwrapping maps arc length back to a flat strip.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from preprocessing.planar_unwarp import UnwarpResult

logger = logging.getLogger("metrix.cylindrical")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False

# Fraction of the cylinder circumference assumed visible in a single frontal
# photograph. Beyond roughly 150 degrees the surface is too oblique to recover.
DEFAULT_VISIBLE_ARC_DEG = 140.0


@dataclass
class CylindricalMaps:
    """The remap lookup tables, retained so coordinates can be mapped back."""

    map_x: np.ndarray
    map_y: np.ndarray
    source_size: tuple[int, int]   # (w, h)
    output_size: tuple[int, int]   # (w, h)
    visible_arc_deg: float


def _build_maps(
    src_w: int, src_h: int, visible_arc_deg: float
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Build the inverse-projection sampling grid.

    For each output column u (uniform in arc length), find the source column x
    it was projected from:

        theta = theta_min + (u / out_w) * arc          angle on the cylinder
        x     = cx + R * sin(theta)                    where it lands in the photo

    Sampling uniformly in theta and reading from sin(theta) is what restores
    even character spacing across the label.
    """
    arc = np.radians(visible_arc_deg)
    radius = (src_w / 2.0) / np.sin(arc / 2.0)

    # Unwrapped width is the true arc length, so the output is wider than the
    # photograph -- that expansion is precisely the compression being undone.
    out_w = int(round(radius * arc))
    out_w = max(32, min(out_w, src_w * 3))
    out_h = src_h

    cx = src_w / 2.0
    theta = np.linspace(-arc / 2.0, arc / 2.0, out_w, dtype=np.float32)
    xs = cx + radius * np.sin(theta)
    xs = np.clip(xs, 0, src_w - 1).astype(np.float32)

    map_x = np.tile(xs, (out_h, 1))

    # The cylinder axis is vertical, so image height is independent of the angle
    # around the cylinder -- rows pass through unchanged. Only the horizontal
    # axis was compressed by the projection, and only that is undone here.
    map_y = np.tile(np.arange(out_h, dtype=np.float32).reshape(-1, 1), (1, out_w))

    return map_x, map_y, out_w, out_h


def unwarp(
    image: np.ndarray,
    corners: np.ndarray | None = None,
    visible_arc_deg: float = DEFAULT_VISIBLE_ARC_DEG,
) -> tuple[UnwarpResult, CylindricalMaps | None]:
    """Flatten a curved label into a fronto-parallel strip."""
    h, w = image.shape[:2]

    if not _CV2:
        return (
            UnwarpResult(
                image=image, matrix=None, inverse_matrix=None, method="none",
                output_size=(w, h), applied=False,
                reason="OpenCV unavailable; curved surface left uncorrected",
            ),
            None,
        )

    working = image
    crop_offset = (0, 0)

    # Crop to the pack before unwrapping -- background pixels would otherwise be
    # stretched along with the label and corrupt the geometry.
    if corners is not None and len(corners) == 4:
        xs, ys = corners[:, 0], corners[:, 1]
        x0, x1 = int(max(0, xs.min())), int(min(w, xs.max()))
        y0, y1 = int(max(0, ys.min())), int(min(h, ys.max()))
        if x1 - x0 > 32 and y1 - y0 > 32:
            working = image[y0:y1, x0:x1]
            crop_offset = (x0, y0)

    src_h, src_w = working.shape[:2]

    try:
        map_x, map_y, out_w, out_h = _build_maps(src_w, src_h, visible_arc_deg)
        unwrapped = cv2.remap(
            working, map_x, map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception as exc:
        logger.warning("Cylindrical unwarp failed: %s", exc)
        return (
            UnwarpResult(
                image=image, matrix=None, inverse_matrix=None, method="none",
                output_size=(w, h), applied=False, reason=f"Unwrap failed: {exc}",
            ),
            None,
        )

    maps = CylindricalMaps(
        map_x=map_x,
        map_y=map_y,
        source_size=(src_w, src_h),
        output_size=(out_w, out_h),
        visible_arc_deg=visible_arc_deg,
    )

    # The transform is a per-pixel remap, not a matrix. The parameters below are
    # what coordinate_mapper needs to invert it analytically.
    descriptor = np.array(
        [
            [visible_arc_deg, src_w, src_h],
            [out_w, out_h, crop_offset[0]],
            [crop_offset[1], 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    return (
        UnwarpResult(
            image=unwrapped,
            matrix=descriptor,
            inverse_matrix=None,
            method="cylindrical",
            output_size=(out_w, out_h),
            applied=True,
            reason=(
                f"Cylindrical label unwrapped over {visible_arc_deg:.0f} deg arc "
                f"({src_w}x{src_h} -> {out_w}x{out_h})"
            ),
        ),
        maps,
    )


def estimate_visible_arc(image: np.ndarray, corners: np.ndarray | None) -> float:
    """Estimate how much of the cylinder is in view from the pack aspect ratio.

    A tall narrow bottle shows less circumference than a squat jar. Rough, but
    materially better than assuming one fixed arc for every container.
    """
    if corners is None or len(corners) != 4:
        return DEFAULT_VISIBLE_ARC_DEG
    tl, tr, br, bl = corners
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if height <= 0:
        return DEFAULT_VISIBLE_ARC_DEG
    ratio = width / height
    # ratio 0.3 (tall bottle) -> ~110 deg ; ratio 1.2 (wide jar) -> ~165 deg
    arc = 100.0 + float(np.clip(ratio, 0.2, 1.4)) * 50.0
    return float(np.clip(arc, 100.0, 170.0))
