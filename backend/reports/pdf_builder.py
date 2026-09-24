"""PDF rendering -- spec reports/pdf_builder.py.

Three documents: the enforcement notice with embedded pixel crops, the brand
Digital Compliance Certificate, and the ministry policy report.

Engine selection
----------------
WeasyPrint renders the HTML templates faithfully and is the production path
(it ships in the Docker image with its GTK dependencies). It is impractical to
install on Windows, so a reportlab builder produces the same documents natively.
Both are real implementations of the same documents -- not a fallback stub --
because a legal notice that cannot be generated on the machine in front of you
is not much of a notice.
"""
from __future__ import annotations

import importlib.util
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from core.storage import get_storage

logger = logging.getLogger("metrix.pdf")

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def select_engine() -> str:
    configured = settings.PDF_ENGINE
    if configured == "weasyprint" and _have("weasyprint"):
        return "weasyprint"
    if configured == "reportlab":
        return "reportlab"
    if configured == "auto":
        return "weasyprint" if _have("weasyprint") else "reportlab"
    return "reportlab"


# ===========================================================================
# reportlab builder
# ===========================================================================
INK = (0.11, 0.13, 0.16)
MUTED = (0.42, 0.45, 0.50)
CRITICAL = (0.72, 0.11, 0.11)
MAJOR = (0.78, 0.42, 0.05)
MINOR = (0.55, 0.47, 0.13)
ACCENT = (0.09, 0.31, 0.55)
OK = (0.10, 0.45, 0.28)

SEVERITY_COLOURS = {"CRITICAL": CRITICAL, "MAJOR": MAJOR, "MINOR": MINOR}


@dataclass
class _Cursor:
    y: float


