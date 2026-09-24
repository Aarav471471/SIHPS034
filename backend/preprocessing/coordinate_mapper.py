"""Inverse coordinate mapping -- spec preprocessing/coordinate_mapper.py.

The vision model and OCR both work on the *rectified* image, so every bounding
box they return is in rectified space.  A legal notice, however, must cite the
officer's original photograph -- an unedited, hash-sealed capture -- not a
machine-transformed derivative a defence lawyer can challenge.

This module inverts each transform so a rectified box becomes a polygon in
original camera pixels:

    planar       exact, via the inverse homography
    cylindrical  analytic inversion of the sin(theta) projection
    none         identity

The mapped region is returned as a full quadrilateral as well as an axis-aligned
box, because inverting perspective turns a rectangle into a general quad and
flattening that to a rectangle too early loses evidence fidelity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("metrix.coords")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False


@dataclass
class BBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    def corners(self) -> np.ndarray:
        return np.array(
            [[self.x, self.y], [self.x2, self.y], [self.x2, self.y2], [self.x, self.y2]],
            dtype=np.float32,
        )

    def clamp(self, width: int, height: int) -> "BBox":
        x = max(0, min(self.x, width - 1))
        y = max(0, min(self.y, height - 1))
        return BBox(x, y, max(1, min(self.width, width - x)), max(1, min(self.height, height - y)))

    def pad(self, px: int) -> "BBox":
        return BBox(self.x - px, self.y - px, self.width + 2 * px, self.height + 2 * px)


@dataclass
class MappedRegion:
    """A rectified-space box expressed back in original image pixels."""

    bbox: BBox                      # axis-aligned bounds in the original image
    polygon: list[list[int]]        # the true quadrilateral, 4 x [x, y]
    method: str
    exact: bool                     # False when the inversion is approximate
    note: str = ""


class CoordinateMapper:
    """Inverts whatever transform preprocessing applied to one surface."""

    def __init__(
        self,
        method: str,
        transform: dict[str, Any] | np.ndarray | None,
        original_size: tuple[int, int],
        rectified_size: tuple[int, int],
    ) -> None:
        self.method = method or "none"
        self.original_size = original_size      # (w, h)
        self.rectified_size = rectified_size    # (w, h)
        self._inverse: np.ndarray | None = None
        self._cyl: dict[str, float] | None = None

        if self.method == "planar":
            self._load_planar(transform)
        elif self.method == "cylindrical":
            self._load_cylindrical(transform)

    # ------------------------------------------------------------ loading --
    def _load_planar(self, transform) -> None:
        try:
            if isinstance(transform, dict):
                inv = transform.get("inverse")
                fwd = transform.get("forward")
                if inv is not None:
                    self._inverse = np.array(inv, dtype=np.float64)
                elif fwd is not None:
                    self._inverse = np.linalg.inv(np.array(fwd, dtype=np.float64))
            elif transform is not None:
                self._inverse = np.linalg.inv(np.asarray(transform, dtype=np.float64))
        except Exception as exc:
            logger.warning("Planar inverse unavailable: %s", exc)
            self._inverse = None

    def _load_cylindrical(self, transform) -> None:
        """Recover the unwrap parameters stored in the descriptor matrix."""
        try:
            m = (
                np.array(transform.get("forward"), dtype=np.float64)
                if isinstance(transform, dict)
                else np.asarray(transform, dtype=np.float64)
            )
            self._cyl = {
                "arc_deg": float(m[0][0]),
                "src_w": float(m[0][1]),
                "src_h": float(m[0][2]),
                "out_w": float(m[1][0]),
                "out_h": float(m[1][1]),
                "offset_x": float(m[1][2]),
                "offset_y": float(m[2][0]),
            }
        except Exception as exc:
            logger.warning("Cylindrical parameters unavailable: %s", exc)
            self._cyl = None

    # ----------------------------------------------------------- mapping ---
    def _map_point_planar(self, x: float, y: float) -> tuple[float, float]:
        v = self._inverse @ np.array([x, y, 1.0], dtype=np.float64)
        w = v[2] if abs(v[2]) > 1e-12 else 1e-12
        return float(v[0] / w), float(v[1] / w)

    def _map_point_cylindrical(self, x: float, y: float) -> tuple[float, float]:
        """Invert the unwrap: output column -> angle -> source column.

        Forward was  x_src = cx + R*sin(theta),  theta uniform across out_w.
        So going back is a direct evaluation -- no numeric search needed.
        """
        c = self._cyl
        arc = np.radians(c["arc_deg"])
        radius = (c["src_w"] / 2.0) / np.sin(arc / 2.0)
        cx = c["src_w"] / 2.0
        cy = c["src_h"] / 2.0

        theta = -arc / 2.0 + (x / max(c["out_w"], 1.0)) * arc
        src_x = cx + radius * np.sin(theta)

        # Vertical axis is unchanged by the projection (see cylindrical_unwarp).
        src_y = y

        # Undo the pre-unwrap crop to land in full original-image coordinates.
        return src_x + c["offset_x"], src_y + c["offset_y"]

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        if self.method == "planar" and self._inverse is not None:
            return self._map_point_planar(x, y)
        if self.method == "cylindrical" and self._cyl is not None:
            return self._map_point_cylindrical(x, y)
        return float(x), float(y)

    def map_bbox(self, bbox: BBox) -> MappedRegion:
        """Map a rectified-space box back to the original photograph."""
        ow, oh = self.original_size

        if self.method == "none" or (self._inverse is None and self._cyl is None):
            clamped = bbox.clamp(ow, oh)
            return MappedRegion(
                bbox=clamped,
                polygon=clamped.corners().astype(int).tolist(),
                method="none",
                exact=True,
                note="No transform was applied; coordinates are already original",
            )

        # Sample along the edges, not just the corners: under a strong
        # cylindrical inversion the edges bow, and corner-only mapping would
        # crop through the text it is supposed to evidence.
        pts: list[tuple[float, float]] = []
        steps = 8
        for i in range(steps + 1):
            t = i / steps
            pts.append((bbox.x + t * bbox.width, bbox.y))                 # top
            pts.append((bbox.x + t * bbox.width, bbox.y + bbox.height))   # bottom
            pts.append((bbox.x, bbox.y + t * bbox.height))                # left
            pts.append((bbox.x + bbox.width, bbox.y + t * bbox.height))   # right

        mapped = [self.map_point(px, py) for px, py in pts]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]

        x0, x1 = int(np.floor(min(xs))), int(np.ceil(max(xs)))
        y0, y1 = int(np.floor(min(ys))), int(np.ceil(max(ys)))
        box = BBox(x0, y0, max(1, x1 - x0), max(1, y1 - y0)).clamp(ow, oh)

        corners = [self.map_point(*c) for c in bbox.corners()]
        polygon = [[int(round(cx)), int(round(cy))] for cx, cy in corners]

        return MappedRegion(
            bbox=box,
            polygon=polygon,
            method=self.method,
            exact=self.method == "planar",
            note=(
                "Exact inverse homography"
                if self.method == "planar"
                else "Analytic inversion of the cylindrical projection"
            ),
        )


def crop_region(
    image: np.ndarray, bbox: BBox, padding: int = 8
) -> np.ndarray:
    """Extract an evidence crop with a little context around it.

    The padding is deliberate: a crop cut flush to the glyphs looks cherry-picked.
    Showing the declaration in its printed surroundings is more convincing and
    harder to dispute.
    """
    h, w = image.shape[:2]
    b = bbox.pad(padding).clamp(w, h)
    return image[b.y : b.y2, b.x : b.x2]


def draw_annotation(
    image: np.ndarray,
    polygon: list[list[int]],
    label: str,
    colour: tuple[int, int, int] = (220, 38, 38),
    thickness: int = 3,
) -> np.ndarray:
    """Outline a cited region on a copy of the original photograph."""
    if not _CV2:
        return image
    out = image.copy()
    pts = np.array(polygon, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(out, [pts], isClosed=True, color=colour, thickness=thickness)

    if label:
        x, y = polygon[0]
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(out, (x, max(0, y - th - 10)), (x + tw + 8, y), colour, -1)
        cv2.putText(
            out, label, (x + 4, max(12, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA,
        )
    return out


def measure_ink_height_px(crop: np.ndarray, min_coverage: float = 0.02) -> float | None:
    """Measure the true glyph height inside a text box, in pixels.

    OCR bounding boxes are detection regions, not tight ink extents -- they
    carry several pixels of padding. Taking the box height as the character
    height therefore over-measures, and Rule 11 findings are decided by exactly
    that number: a declaration printed at 1.4 mm can be reported as 1.9 mm and
    silently pass a 2.0 mm requirement.

    This finds the rows that actually contain ink, which is what the Rule means
    by the height of a numeral or letter.
    """
    if not _CV2 or crop is None or crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return None

    # Otsu separates ink from substrate without assuming either is darker.
    _t, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Printing is dark on light far more often than the reverse; if the
    # "ink" covers most of the crop the polarity was inverted.
    if np.count_nonzero(binary) > 0.6 * binary.size:
        binary = cv2.bitwise_not(binary)

    row_coverage = binary.sum(axis=1) / (255.0 * binary.shape[1])
    inked = np.flatnonzero(row_coverage > min_coverage)
    if inked.size < 2:
        return None

    return float(inked[-1] - inked[0] + 1)


def font_height_mm(
    bbox_height_px: float,
    px_per_mm: float | None,
    box_kind: str = "ink",
) -> float | None:
    """Convert a text box height in pixels to millimetres.

    Rule 11 sets minimum heights for *numerals and letters* -- i.e. cap height,
    not the typographic em. Which correction applies depends on what produced
    the box, and conflating the two silently mis-measures by ~30%:

      ``ink``  a tight box around the rendered glyphs, which is what OCR and
               vision models return. For text of digits and capitals its height
               already *is* the cap height, so no correction is applied.
      ``em``   a full font line box including ascender and descender space, as
               a layout engine would report. Cap height is ~70% of it.

    Returns None rather than guessing when no physical scale is known -- an
    unfounded measurement in a legal notice is worse than no measurement.
    """
    if not px_per_mm or px_per_mm <= 0 or bbox_height_px <= 0:
        return None
    factor = 0.7 if box_kind == "em" else 1.0
    return round((bbox_height_px * factor) / px_per_mm, 2)
