"""Four-point perspective rectification -- spec preprocessing/planar_unwarp.py.

An officer photographing a carton on a shelf never gets a square-on shot.  The
resulting keystone distortion makes text on the far edge smaller than text on
the near edge, which would systematically bias font-height measurement -- the
exact thing Rule 11 findings depend on.

A homography derived from the four detected corners removes it.  The matrix is
kept so every bounding box found in the rectified image can be mapped back to
original camera pixels for the evidence crop.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("metrix.planar")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False


@dataclass
class UnwarpResult:
    image: np.ndarray
    matrix: np.ndarray | None            # 3x3 forward homography (orig -> rectified)
    inverse_matrix: np.ndarray | None    # 3x3 (rectified -> orig)
    method: str
    output_size: tuple[int, int]         # (w, h)
    applied: bool
    reason: str = ""

    def matrix_as_json(self) -> dict | None:
        """Serialisable form for the session_images.transformation_matrix column."""
        if self.matrix is None:
            return None
        return {
            "method": self.method,
            "forward": self.matrix.tolist(),
            "inverse": self.inverse_matrix.tolist() if self.inverse_matrix is not None else None,
            "output_size": list(self.output_size),
        }


def _target_size(corners: np.ndarray) -> tuple[int, int]:
    """Output dimensions preserving the pack's true aspect ratio.

    The longer of each opposing pair is used: foreshortening only ever shrinks
    an edge, so the maximum is the closest estimate of real extent.
    """
    tl, tr, br, bl = corners
    width = max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))
    height = max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))
    return max(int(round(width)), 32), max(int(round(height)), 32)


def unwarp(image: np.ndarray, corners: np.ndarray | None) -> UnwarpResult:
    """Rectify a flat pack face to a fronto-parallel view."""
    h, w = image.shape[:2]

    if not _CV2 or corners is None or len(corners) != 4:
        return UnwarpResult(
            image=image, matrix=None, inverse_matrix=None, method="none",
            output_size=(w, h), applied=False,
            reason="No four-corner geometry available; original retained",
        )

    out_w, out_h = _target_size(corners)

    # Refuse absurd rectifications -- a bad corner detection can otherwise
    # produce a 30000px canvas and exhaust memory.
    if out_w > 8000 or out_h > 8000 or out_w * out_h > 40_000_000:
        return UnwarpResult(
            image=image, matrix=None, inverse_matrix=None, method="none",
            output_size=(w, h), applied=False,
            reason=f"Rejected implausible rectification target {out_w}x{out_h}",
        )

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )

    try:
        matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
        rectified = cv2.warpPerspective(
            image, matrix, (out_w, out_h),
            flags=cv2.INTER_CUBIC,           # text quality matters more than speed
            borderMode=cv2.BORDER_REPLICATE,
        )
        inverse = np.linalg.inv(matrix)
    except Exception as exc:
        logger.warning("Planar unwarp failed: %s", exc)
        return UnwarpResult(
            image=image, matrix=None, inverse_matrix=None, method="none",
            output_size=(w, h), applied=False, reason=f"Homography failed: {exc}",
        )

    return UnwarpResult(
        image=rectified,
        matrix=matrix,
        inverse_matrix=inverse,
        method="planar",
        output_size=(out_w, out_h),
        applied=True,
        reason=f"Perspective corrected via 4-point homography to {out_w}x{out_h}",
    )


def deskew(image: np.ndarray, max_angle: float = 15.0) -> tuple[np.ndarray, float]:
    """Correct small residual rotation using dominant text-line orientation.

    Applied after rectification: homography squares the pack, but the printed
    text can still sit at a slight angle, and OCR accuracy is sensitive to that.
    """
    if not _CV2:
        return image, 0.0
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=120, minLineLength=gray.shape[1] // 4, maxLineGap=20
        )
        if lines is None:
            return image, 0.0

        angles = []
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) <= max_angle:
                angles.append(angle)
        if not angles:
            return image, 0.0

        # Median, not mean: a few spurious long edges must not drag the estimate.
        skew = float(np.median(angles))
        if abs(skew) < 0.3:
            return image, 0.0

        h, w = image.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), skew, 1.0)
        rotated = cv2.warpAffine(
            image, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return rotated, round(skew, 3)
    except Exception as exc:
        logger.debug("Deskew skipped: %s", exc)
        return image, 0.0