def _reportlab_notice(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 18 * mm
    cur = _Cursor(y=H - margin)
    storage = get_storage()

    def line(gap=4 * mm):
        cur.y -= gap

    def need(space: float) -> None:
        if cur.y < margin + space:
            c.showPage()
            cur.y = H - margin

    def text(s: str, size=9.5, colour=INK, bold=False, indent=0.0, leading=4.6 * mm):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.setFillColorRGB(*colour)
        max_chars = int((W - 2 * margin - indent) / (size * 0.5))
        words, row = s.split(), ""
        for w in words:
            trial = f"{row} {w}".strip()
            if len(trial) > max_chars and row:
                need(leading)
                c.drawString(margin + indent, cur.y, row)
                cur.y -= leading
                row = w
            else:
                row = trial
        if row:
            need(leading)
            c.drawString(margin + indent, cur.y, row)
            cur.y -= leading

    # ---------------- header ----------------
    c.setFillColorRGB(*ACCENT)
    c.rect(0, H - 34 * mm, W, 34 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin, H - 15 * mm, "LEGAL METROLOGY INSPECTION NOTICE")
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, H - 21 * mm,
                 "Department of Legal Metrology | Ministry of Consumer Affairs, "
                 "Food & Public Distribution")
    c.drawString(margin, H - 26 * mm,
                 "Issued under the Legal Metrology Act, 2009 and the Legal Metrology "
                 "(Packaged Commodities) Rules, 2011")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(W - margin, H - 15 * mm, f"Ref: {data.get('session_id', '-')}")
    c.drawRightString(
        W - margin, H - 21 * mm,
        datetime.now(timezone.utc).strftime("%d %B %Y"),
    )

    cur.y = H - 44 * mm

    # ---------------- verdict banner ----------------
    status = data.get("compliance_status") or "UNKNOWN"
    score = data.get("overall_score")
    banner = CRITICAL if status == "NON_COMPLIANT" else MAJOR if status == "WARNING" else OK
    c.setFillColorRGB(*banner)
    c.rect(margin, cur.y - 12 * mm, W - 2 * margin, 12 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 4 * mm, cur.y - 8 * mm,
                 f"{status.replace('_', ' ')}   |   Compliance score: "
                 f"{score if score is not None else '-'}/100")
    penalty = data.get("estimated_penalty")
    if penalty:
        c.drawRightString(W - margin - 4 * mm, cur.y - 8 * mm,
                          f"Penalty exposure: Rs. {penalty:,.0f}")
    cur.y -= 18 * mm

    # ---------------- particulars ----------------
    text("PARTICULARS OF THE COMMODITY", 10.5, ACCENT, bold=True)
    line(1.5 * mm)
    rows = [
        ("Commodity", data.get("product_name")),
        ("Brand / Manufacturer", data.get("brand_name")),
        ("Barcode (EAN)", data.get("barcode")),
        ("Category", data.get("product_category")),
        ("Premises inspected", data.get("store_name")),
        ("Address", data.get("location_address")),
        ("Date of inspection", data.get("inspected_at")),
        ("Inspecting officer", data.get("officer_name")),
        ("Officer ID", data.get("officer_id_code")),
        ("Jurisdiction", data.get("jurisdiction_status")),
    ]
    for label, value in rows:
        if not value:
            continue
        need(4.6 * mm)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*MUTED)
        c.drawString(margin, cur.y, f"{label}:")
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin + 42 * mm, cur.y, str(value)[:78])
        cur.y -= 4.6 * mm

    line(3 * mm)

    # ---------------- findings ----------------
    violations = data.get("violations") or []
    text(f"FINDINGS ({len(violations)})", 10.5, ACCENT, bold=True)
    line(1.5 * mm)

    if not violations:
        text("No contravention was detected in this inspection.", 9.5, OK)
    for i, v in enumerate(violations, start=1):
        need(30 * mm)
        colour = SEVERITY_COLOURS.get(v.get("severity") or "MAJOR", MAJOR)

        c.setFillColorRGB(*colour)
        c.rect(margin, cur.y - 1 * mm, 1.4 * mm, 6 * mm, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(margin + 4 * mm, cur.y + 1.4 * mm,
                     f"{i}. {v.get('rule_name') or v.get('rule_id')}  "
                     f"[{v.get('severity', 'MAJOR')}]")
        cur.y -= 6.5 * mm

        if v.get("legal_clause"):
            text(f"Clause: {v['legal_clause']}", 8.5, MUTED, indent=4 * mm, leading=4 * mm)
        if v.get("evidence_text"):
            text(v["evidence_text"], 9, INK, indent=4 * mm)
        if v.get("expected_value") or v.get("calculated_value"):
            text(
                f"Observed: {v.get('calculated_value') or '-'}    "
                f"Required: {v.get('expected_value') or '-'}",
                8.5, MUTED, indent=4 * mm, leading=4 * mm,
            )
        if v.get("penalty_amount"):
            text(f"Penalty under the Act: Rs. {v['penalty_amount']:,.0f}",
                 8.5, colour, indent=4 * mm, leading=4 * mm)

        # The pixel crop -- what makes the finding evidentiary rather than asserted.
        crop = v.get("evidence_crop_path")
        if crop:
            try:
                raw = storage.read(crop)
                img = ImageReader(io.BytesIO(raw))
                iw, ih = img.getSize()
                target_w = min(78 * mm, W - 2 * margin - 8 * mm)
                target_h = target_w * ih / iw
                if target_h > 34 * mm:
                    target_h = 34 * mm
                    target_w = target_h * iw / ih
                need(target_h + 6 * mm)
                c.drawImage(img, margin + 4 * mm, cur.y - target_h,
                            width=target_w, height=target_h,
                            preserveAspectRatio=True, anchor="sw")
                c.setStrokeColorRGB(*MUTED)
                c.setLineWidth(0.4)
                c.rect(margin + 4 * mm, cur.y - target_h, target_w, target_h,
                       stroke=1, fill=0)
                cur.y -= target_h + 2 * mm
                text("Evidence crop from the original inspection photograph.",
                     7.5, MUTED, indent=4 * mm, leading=3.6 * mm)
            except Exception as exc:
                logger.debug("Could not embed crop %s: %s", crop, exc)
        line(2.5 * mm)

    # ---------------- evidence integrity ----------------
    need(34 * mm)
    line(2 * mm)
    text("EVIDENCE INTEGRITY", 10.5, ACCENT, bold=True)
    line(1.5 * mm)
    text(
        "Every photograph supporting this notice was sealed with a SHA-256 digest at "
        "the moment of capture. The session seal below chains those digests; any "
        "alteration, addition or removal of an image invalidates it.",
        8.5, MUTED,
    )
    if data.get("evidence_seal"):
        text(f"Session seal: {data['evidence_seal']}", 8, INK, leading=4 * mm)
    for img in data.get("images") or []:
        text(f"  {img.get('surface_type', '?'):<10} SHA-256 {img.get('sha256_hash', '')}",
             7.5, MUTED, leading=3.6 * mm)

    # ---------------- appeal rights ----------------
    need(30 * mm)
    line(2 * mm)
    text("RIGHT OF APPEAL", 10.5, ACCENT, bold=True)
    line(1.5 * mm)
    text(
        f"The addressee may contest these findings within {settings.DISPUTE_WINDOW_DAYS} "
        "days of service. The appeal portal provides access to the full-resolution "
        "evidence crops cited above and accepts counter-evidence including batch "
        "records, laboratory certificates and approved packaging variance notices. "
        "An appellate officer reviews both evidence streams before any further action.",
        8.5, MUTED,
    )
    if data.get("dispute_token"):
        text(f"Appeal reference: {data['dispute_token']}", 8.5, INK, leading=4 * mm)

    # ---------------- footer ----------------
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColorRGB(*MUTED)
    c.drawString(margin, margin - 4 * mm,
                 "Generated by MetriX. AI-assisted extraction verified by deterministic "
                 "OCR and reviewed by the named officer.")
    c.drawRightString(W - margin, margin - 4 * mm,
                      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    c.save()
    return buf.getvalue()


def _reportlab_certificate(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 20 * mm

    approved = bool(data.get("is_approved"))
    header = OK if approved else MAJOR

    c.setFillColorRGB(*header)
    c.rect(0, H - 46 * mm, W, 46 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 19)
    c.drawCentredString(
        W / 2, H - 22 * mm,
        "DIGITAL COMPLIANCE CERTIFICATE" if approved else "PRE-MARKET AUDIT REPORT",
    )
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, H - 30 * mm,
                        "Legal Metrology Pre-Market Self-Certification Sandbox")
    c.drawCentredString(W / 2, H - 36 * mm,
                        "Ministry of Consumer Affairs, Food & Public Distribution")

    y = H - 60 * mm
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, y, str(data.get("product_name", "-")))
    y -= 7 * mm
    c.setFont("Helvetica", 10.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(W / 2, y, str(data.get("brand_name", "-")))
    y -= 14 * mm

    score = data.get("compliance_score") or 0
    c.setFont("Helvetica-Bold", 34)
    c.setFillColorRGB(*(OK if score >= 90 else MAJOR if score >= 70 else CRITICAL))
    c.drawCentredString(W / 2, y, f"{score}/100")
    y -= 8 * mm
    c.setFont("Helvetica", 9.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(W / 2, y, "Compliance score against the Packaged Commodities Rules, 2011")
    y -= 14 * mm

    for label, value in [
        ("Certificate reference", data.get("cert_ref")),
        ("Artwork SHA-256", data.get("sha256_hash")),
        ("Target pack size",
         f"{data.get('target_pack_width_cm')} x {data.get('target_pack_height_cm')} cm"
         if data.get("target_pack_width_cm") else None),
        ("Issued", datetime.now(timezone.utc).strftime("%d %B %Y")),
        ("Verification token", data.get("digital_badge_token")),
    ]:
        if not value:
            continue
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*MUTED)
        c.drawString(margin, y, f"{label}:")
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(*INK)
        c.drawString(margin + 46 * mm, y, str(value)[:70])
        y -= 5.6 * mm

    # QR badge
    qr_bytes = data.get("_qr_bytes")
    if qr_bytes:
        try:
            img = ImageReader(io.BytesIO(qr_bytes))
            size = 34 * mm
            c.drawImage(img, W - margin - size, y - size + 4 * mm, size, size)
            c.setFont("Helvetica", 7)
            c.setFillColorRGB(*MUTED)
            c.drawCentredString(W - margin - size / 2, y - size, "Scan to verify")
        except Exception as exc:
            logger.debug("QR embed failed: %s", exc)

    y -= 14 * mm
    findings = data.get("findings") or []
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColorRGB(*ACCENT)
    c.drawString(margin, y, "AUDIT FINDINGS" if findings else "NO DEFECTS FOUND")
    y -= 6 * mm

    if not findings:
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*OK)
        c.drawString(margin, y,
                     "This artwork satisfies every applicable mandatory declaration.")
        y -= 6 * mm
    for f in findings[:14]:
        if y < margin + 24 * mm:
            c.showPage()
            y = H - margin
        colour = SEVERITY_COLOURS.get(f.get("severity") or "MAJOR", MAJOR)
        c.setFillColorRGB(*colour)
        c.rect(margin, y - 1 * mm, 1.2 * mm, 5 * mm, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8.8)
        c.setFillColorRGB(*INK)
        c.drawString(margin + 4 * mm, y + 1 * mm,
                     f"{f.get('rule_name') or f.get('rule')} [{f.get('severity')}]")
        y -= 4.6 * mm
        c.setFont("Helvetica", 8.2)
        c.setFillColorRGB(*MUTED)
        msg = (f.get("message") or "")[:150]
        c.drawString(margin + 4 * mm, y, msg)
        y -= 4.2 * mm
        if f.get("fix"):
            c.setFillColorRGB(*ACCENT)
            c.drawString(margin + 4 * mm, y, f"Fix: {f['fix'][:140]}")
            y -= 5.4 * mm

    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(
        W / 2, margin - 4 * mm,
        "Advisory pre-market audit. Findings here carry no statutory penalty; they "
        "identify defects to correct before printing.",
    )
    c.save()
    return buf.getvalue()


def _reportlab_policy(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 18 * mm

    c.setFillColorRGB(*ACCENT)
    c.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, H - 14 * mm, "POLICY INTELLIGENCE REPORT")
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, H - 21 * mm,
                 "Legal Metrology compliance across packaged commodities | "
                 "Ministry of Consumer Affairs")
    c.drawRightString(W - margin, H - 14 * mm,
                      datetime.now(timezone.utc).strftime("%d %B %Y"))

    y = H - 42 * mm
    head = data.get("headline") or {}

    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "HEADLINE INDICATORS")
    y -= 8 * mm

    tiles = [
        ("Inspections", head.get("inspections_current")),
        ("Compliance rate", f"{head.get('overall_compliance_rate')}%"
         if head.get("overall_compliance_rate") is not None else "-"),
        ("Avg score", head.get("avg_compliance_score")),
        ("Escalated", head.get("cases_escalated")),
    ]
    tile_w = (W - 2 * margin - 9 * mm) / 4
    for i, (label, value) in enumerate(tiles):
        x = margin + i * (tile_w + 3 * mm)
        c.setFillColorRGB(0.96, 0.97, 0.99)
        c.rect(x, y - 16 * mm, tile_w, 16 * mm, stroke=0, fill=1)
        c.setFillColorRGB(*ACCENT)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x + 3 * mm, y - 8 * mm, str(value if value is not None else "-"))
        c.setFillColorRGB(*MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(x + 3 * mm, y - 13 * mm, label)
    y -= 26 * mm

    def section(title: str, rows: list[tuple[str, str]]):
        nonlocal y
        if y < margin + 40 * mm:
            c.showPage()
            y = H - margin
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, title)
        y -= 6.5 * mm
        for left, right in rows[:10]:
            c.setFont("Helvetica", 8.6)
            c.setFillColorRGB(*INK)
            c.drawString(margin, y, left[:78])
            c.setFillColorRGB(*MUTED)
            c.drawRightString(W - margin, y, right)
            y -= 4.8 * mm
        y -= 4 * mm

    section("MOST VIOLATED CLAUSES", [
        (f"{v.get('rule_name')} -- {v.get('clause', '')[:44]}",
         f"{v.get('violation_rate')}% of {v.get('applicable_inspections')} checks")
        for v in (data.get("most_violated_clauses") or [])
    ])
    section("DEGRADING CATEGORIES", [
        (t.get("name", ""), f"{t.get('change'):+.1f} pts ({t.get('current_samples')} inspections)")
        for t in (data.get("degrading_categories") or [])
    ])
    section("IMPROVING CATEGORIES", [
        (t.get("name", ""), f"{t.get('change'):+.1f} pts ({t.get('current_samples')} inspections)")
        for t in (data.get("improving_categories") or [])
    ])

    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColorRGB(*MUTED)
    c.drawString(margin, margin - 4 * mm, (data.get("methodology") or "")[:150])
    c.save()
    return buf.getvalue()


