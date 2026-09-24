"""Pack detection and curvature analysis -- spec preprocessing/contour.py.

Decides the single most consequential thing in preprocessing: is this pack a
flat carton or a curved bottle/pouch?  The answer selects planar homography or
cylindrical unwarping, and choosing wrong distorts every measurement taken
afterwards -- including the font heights that Rule 11 findings rest on.

The primary signal is *shading*, not silhouette shape.  A bottle photographed
straight on still has a rectangular outline -- its label spans the whole visible
arc -- so shape alone scores it as flat.  What a cylinder cannot hide is that its
surface turns away from the light towards both edges, producing a symmetric
brightness falloff no flat carton exhibits.  Silhouette geometry corroborates,
and supplies the corners that rectification is keyed to.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("metrix.contour")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False

PLANAR = "planar"
CYLINDRICAL = "cylindrical"
NONE = "none"

# Above this, the silhouette is bowing enough to treat as a curved surface.
CURVATURE_THRESHOLD = 0.35


@dataclass
class ContourResult:
    method: str                                  # planar | cylindrical | none
    curvature_score: float                       # 0 (flat) .. 1 (strongly curved)
    corners: np.ndarray | None = None            # 4x2 float32, TL TR BR BL
    contour_area_ratio: float = 0.0              # pack area / image area
    detected: bool = False
    reason: str = ""
    diagnostics: dict = field(default_factory=dict)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left.

    Sum (x+y) is extremal at TL/BR; difference (y-x) is extremal at TR/BL.
    Robust to rotation up to ~45 degrees, which is all a handheld capture needs.
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [
            pts[np.argmin(s)],   # TL
            pts[np.argmin(d)],   # TR
            pts[np.argmax(s)],   # BR
            pts[np.argmax(d)],   # BL
        ],
        dtype=np.float32,
    )


def _largest_pack_contour(gray: np.ndarray) -> np.ndarray | None:
    """Find the dominant foreground object.

    Several segmentations are tried because inspection photographs vary wildly.
    The hard case is a pale pack on a pale counter: the silhouette edge can be a
    dozen grey levels, far below what a fixed Canny threshold sees, while the
    pack's own printed artwork is high-contrast. A detector that only follows
    strong edges then locks onto a colour band *inside* the label and reports a
    fragment of the pack as the whole pack -- which silently corrupts both
    rectification and the px/mm scale every font-height finding depends on.

    Contrast is therefore equalised before edge detection, and the largest
    plausible contour across all strategies wins.
    """
    h, w = gray.shape[:2]
    image_area = float(h * w)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    # CLAHE lifts a faint pack-vs-background boundary into detectable range
    # without blowing out the already-strong internal edges.
    equalised = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(blurred)

    candidates: list[np.ndarray] = []

    def collect(mask: np.ndarray) -> None:
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
        )
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates.extend(cnts)

    # Strategy A -- Otsu on both the raw and equalised image, both polarities
    # (the pack may be lighter or darker than what it sits on).
    for source in (blurred, equalised):
        for flag in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
            _t, binary = cv2.threshold(source, 0, 255, flag + cv2.THRESH_OTSU)
            collect(binary)

    # Strategy B -- auto-tuned Canny on the equalised image. Thresholds are
    # derived from the median so they adapt to exposure instead of assuming it.
    median = float(np.median(equalised))
    lower = int(max(10, 0.55 * median))
    upper = int(min(255, 1.25 * median))
    edges = cv2.Canny(equalised, lower, upper)
    collect(cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2))

    # Strategy C -- gradient magnitude thresholded at a high percentile. Catches
    # a soft silhouette boundary that survives neither Otsu nor Canny.
    gx = cv2.Sobel(equalised, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(equalised, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    cutoff = float(np.percentile(mag, 92))
    collect(cv2.dilate((mag > cutoff).astype(np.uint8) * 255,
                       np.ones((7, 7), np.uint8), iterations=2))

    if not candidates:
        return None

    # Reject noise-sized blobs, and anything that is effectively the whole
    # frame. The upper bound matters more than it looks: a contour spanning the
    # entire image has swallowed the background, and the scene's own lighting
    # falloff then reads as curvature shading -- turning a flat carton into a
    # phantom cylinder. A genuine pack photo always leaves some surround.
    viable = [
        c for c in candidates
        if 0.05 * image_area < cv2.contourArea(c) < 0.92 * image_area
    ]
    if not viable:
        return None
    return max(viable, key=cv2.contourArea)


def _shading_curvature(gray: np.ndarray, cnt: np.ndarray) -> tuple[float, dict]:
    """Measure curvature from the pack's horizontal luminance profile.

    This is the reliable signal, and silhouette shape is not. A bottle label
    photographed straight on still has a rectangular outline -- the label spans
    the whole visible arc -- so a shape-based test scores it as flat.

    What a cylinder cannot hide is its shading. Its surface normal turns away
    from the light towards each edge, so brightness falls off roughly as
    cos(theta): a pronounced bright band down the middle with both edges
    markedly darker. A flat carton has no such structure.

    The per-column 90th percentile is used rather than the mean so the
    measurement tracks the substrate's brightness and is not dragged around by
    how much dark text happens to sit in each column.
    """
    x, y, w, h = cv2.boundingRect(cnt)
    if w < 40 or h < 40:
        return 0.0, {"shading": "region too small"}

    region = gray[y : y + h, x : x + w].astype(np.float32)
    profile = np.percentile(region, 90, axis=0)          # brightness per column

    # Smooth over ~5% of the width to suppress artwork bands. Edge-padding
    # before convolving keeps the outermost columns valid -- they carry the
    # strongest curvature signal and trimming them would throw it away.
    k = max(3, (w // 20) | 1)
    padded = np.pad(profile, k, mode="edge")
    profile = np.convolve(padded, np.ones(k) / k, mode="same")[k:-k]
    n = profile.size
    if n < 24:
        return 0.0, {"shading": "profile too short"}

    centre = float(np.mean(profile[int(n * 0.35) : int(n * 0.65)]))
    left = float(np.mean(profile[: max(1, int(n * 0.12))]))
    right = float(np.mean(profile[int(n * 0.88) :]))
    if centre <= 1e-6:
        return 0.0, {"shading": "degenerate"}

    drop_l = (centre - left) / centre
    drop_r = (centre - right) / centre

    # Both edges must be darker. A one-sided gradient is directional lighting
    # across a flat pack, not curvature, so the weaker side governs.
    falloff = max(0.0, min(drop_l, drop_r))

    # A cylinder is shaded symmetrically about its axis; a specular highlight or
    # a raking light is not. Lopsided falloff is therefore discounted, which is
    # what stops glare on a flat pack reading as curvature.
    asymmetry = abs(drop_l - drop_r) / max(abs(drop_l) + abs(drop_r), 1e-6)
    symmetry_factor = float(np.clip(1.0 - asymmetry, 0.0, 1.0))

    # Reference point: a ~140 deg visible arc under diffuse light drops the
    # edges to roughly 0.7 of centre brightness, i.e. a falloff near 0.30.
    score = float(np.clip((falloff / 0.30) * symmetry_factor, 0.0, 1.0))

    return score, {
        "profile_centre": round(centre, 1),
        "profile_left": round(left, 1),
        "profile_right": round(right, 1),
        "edge_falloff": round(falloff, 4),
        "asymmetry": round(asymmetry, 4),
    }


# Silhouette detection needs shape, not detail. Running four segmentation
# strategies over a 6-megapixel phone photo costs seconds per surface and finds
# the same outline a downscaled copy does, so detection happens at this working
# width and the resulting geometry is scaled back to full resolution.
DETECTION_MAX_WIDTH = 900


def analyse(image: np.ndarray) -> ContourResult:
    """Detect the pack and classify its surface geometry."""
    if not _CV2:
        return ContourResult(
            method=NONE, curvature_score=0.0,
            reason="OpenCV unavailable; preprocessing skipped",
        )

    if image.ndim == 3:
        full_gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        full_gray = image

    # Work on a downscaled copy, then map the geometry back up.
    scale = 1.0
    if full_gray.shape[1] > DETECTION_MAX_WIDTH:
        scale = DETECTION_MAX_WIDTH / full_gray.shape[1]
        gray = cv2.resize(
            full_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
    else:
        gray = full_gray

    h, w = gray.shape[:2]
    image_area = float(h * w)

    contour = _largest_pack_contour(gray)
    if contour is None:
        return ContourResult(
            method=NONE, curvature_score=0.0, detected=False,
            reason="No pack silhouette could be isolated; using the frame as-is",
        )

    area = cv2.contourArea(contour)
    area_ratio = area / image_area

    # Approximate the silhouette. Sweeping epsilon finds the coarsest polygon
    # that still tracks the outline, which is what reveals whether four corners
    # are sufficient to describe it.
    perimeter = cv2.arcLength(contour, True)
    quad = None
    vertex_counts = []
    for eps in (0.01, 0.02, 0.03, 0.04, 0.05):
        approx = cv2.approxPolyDP(contour, eps * perimeter, True)
        vertex_counts.append(len(approx))
        if len(approx) == 4 and quad is None:
            quad = approx

    # Curvature signal: how much of the convex hull the best-fit quadrilateral
    # fails to cover. A flat carton fills its own hull; a bottle bulges past it.
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull) or 1.0
    min_rect = cv2.minAreaRect(contour)
    rect_area = float(min_rect[1][0] * min_rect[1][1]) or 1.0

    rect_fill = area / rect_area          # 1.0 for a perfect rectangle
    solidity = area / hull_area           # 1.0 for a convex shape

    # Shading is the primary evidence of curvature; silhouette shape only
    # corroborates it (a bottle with rounded shoulders fills its bounding
    # rectangle poorly, but a full-height label may not).
    shading_score, shading_diag = _shading_curvature(gray, contour)
    shape_score = float(np.clip((1.0 - rect_fill) * 2.2 + (1.0 - solidity) * 0.8, 0.0, 1.0))
    curvature = float(np.clip(0.75 * shading_score + 0.25 * shape_score, 0.0, 1.0))

    diagnostics = {
        "rect_fill": round(rect_fill, 4),
        "solidity": round(solidity, 4),
        "shading_score": round(shading_score, 4),
        "shape_score": round(shape_score, 4),
        "vertex_counts": vertex_counts,
        "perimeter_px": round(perimeter, 1),
        "min_rect_angle": round(float(min_rect[2]), 2),
        **shading_diag,
    }

    # Curvature alone decides the method. Whether a clean quadrilateral was
    # found is a separate question -- it only determines which corners key the
    # rectification. Conflating the two misclassifies a flat pack as a cylinder
    # merely because its outline did not reduce to exactly four vertices, and
    # then unwraps a carton that was never curved.
    inv_scale = 1.0 / scale
    diagnostics["detection_scale"] = round(scale, 4)

    if curvature >= CURVATURE_THRESHOLD:
        box = cv2.boxPoints(min_rect)
        return ContourResult(
            method=CYLINDRICAL,
            curvature_score=round(curvature, 4),
            corners=_order_corners(box) * inv_scale,
            contour_area_ratio=round(area_ratio, 4),
            detected=True,
            reason=(
                f"Luminance falls off symmetrically towards both edges "
                f"(curvature {curvature:.2f} >= {CURVATURE_THRESHOLD}); "
                "treating as a curved surface"
            ),
            diagnostics=diagnostics,
        )

    if quad is not None:
        corners = _order_corners(quad) * inv_scale
        note = "clean four-corner silhouette"
    else:
        # Flat, but the outline did not reduce to four vertices -- a minimum-area
        # rectangle still gives a sound basis for the homography.
        corners = _order_corners(cv2.boxPoints(min_rect)) * inv_scale
        note = "no exact quadrilateral; using minimum-area rectangle"

    return ContourResult(
        method=PLANAR,
        curvature_score=round(curvature, 4),
        corners=corners,
        contour_area_ratio=round(area_ratio, 4),
        detected=True,
        reason=f"Flat surface (curvature {curvature:.2f}); planar rectification -- {note}",
        diagnostics=diagnostics,
    )


def estimate_px_per_mm(
    corners: np.ndarray | None,
    pack_width_cm: float | None,
    pack_height_cm: float | None,
) -> float | None:
    """Pixels per millimetre, from the detected pack against its stated size.

    This is the bridge between image space and physical space -- without it,
    Rule 11 font-height enforcement is impossible, because a "2 mm" requirement
    cannot be checked against a measurement in pixels.
    """
    if corners is None or not pack_width_cm or not pack_height_cm:
        return None
    tl, tr, br, bl = corners
    width_px = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height_px = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if width_px <= 0 or height_px <= 0:
        return None
    # Average both axes: perspective makes them disagree slightly, and the mean
    # is a better estimate than trusting either alone.
    scale = ((width_px / (pack_width_cm * 10)) + (height_px / (pack_height_cm * 10))) / 2
    return round(float(scale), 4) if scale > 0 else None
