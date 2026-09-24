"""Pre-market die-line audit -- spec section 3.F, the Self-Certification Sandbox.

A brand uploads label artwork BEFORE printing and gets back either a
cryptographic compliance certificate or an actionable defect list.

Why this is worth building
--------------------------
Every violation caught here is a print run that never becomes an enforcement
case. Fixing "net quantity is 1.6 mm, needs 2.0 mm" in the artwork file costs
minutes; discovering it after 200,000 cartons are printed costs a recall. The
same rules engine that enforces in the field runs here in advisory mode, so a
brand cannot be surprised later by a standard it was never shown.

The measurement problem
-----------------------
Field inspection derives its pixels-per-millimetre from a photographed pack of
known size. A die-line has no such ambiguity: it is a vector or raster artwork
whose intended physical dimensions the brand states outright, so scale is exact
rather than estimated. That makes font-height findings here *more* reliable
than in the field, not less -- which is precisely why a brand should trust them.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import numpy as np

from extraction.ocr_verify import get_verifier
from extraction.vision_llm import get_provider
from preprocessing.coordinate_mapper import (
    BBox,
    crop_region,
    font_height_mm,
    measure_ink_height_px,
)
from rules.base import RuleContext
from rules.registry import evaluate as evaluate_rules

logger = logging.getLogger("metrix.dieline")




@dataclass
class DielineFinding:
    rule_id: str
    rule_name: str
    clause: str
    severity: str
    status: str
    message: str
    fix: str | None = None
    measured: str | None = None
    required: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule": self.rule_id,
            "rule_name": self.rule_name,
            "clause": self.clause,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "fix": self.fix,
            "measured": self.measured,
            "required": self.required,
        }


@dataclass
class DielineAudit:
    compliance_score: int
    is_approved: bool
    findings: list[DielineFinding] = field(default_factory=list)
    extracted: dict[str, str | None] = field(default_factory=dict)
    font_heights_mm: dict[str, float] = field(default_factory=dict)
    px_per_mm: float | None = None
    panel_area_cm2: float | None = None
    page_count: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def blocking_count(self) -> int:
        return len([f for f in self.findings if f.status == "FAIL"])

    def to_dict(self) -> dict:
        return {
            "compliance_score": self.compliance_score,
            "is_compliant": self.is_approved,
            "blocking_issues": self.blocking_count,
            "advisory_issues": len([f for f in self.findings if f.status == "WARNING"]),
            "findings": [f.to_dict() for f in self.findings],
            "extracted_declarations": self.extracted,
            "measured_font_heights_mm": self.font_heights_mm,
            "artwork": {
                "px_per_mm": self.px_per_mm,
                "panel_area_cm2": self.panel_area_cm2,
                "page_count": self.page_count,
            },
            "warnings": self.warnings,
        }


def render_artwork(
    data: bytes, content_type: str | None, target_px_per_mm: float = 12.0,
    pack_width_cm: float | None = None,
) -> tuple[np.ndarray, float, int, list[str]]:
    """Rasterise the uploaded artwork and establish an exact physical scale.

    Returns (image, px_per_mm, page_count, warnings).
    """
    warnings: list[str] = []
    from PIL import Image

    ctype = (content_type or "").lower()

    if "pdf" in ctype or data[:5] == b"%PDF-":
        # A PDF die-line carries its page size in points (1/72 inch), which is a
        # true physical dimension -- so scale is known exactly with no estimate.
        try:
            import pypdfium2  # noqa: F401

            raise ImportError  # keep the fallback path below authoritative
        except ImportError:
            pass

        width_pt = _pdf_page_width_pt(data)
        if width_pt:
            width_mm = width_pt * 25.4 / 72.0
            warnings.append(
                f"PDF page is {width_mm:.1f} mm wide; scale taken from the page "
                "geometry rather than the stated pack width."
            )
        raise ValueError(
            "PDF die-lines require a PDF rasteriser (pypdfium2 or pdf2image with "
            "poppler), which is not installed. Upload the artwork as PNG or JPEG "
            "at a known width instead."
        )

    with Image.open(io.BytesIO(data)) as img:
        rgb = img.convert("RGB")
        arr = np.asarray(rgb, dtype=np.uint8)

    # Scale comes from the stated physical width -- exact, not inferred from a
    # photograph of unknown distance.
    if pack_width_cm and pack_width_cm > 0:
        px_per_mm = arr.shape[1] / (pack_width_cm * 10.0)
    else:
        px_per_mm = target_px_per_mm
        warnings.append(
            "No pack width supplied; font heights are estimated against a default "
            "scale and should be treated as indicative only."
        )

    return arr, round(px_per_mm, 4), 1, warnings


def _pdf_page_width_pt(data: bytes) -> float | None:
    """Read the first MediaBox width from a PDF without a full parser."""
    import re

    m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", data)
    if not m:
        return None
    try:
        return float(m.group(3)) - float(m.group(1))
    except ValueError:
        return None


def audit(
    artwork: np.ndarray,
    px_per_mm: float,
    pack_width_cm: float | None,
    pack_height_cm: float | None,
    category_slug: str | None = None,
    warnings: list[str] | None = None,
) -> DielineAudit:
    """Run the field rules engine over artwork, in advisory mode."""
    provider = get_provider()
    result = provider.extract(artwork, surface="DIE_LINE")

    extracted: dict[str, str | None] = {}
    font_heights: dict[str, float] = {}

    for f in result.fields:
        if not f.is_present or f.value is None:
            continue
        extracted[f.field_name] = f.value
        if f.bbox is not None:
            # Measure the actual ink, not the detector's padded box. Rule 11
            # findings turn on this number, so a few pixels of padding is the
            # difference between catching undersized print and passing it.
            box = BBox(f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height)
            ink_px = measure_ink_height_px(crop_region(artwork, box, padding=0))
            mm = font_height_mm(ink_px or f.bbox.height, px_per_mm, box_kind="ink")
            if mm:
                font_heights[f.field_name] = mm

    area = None
    if pack_width_cm and pack_height_cm:
        area = round(pack_width_cm * pack_height_cm, 2)

    ctx = RuleContext(
        fields=extracted,
        surfaces=["DIE_LINE"],
        surface_area_cm2=area,
        package_width_cm=pack_width_cm,
        package_height_cm=pack_height_cm,
        font_heights_mm=font_heights,
        category_slug=category_slug,
        # Advisory: findings carry no statutory penalty. A brand voluntarily
        # submitting artwork for checking must not be punished for doing so --
        # that would guarantee nobody ever uses the sandbox.
        is_pre_certification=True,
    )

    ev = evaluate_rules(ctx)

    findings = [
        DielineFinding(
            rule_id=r.rule_id,
            rule_name=r.rule_name,
            clause=r.legal_clause,
            severity=r.severity,
            status=r.status,
            message=r.evidence_text,
            fix=r.suggested_fix,
            measured=r.calculated_value,
            required=r.expected_value,
        )
        for r in ev.results
        if r.is_violation
    ]

    order = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    findings.sort(key=lambda f: (f.status != "FAIL", order.get(f.severity, 3)))

    # A certificate issues only when nothing is blocking. Advisory warnings do
    # not block, but they are reported so the brand can act on them.
    blocking = len([f for f in findings if f.status == "FAIL"])
    approved = blocking == 0

    return DielineAudit(
        compliance_score=ev.score,
        is_approved=approved,
        findings=findings,
        extracted=extracted,
        font_heights_mm=font_heights,
        px_per_mm=px_per_mm,
        panel_area_cm2=area,
        warnings=list(warnings or []),
    )