# ===========================================================================
# WeasyPrint builder
# ===========================================================================
def _weasy(template: str, data: dict) -> bytes:
    from weasyprint import HTML

    path = TEMPLATE_DIR / template
    html = path.read_text(encoding="utf-8")
    for key, value in data.items():
        if isinstance(value, (str, int, float)):
            html = html.replace(f"{{{{{key}}}}}", str(value))
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()


# ===========================================================================
# Public API
# ===========================================================================
def build_notice(data: dict) -> tuple[bytes, str]:
    engine = select_engine()
    if engine == "weasyprint":
        try:
            return _weasy("legal_notice.html", data), engine
        except Exception as exc:
            logger.warning("WeasyPrint failed, using reportlab: %s", exc)
    return _reportlab_notice(data), "reportlab"


def build_certificate(data: dict) -> tuple[bytes, str]:
    engine = select_engine()
    if engine == "weasyprint":
        try:
            return _weasy("digital_badge_cert.html", data), engine
        except Exception as exc:
            logger.warning("WeasyPrint failed, using reportlab: %s", exc)
    return _reportlab_certificate(data), "reportlab"


def build_policy_report(data: dict) -> tuple[bytes, str]:
    engine = select_engine()
    if engine == "weasyprint":
        try:
            return _weasy("policy_macro_report.html", data), engine
        except Exception as exc:
            logger.warning("WeasyPrint failed, using reportlab: %s", exc)
    return _reportlab_policy(data), "reportlab"


def build_qr(payload: str, size: int = 8) -> bytes | None:
    """QR badge encoding the public verification URL."""
    try:
        import qrcode

        qr = qrcode.QRCode(box_size=size, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("QR generation failed: %s", exc)
        return None
