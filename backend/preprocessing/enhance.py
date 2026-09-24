"""Glare removal and adaptive binarisation -- spec preprocessing/enhance.py.

Retail packaging is designed to be shiny.  Foil, laminate and plastic film all
throw specular highlights that blow out exactly the printed declarations an
inspection needs to read, and shop lighting is rarely even across a pack.

Two enhanced variants are produced rather than one:
  * a contrast-normalised RGB image for the vision model, which reads colour
    context and layout better than a thresholded bitmap;
  * a binarised image for deterministic OCR verification, which is far more
    accurate on clean black-on-white text.

Both are returned because the two consumers genuinely want different inputs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("metrix.enhance")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False

# Below these measurements a correction genuinely helps; above them it hurts.
LOW_CONTRAST_STD = 45.0        # std of grey levels
SOFT_IMAGE_LAPLACIAN = 150.0   # variance of Laplacian
GLARE_MAX_AREA = 0.15          # beyond this it is not a highlight, it is a white pack


@dataclass
class EnhanceResult:
    enhanced: np.ndarray            # RGB, for the vision model
    binary: np.ndarray | None       # single channel, for OCR
    glare_ratio: float              # fraction of pixels that were blown out
    glare_repaired: bool
    corrections: list[str]
    sharpness: float                # variance of Laplacian; low means blurry
    brightness: float
    contrast: float
    warnings: list[str]


def detect_glare(
    gray: np.ndarray, threshold: int = 250, local_delta: int = 18
) -> tuple[np.ndarray, float]:
    """Mask specular highlights.

    Glare is a *local* excess of brightness, not simply a bright pixel. Most
    food packaging is printed on white or near-white substrate that sits above
    any fixed brightness threshold, so a plain threshold masks the label itself
    -- and inpainting then erases the very declarations the inspection exists to
    read.

    A pixel is therefore treated as glare only when it is both near-saturated
    AND markedly brighter than its own neighbourhood, which a flat white
    substrate never is.
    """
    # Heavily blurred copy approximates the local substrate brightness.
    background = cv2.GaussianBlur(gray, (0, 0), max(9.0, gray.shape[1] / 50))

    bright = gray >= threshold
    excess = gray.astype(np.int16) - background.astype(np.int16) > local_delta
    mask = (bright & excess).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # drop speckle
    mask = cv2.dilate(mask, kernel, iterations=1)           # cover the falloff

    ratio = float(np.count_nonzero(mask)) / mask.size
    return mask, ratio


def remove_glare(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Inpaint specular highlights from surrounding texture.

    Telea inpainting reconstructs plausible detail. It cannot invent text that
    the highlight destroyed -- when that happens the field is reported missing
    rather than guessed, which is the correct outcome for an evidence pipeline.
    """
    try:
        return cv2.inpaint(image, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
    except Exception as exc:
        logger.debug("Inpainting skipped: %s", exc)
        return image


def enhance(image: np.ndarray, aggressive: bool = False) -> EnhanceResult:
    """Normalise illumination and produce OCR-ready variants."""
    warnings: list[str] = []

    if not _CV2:
        return EnhanceResult(
            enhanced=image, binary=None, glare_ratio=0.0, glare_repaired=False,
            corrections=[], sharpness=0.0, brightness=0.0, contrast=0.0,
            warnings=["OpenCV unavailable; image used unenhanced"],
        )

    rgb = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    brightness = float(gray.mean())
    contrast = float(gray.std())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if sharpness < 60:
        warnings.append(
            f"Image is soft (sharpness {sharpness:.0f}); small print may not be legible"
        )
    if brightness < 60:
        warnings.append(f"Image is underexposed (mean brightness {brightness:.0f})")
    elif brightness > 205:
        warnings.append(f"Image is overexposed (mean brightness {brightness:.0f})")

    # --- glare ---
    glare_mask, glare_ratio = detect_glare(gray)
    repaired = False
    if glare_ratio > GLARE_MAX_AREA:
        # A "highlight" covering this much of the frame is not a highlight. It
        # is a white pack, an overexposed capture, or a detection failure --
        # and inpainting that much area would destroy more than it repairs.
        warnings.append(
            f"Widespread saturation over {glare_ratio * 100:.1f}% of the frame; "
            "left unrepaired, as inpainting an area this large would remove "
            "printed content. Recapture with less direct light if declarations "
            "are unreadable."
        )
    elif glare_ratio > 0.002:
        rgb = remove_glare(rgb, glare_mask)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        repaired = True
        if glare_ratio > 0.08:
            warnings.append(
                f"Significant glare over {glare_ratio * 100:.1f}% of the pack; "
                "declarations under the highlight may be unrecoverable"
            )

    # --- illumination normalisation, applied only where it is warranted ---
    # Enhancement is corrective, not cosmetic. Applied unconditionally it makes
    # a poor image readable but makes a GOOD image worse: CLAHE amplifies
    # sensor noise into character strokes and an unsharp mask rings halos around
    # glyphs, and OCR accuracy on an already-crisp label drops sharply as a
    # result. Each correction is therefore gated on the measurement that
    # justifies it, so a well-exposed capture passes through essentially
    # untouched.
    enhanced = rgb
    applied: list[str] = []

    if contrast < LOW_CONTRAST_STD or aggressive:
        # CLAHE on the L channel only: equalising RGB independently shifts hue,
        # which would mislead a vision model reading a colour-coded label.
        lab = cv2.cvtColor(enhanced, cv2.COLOR_RGB2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(
            clipLimit=3.0 if aggressive else 2.0, tileGridSize=(8, 8)
        )
        lab = cv2.merge([clahe.apply(l_ch), a_ch, b_ch])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        applied.append("clahe")

    if sharpness < SOFT_IMAGE_LAPLACIAN:
        # Gentle unsharp mask with a small radius. A wide, strong mask produces
        # the halos that confuse character segmentation.
        blur = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
        enhanced = cv2.addWeighted(enhanced, 1.3, blur, -0.3, 0)
        applied.append("unsharp")

    # --- binarisation for OCR ---
    gray_e = cv2.cvtColor(enhanced, cv2.COLOR_RGB2GRAY)
    denoised = cv2.bilateralFilter(gray_e, 9, 75, 75)   # smooths, keeps edges
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,     # must exceed stroke width of the smallest legal text
        C=11,
    )
    binary = cv2.morphologyEx(
        binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    )

    return EnhanceResult(
        enhanced=enhanced,
        binary=binary,
        glare_ratio=round(glare_ratio, 5),
        glare_repaired=repaired,
        corrections=(["glare_inpaint"] if repaired else []) + applied,
        sharpness=round(sharpness, 2),
        brightness=round(brightness, 2),
        contrast=round(contrast, 2),
        warnings=warnings,
    )


def upscale_for_ocr(crop: np.ndarray, min_height: int = 48) -> np.ndarray:
    """Enlarge a small crop before OCR.

    OCR engines degrade sharply below roughly 40px of text height, and the
    declarations most likely to be violations are the smallest print on the pack.
    """
    if not _CV2 or crop.size == 0:
        return crop
    h = crop.shape[0]
    if h >= min_height:
        return crop
    scale = min(6.0, min_height / max(h, 1))
    return cv2.resize(
        crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )
