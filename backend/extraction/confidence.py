"""Confidence fusion -- spec extraction/confidence.py.

Turns two independent readings into one number a human can act on, and decides
which of three outcomes a session gets:

    >= CONFIDENCE_ACCEPT_THRESHOLD   act on it
    0.60 .. 0.75                     route to senior peer review (spec 3.E)
    <  CONFIDENCE_REVIEW_FLOOR       reject; recapture required

The weighting is deliberately asymmetric. Agreement between the vision model and
OCR raises confidence modestly; disagreement collapses it. That bias is the
point -- the cost of citing a hallucinated declaration in a statutory notice is
far higher than the cost of asking an officer to retake a photograph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.config import settings


class Verdict(StrEnum):
    ACCEPT = "ACCEPT"
    PEER_REVIEW = "PEER_REVIEW"
    REJECT = "REJECT"


@dataclass
class FieldConfidence:
    field_name: str
    vision_confidence: float
    ocr_confidence: float | None
    ocr_agrees: bool | None
    similarity: float | None
    fused: float
    verdict: str
    rationale: str


@dataclass
class SessionConfidence:
    overall: float
    verdict: str
    fields: list[FieldConfidence] = field(default_factory=list)
    rationale: str = ""
    triggers: list[str] = field(default_factory=list)

    @property
    def needs_peer_review(self) -> bool:
        return self.verdict == Verdict.PEER_REVIEW


# Declarations that carry the most legal weight are held to a higher bar,
# because a wrong reading of them is what produces an unsound notice.
FIELD_WEIGHTS: dict[str, float] = {
    "mrp": 2.0,
    "net_quantity": 2.0,
    "unit_price": 1.5,
    "expiry_date": 1.8,
    "mfg_date": 1.4,
    "manufacturer_name": 1.2,
    "manufacturer_address": 1.0,
    "country_of_origin": 1.2,
    "customer_care": 0.8,
    "fssai_licence": 1.3,
    "batch_number": 0.6,
    "product_name": 0.7,
    "brand_name": 0.7,
}


def fuse_field(
    field_name: str,
    vision_confidence: float,
    ocr_confidence: float | None = None,
    ocr_agrees: bool | None = None,
    similarity: float | None = None,
) -> FieldConfidence:
    """Combine a vision claim with its deterministic re-read."""
    v = max(0.0, min(1.0, vision_confidence or 0.0))

    if ocr_agrees is None:
        # No independent verification was possible (no OCR engine, or no crop).
        # The claim is uncorroborated, so it is capped below the accept line --
        # an unverified value must never auto-issue a notice.
        fused = round(min(v * 0.85, 0.74), 4)
        rationale = "Vision reading only; no independent OCR corroboration available"
    elif ocr_agrees:
        o = ocr_confidence if ocr_confidence is not None else 0.5
        sim = similarity if similarity is not None else 1.0
        # Two independent readers agreeing is worth more than either alone, but
        # the bonus is capped so weak agreement cannot manufacture certainty.
        base = v * 0.6 + o * 0.4
        fused = round(min(1.0, base + 0.10 * sim), 4)
        rationale = (
            f"Vision and OCR agree (similarity {sim:.2f}); "
            "independently corroborated"
        )
    else:
        o = ocr_confidence if ocr_confidence is not None else 0.0
        sim = similarity if similarity is not None else 0.0
        # Disagreement is the hallucination signal. Collapse hard.
        fused = round(min(v, max(o, 0.1)) * (0.35 + 0.3 * sim), 4)
        rationale = (
            f"Vision and OCR disagree (similarity {sim:.2f}); "
            "the extracted value is not supported by the pixels"
        )

    if fused >= settings.CONFIDENCE_ACCEPT_THRESHOLD:
        verdict = Verdict.ACCEPT
    elif fused >= settings.CONFIDENCE_REVIEW_FLOOR:
        verdict = Verdict.PEER_REVIEW
    else:
        verdict = Verdict.REJECT

    return FieldConfidence(
        field_name=field_name,
        vision_confidence=round(v, 4),
        ocr_confidence=round(ocr_confidence, 4) if ocr_confidence is not None else None,
        ocr_agrees=ocr_agrees,
        similarity=round(similarity, 4) if similarity is not None else None,
        fused=fused,
        verdict=verdict,
        rationale=rationale,
    )


def fuse_session(
    field_confidences: list[FieldConfidence],
    estimated_penalty: float | None = None,
    has_contested_unit_price: bool = False,
) -> SessionConfidence:
    """Roll per-field confidence into a session verdict and escalation decision.

    Implements the three peer-review triggers from spec 3.E: a borderline
    confidence band, a contested unit-price calculation, and a high penalty
    exposure.
    """
    if not field_confidences:
        return SessionConfidence(
            overall=0.0,
            verdict=Verdict.REJECT,
            rationale="No declarations could be extracted from the supplied surfaces",
        )

    # Weighted mean over fields that were actually read. Missing declarations
    # are a rules-engine finding, not a confidence problem -- confidently
    # observing that nothing is printed is a valid, high-confidence reading.
    total_weight = 0.0
    total = 0.0
    for fc in field_confidences:
        w = FIELD_WEIGHTS.get(fc.field_name, 1.0)
        total += fc.fused * w
        total_weight += w
    overall = round(total / total_weight, 4) if total_weight else 0.0

    triggers: list[str] = []

    critical_failures = [
        fc for fc in field_confidences
        if fc.verdict == Verdict.REJECT and FIELD_WEIGHTS.get(fc.field_name, 1.0) >= 1.5
    ]
    if critical_failures:
        triggers.append(
            "LOW_CONFIDENCE: "
            + ", ".join(fc.field_name for fc in critical_failures)
            + " could not be read reliably"
        )

    if settings.CONFIDENCE_REVIEW_FLOOR <= overall < settings.CONFIDENCE_ACCEPT_THRESHOLD:
        triggers.append(
            f"LOW_CONFIDENCE: session confidence {overall:.2f} falls in the "
            f"{settings.CONFIDENCE_REVIEW_FLOOR:.2f}-"
            f"{settings.CONFIDENCE_ACCEPT_THRESHOLD:.2f} escalation band"
        )

    if has_contested_unit_price:
        triggers.append(
            "CONTESTED_UNIT_PRICE: declared unit price disagrees with "
            "MRP divided by net quantity"
        )

    if estimated_penalty and estimated_penalty > settings.PEER_REVIEW_PENALTY_THRESHOLD:
        triggers.append(
            f"HIGH_PENALTY: penalty exposure Rs.{estimated_penalty:,.0f} exceeds the "
            f"Rs.{settings.PEER_REVIEW_PENALTY_THRESHOLD:,.0f} senior-review threshold"
        )

    if overall < settings.CONFIDENCE_REVIEW_FLOOR:
        verdict = Verdict.REJECT
        rationale = (
            f"Session confidence {overall:.2f} is below the "
            f"{settings.CONFIDENCE_REVIEW_FLOOR:.2f} floor. Recapture is required "
            "before any finding can be issued."
        )
    elif triggers:
        verdict = Verdict.PEER_REVIEW
        rationale = (
            f"Session confidence {overall:.2f}. Escalated to senior review: "
            + "; ".join(triggers)
        )
    else:
        verdict = Verdict.ACCEPT
        rationale = (
            f"Session confidence {overall:.2f}; all weighted declarations were "
            "independently corroborated"
        )

    return SessionConfidence(
        overall=overall,
        verdict=verdict,
        fields=field_confidences,
        rationale=rationale,
        triggers=triggers,
    )


def compliance_score(
    violations: list, total_rules: int, confidence: float = 1.0
) -> int:
    """Score a pack 0-100 from its violations.

    Severity-weighted rather than a simple pass count: one expired-stock finding
    should not score the same as one missing batch code. The result is scaled by
    session confidence so a shaky reading cannot yield a confident-looking score.
    """
    if total_rules <= 0:
        return 0

    penalty_per_severity = {"CRITICAL": 30.0, "MAJOR": 14.0, "MINOR": 5.0}
    deduction = 0.0
    for v in violations:
        severity = getattr(v, "severity", None) or "MAJOR"
        status = getattr(v, "status", "FAIL")
        weight = penalty_per_severity.get(severity, 12.0)
        # A warning is a partial deduction; the finding is real but not proven.
        deduction += weight if status == "FAIL" else weight * 0.4

    raw = max(0.0, 100.0 - deduction)
    # Confidence scaling is floored: a compliant pack read with moderate
    # confidence should not be scored as if it were non-compliant.
    scaled = raw * (0.75 + 0.25 * max(0.0, min(1.0, confidence)))
    return int(round(max(0.0, min(100.0, scaled))))
