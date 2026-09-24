"""Deterministic OCR crop verification -- spec extraction/ocr_verify.py.

This is the guard rail on the vision model.  For every declaration the model
claims to have read, the *exact pixel crop* it pointed at is re-read by a
conventional OCR engine that has no language model, no world knowledge, and no
capacity to invent a plausible value.

If the two agree, confidence rises and the finding is safe to cite.  If the
model returned text the pixels do not support, they disagree and the field is
demoted -- which is precisely the hallucination case that would otherwise put a
fabricated value into a statutory notice.

Engines are probed in order of accuracy and selected at runtime:
PaddleOCR -> RapidOCR (ONNX) -> Tesseract -> a morphology-based line detector.
"""
from __future__ import annotations

import importlib.util
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np

from app.config import settings

logger = logging.getLogger("metrix.ocr")

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False


# ---------------------------------------------------------------------------
@dataclass
class VerificationResult:
    """Outcome of re-reading one crop."""

    field_name: str
    claimed_value: str | None
    ocr_value: str | None
    similarity: float          # 0-1 normalised agreement
    agrees: bool
    confidence: float          # OCR's own confidence in its reading
    engine: str
    note: str = ""


def _have(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


# ===========================================================================
# Engines
# ===========================================================================
class OCREngine(ABC):
    name = "base"

    @abstractmethod
    def read(self, image: np.ndarray) -> tuple[str, float]:
        """Read all text in a crop. Returns (text, confidence)."""

    @abstractmethod
    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        """Locate and read text lines. Returns [(text, (x,y,w,h), confidence)]."""

    @property
    def available(self) -> bool:
        return True


class RapidOCREngine(OCREngine):
    """RapidOCR -- PaddleOCR's detection/recognition models on ONNX Runtime.

    Chosen as the practical default: same model lineage as PaddleOCR with no
    heavyweight framework dependency, so it installs cleanly on any platform.
    """

    name = "rapidocr"

    def __init__(self) -> None:
        self._engine = None

    @property
    def available(self) -> bool:
        return _have("rapidocr_onnxruntime") or _have("rapidocr")

    def _get(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError:
                from rapidocr import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def _run(self, image: np.ndarray):
        if image.ndim == 3:
            bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if _CV2 else image
        else:
            bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if _CV2 else image
        out = self._get()(bgr)
        # 1.x returns (result, elapse); 2.x/3.x may return an object.
        if isinstance(out, tuple):
            return out[0]
        return getattr(out, "boxes", None) and list(
            zip(out.boxes, out.txts, out.scores)
        ) or None

    def read(self, image: np.ndarray) -> tuple[str, float]:
        try:
            result = self._run(image)
        except Exception as exc:
            logger.debug("RapidOCR read failed: %s", exc)
            return "", 0.0
        if not result:
            return "", 0.0
        texts, scores = [], []
        for row in result:
            texts.append(str(row[1]))
            try:
                scores.append(float(row[2]))
            except (IndexError, TypeError, ValueError):
                scores.append(0.5)
        return " ".join(texts).strip(), (sum(scores) / len(scores) if scores else 0.0)

    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        try:
            result = self._run(image)
        except Exception as exc:
            logger.debug("RapidOCR line read failed: %s", exc)
            return []
        if not result:
            return []

        lines = []
        for row in result:
            box = np.array(row[0], dtype=np.float32).reshape(-1, 2)
            x, y = int(box[:, 0].min()), int(box[:, 1].min())
            w = int(box[:, 0].max() - box[:, 0].min())
            h = int(box[:, 1].max() - box[:, 1].min())
            try:
                score = float(row[2])
            except (IndexError, TypeError, ValueError):
                score = 0.5
            lines.append((str(row[1]), (x, y, max(1, w), max(1, h)), score))
        return lines


class PaddleOCREngine(OCREngine):
    """PaddleOCR -- the spec's named engine; used when it is installed."""

    name = "paddle"

    def __init__(self) -> None:
        self._engine = None

    @property
    def available(self) -> bool:
        return _have("paddleocr")

    def _get(self):
        if self._engine is None:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._engine

    def read(self, image: np.ndarray) -> tuple[str, float]:
        lines = self.read_lines(image)
        if not lines:
            return "", 0.0
        return (
            " ".join(t for t, _b, _c in lines).strip(),
            sum(c for _t, _b, c in lines) / len(lines),
        )

    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        try:
            result = self._get().ocr(image, cls=True)
        except Exception as exc:
            logger.debug("PaddleOCR failed: %s", exc)
            return []
        if not result or not result[0]:
            return []
        lines = []
        for box, (text, score) in result[0]:
            pts = np.array(box, dtype=np.float32)
            x, y = int(pts[:, 0].min()), int(pts[:, 1].min())
            w = int(pts[:, 0].max() - x)
            h = int(pts[:, 1].max() - y)
            lines.append((text, (x, y, max(1, w), max(1, h)), float(score)))
        return lines


class TesseractEngine(OCREngine):
    name = "tesseract"

    @property
    def available(self) -> bool:
        if not _have("pytesseract"):
            return False
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def read(self, image: np.ndarray) -> tuple[str, float]:
        try:
            import pytesseract

            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            words, confs = [], []
            for txt, conf in zip(data["text"], data["conf"]):
                if txt.strip() and float(conf) >= 0:
                    words.append(txt.strip())
                    confs.append(float(conf) / 100.0)
            return " ".join(words), (sum(confs) / len(confs) if confs else 0.0)
        except Exception as exc:
            logger.debug("Tesseract read failed: %s", exc)
            return "", 0.0

    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        try:
            import pytesseract

            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
        except Exception:
            return []

        grouped: dict[tuple, list] = {}
        for i, txt in enumerate(data["text"]):
            if not txt.strip() or float(data["conf"][i]) < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append(i)

        lines = []
        for idxs in grouped.values():
            text = " ".join(data["text"][i].strip() for i in idxs)
            x = min(data["left"][i] for i in idxs)
            y = min(data["top"][i] for i in idxs)
            x2 = max(data["left"][i] + data["width"][i] for i in idxs)
            y2 = max(data["top"][i] + data["height"][i] for i in idxs)
            conf = sum(float(data["conf"][i]) for i in idxs) / len(idxs) / 100.0
            lines.append((text, (x, y, x2 - x, y2 - y), conf))
        return lines


class MorphologyEngine(OCREngine):
    """Last-resort text *localiser* -- it finds lines but cannot read them.

    When no OCR engine is installed this still contributes something real: text
    line geometry, which is what font-height measurement under Rule 11 needs and
    what tells the pipeline whether a panel carries printing at all.

    It deliberately returns empty strings rather than guesses. A verifier that
    invents text would defeat its own purpose -- the entire reason this module
    exists is to be the component that cannot hallucinate.
    """

    name = "morphology"

    def read(self, image: np.ndarray) -> tuple[str, float]:
        return "", 0.0

    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        if not _CV2:
            return []
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        h, w = gray.shape[:2]

        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 11
        )
        # Dilate horizontally to merge characters into words and words into lines.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 40), 3))
        merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        cnts, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        lines = []
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            if cw < w * 0.04 or ch < 8 or ch > h * 0.35:
                continue
            if cw / ch < 1.2:      # text lines are wider than they are tall
                continue
            lines.append(("", (x, y, cw, ch), 0.0))
        lines.sort(key=lambda ln: (ln[1][1], ln[1][0]))
        return lines


# ===========================================================================
# Verifier
# ===========================================================================
def normalise(text: str | None) -> str:
    """Reduce a value to what actually matters for comparison.

    OCR and a vision model will disagree endlessly on punctuation, spacing and
    currency glyphs while agreeing perfectly on the number that carries legal
    meaning. Comparing raw strings would report constant false disagreement.
    """
    if not text:
        return ""
    t = str(text).lower()
    t = t.replace("₹", "rs").replace("`", "").replace("|", "l")
    # Common OCR confusions, applied only between digits so words are untouched.
    t = re.sub(r"(?<=\d)[oO](?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[lI](?=\d)", "1", t)
    t = re.sub(r"[^a-z0-9./@-]+", "", t)
    return t


def similarity(a: str | None, b: str | None) -> float:
    na, nb = normalise(a), normalise(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Containment counts as agreement: OCR often reads the whole label line
    # ("mrprs45.00inclofalltaxes") where the model returned just the value.
    if na in nb or nb in na:
        return 0.92
    return SequenceMatcher(None, na, nb).ratio()


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _dedupe_lines(
    lines: list[tuple[str, tuple[int, int, int, int], float]],
    iou_threshold: float = 0.4,
) -> list[tuple[str, tuple[int, int, int, int], float]]:
    """Merge duplicate reads produced by overlapping tiles.

    The same line seen twice is kept once -- the read with higher confidence
    wins, since a line clipped by a tile edge tends to score lower than the
    copy that was seen whole.
    """
    kept: list[tuple[str, tuple[int, int, int, int], float]] = []
    for line in sorted(lines, key=lambda ln: -ln[2]):
        if any(_iou(line[1], other[1]) >= iou_threshold for other in kept):
            continue
        kept.append(line)
    kept.sort(key=lambda ln: (ln[1][1], ln[1][0]))
    return kept


NUMERIC_FIELDS = {"mrp", "net_quantity", "unit_price", "fssai_licence"}


def _numbers(text: str | None) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", str(text or ""))


# Text detectors resize their input to a fixed maximum side before running, so
# feeding them a high-resolution page silently shrinks the small print back below
# the readable threshold. Tiles are kept under this so each is processed at (or
# near) native resolution.
TILE_MAX_SIDE = 1400
# Tiles overlap so a line of text straddling a boundary is still read whole.
TILE_OVERLAP = 180


class OCRVerifier:
    def __init__(self, engine: OCREngine) -> None:
        self.engine = engine

    def read_lines(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int], float]]:
        return self.engine.read_lines(image)

    def read_lines_tiled(
        self, image: np.ndarray, max_side: int = TILE_MAX_SIDE
    ) -> list[tuple[str, tuple[int, int, int, int], float]]:
        """Read a high-resolution page by tiling it at native resolution.

        Detectors like DBNet rescale their input to a fixed maximum side. On a
        4000px artwork that means the whole page is shrunk to roughly a quarter
        size before detection, so a 1.4 mm declaration that occupied 48 px is
        presented to the model at 12 px and vanishes -- the exact declaration a
        font-height audit exists to catch.

        Splitting into overlapping tiles keeps every region near 1:1, which is
        what makes small print measurable. Overlap prevents a line landing on a
        boundary from being cut in half, and duplicates from the overlap are
        merged by position afterwards.
        """
        h, w = image.shape[:2]
        if max(h, w) <= max_side:
            return self.engine.read_lines(image)

        step = max_side - TILE_OVERLAP
        results: list[tuple[str, tuple[int, int, int, int], float]] = []

        for top in range(0, h, step):
            for left in range(0, w, step):
                bottom = min(top + max_side, h)
                right = min(left + max_side, w)
                if bottom - top < 40 or right - left < 40:
                    continue

                tile = image[top:bottom, left:right]
                for text, (x, y, tw, th), conf in self.engine.read_lines(tile):
                    results.append((text, (x + left, y + top, tw, th), conf))

                if right >= w:
                    break
            if bottom >= h:
                break

        return _dedupe_lines(results)

    def verify(
        self,
        crop: np.ndarray,
        field_name: str,
        claimed_value: str | None,
    ) -> VerificationResult:
        """Re-read one crop and compare against what the model claimed."""
        from preprocessing.enhance import upscale_for_ocr

        if crop is None or crop.size == 0:
            return VerificationResult(
                field_name=field_name, claimed_value=claimed_value, ocr_value=None,
                similarity=0.0, agrees=False, confidence=0.0, engine=self.engine.name,
                note="Empty crop; nothing to verify against",
            )

        text, conf = self.engine.read(upscale_for_ocr(crop))

        if self.engine.name == "morphology":
            # The localiser cannot read. Say so rather than reporting agreement
            # or disagreement it has no basis for.
            return VerificationResult(
                field_name=field_name, claimed_value=claimed_value, ocr_value=None,
                similarity=0.0, agrees=False, confidence=0.0, engine=self.engine.name,
                note="No OCR engine installed; value could not be independently verified",
            )

        sim = similarity(claimed_value, text)

        # For fields whose legal meaning is a number, matching digits is what
        # counts -- surrounding words are noise either reader may render freely.
        if field_name in NUMERIC_FIELDS:
            claimed_nums, ocr_nums = _numbers(claimed_value), _numbers(text)
            if claimed_nums and ocr_nums:
                if any(c in ocr_nums for c in claimed_nums):
                    sim = max(sim, 0.95)
                else:
                    sim = min(sim, 0.35)   # digits differ: a material disagreement

        agrees = sim >= 0.75
        return VerificationResult(
            field_name=field_name,
            claimed_value=claimed_value,
            ocr_value=text or None,
            similarity=round(sim, 4),
            agrees=agrees,
            confidence=round(conf, 4),
            engine=self.engine.name,
            note=(
                "Independent OCR read agrees with the extracted value"
                if agrees
                else "OCR re-read does not support the extracted value"
            ),
        )


_ENGINES: list[type[OCREngine]] = [
    PaddleOCREngine,
    RapidOCREngine,
    TesseractEngine,
    MorphologyEngine,
]
_verifier: OCRVerifier | None = None


def get_verifier(engine_name: str | None = None) -> OCRVerifier:
    """Select an OCR engine, probing in descending order of accuracy."""
    global _verifier
    requested = (engine_name or settings.OCR_ENGINE).lower()

    if _verifier is not None and (requested == "auto" or _verifier.engine.name == requested):
        return _verifier

    if requested != "auto":
        for cls in _ENGINES:
            if cls.name == requested:
                candidate = cls()
                if candidate.available:
                    _verifier = OCRVerifier(candidate)
                    logger.info("OCR engine: %s (explicitly configured)", candidate.name)
                    return _verifier
                logger.warning("Requested OCR engine %r is unavailable; probing", requested)
                break

    for cls in _ENGINES:
        candidate = cls()
        if candidate.available:
            _verifier = OCRVerifier(candidate)
            logger.info("OCR engine: %s", candidate.name)
            return _verifier

    _verifier = OCRVerifier(MorphologyEngine())
    return _verifier


def reset_verifier() -> None:
    global _verifier
    _verifier = None
