"""Brand APIs -- spec routes/brand.py, section 6.C.

Pre-market self-certification (3.F) and the dispute/appeal workflow (3.G).

The dispute portal is deliberately token-addressed rather than login-gated: a
brand receives a secure link with the notice and can inspect the exact pixel
crops cited against it without first negotiating an account. Due process should
not have an onboarding funnel.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from core.deps import BrandUser, CurrentUser, DbSession, SeniorUser
from core.security import generate_reference, generate_token, sha256_bytes
from core.storage import build_key, get_storage
from intelligence.dieline_auditor import audit, render_artwork
from models.base import as_utc
from models.brand_dispute import BrandDispute
from models.brand_pre_cert import BrandPreCert
from models.category import Category
from models.enums import AppellateStatus, SessionStatus, UserRole
from models.inspection_session import InspectionSession
from schemas.brand import (
    DisputeDecision,
    DisputeOut,
    DisputeSubmit,
    PreCertOut,
    PreCertResponse,
)
from schemas.common import Message

logger = logging.getLogger("metrix.brand")
router = APIRouter(prefix="/brand", tags=["Brand"])

ARTWORK_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf",
}


def _url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return get_storage().url_for(path)
    except Exception:
        return None


# ===========================================================================
# Pre-market self-certification sandbox -- spec 3.F
# ===========================================================================
@router.post(
    "/pre-certify", response_model=PreCertResponse, status_code=status.HTTP_201_CREATED
)
async def pre_certify(
    user: BrandUser,
    db: DbSession,
    die_line: UploadFile = File(...),
    product_name: str = Form(..., max_length=200),
    pack_width_cm: float = Form(..., gt=0, le=500),
    pack_height_cm: float = Form(..., gt=0, le=500),
    category_id: int | None = Form(default=None),
) -> PreCertResponse:
    """Audit label artwork before it goes to print."""
    if die_line.content_type and die_line.content_type.lower() not in ARTWORK_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported artwork type {die_line.content_type}. "
            "Upload PNG, JPEG or PDF.",
        )

    data = await die_line.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty artwork upload")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Artwork exceeds the {settings.MAX_UPLOAD_MB} MB limit",
        )

    digest = sha256_bytes(data)
    key = build_key("dieline", f"{user.id}_{digest[:12]}_{die_line.filename or 'artwork'}")
    get_storage().save(key, data, die_line.content_type or "application/octet-stream")

    try:
        image, px_per_mm, pages, warnings = render_artwork(
            data, die_line.content_type, pack_width_cm=pack_width_cm
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    slug = None
    if category_id:
        cat = (
            await db.execute(select(Category).where(Category.id == category_id))
        ).scalar_one_or_none()
        slug = cat.slug if cat else None

    result = audit(
        image, px_per_mm, pack_width_cm, pack_height_cm,
        category_slug=slug, warnings=warnings,
    )

    count = (await db.execute(select(func.count(BrandPreCert.id)))).scalar_one()
    badge_token = generate_token("badge") if result.is_approved else None

    cert = BrandPreCert(
        cert_ref=generate_reference("cert", 4400 + count + 1),
        brand_id=user.id,
        brand_name=user.brand_name,
        product_name=product_name,
        category_id=category_id,
        die_line_file_path=key,
        sha256_hash=digest,
        target_pack_width_cm=pack_width_cm,
        target_pack_height_cm=pack_height_cm,
        target_surface_area_cm2=result.panel_area_cm2,
        compliance_score=result.compliance_score,
        is_approved=result.is_approved,
        findings=[f.to_dict() for f in result.findings],
        digital_badge_token=badge_token,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)

    # Certificate and QR badge render in the background.
    from core.task_runner import dispatch

    try:
        dispatch("pdf.render_pre_cert", cert.id)
    except Exception as exc:
        logger.warning("Certificate rendering could not be queued: %s", exc)

    return PreCertResponse(
        pre_cert_id=cert.cert_ref,
        is_compliant=result.is_approved,
        compliance_score=result.compliance_score,
        blocking_issues=result.blocking_count,
        digital_badge_token=badge_token,
        audit_report_url=f"/api/brand/pre-certifications/{cert.cert_ref}/report",
        findings=[f.to_dict() for f in result.findings],
        extracted_declarations=result.extracted,
        measured_font_heights_mm=result.font_heights_mm,
        warnings=result.warnings,
        message=(
            "Artwork is compliant. A Digital Compliance Certificate and verified "
            "QR badge have been issued."
            if result.is_approved
            else f"{result.blocking_count} issue(s) must be corrected before printing. "
                 "Each finding below includes the specific fix required."
        ),
    )


@router.get("/pre-certifications", response_model=list[PreCertOut])
async def my_certifications(user: BrandUser, db: DbSession) -> list[PreCertOut]:
    rows = (
        await db.execute(
            select(BrandPreCert)
            .where(BrandPreCert.brand_id == user.id)
            .order_by(BrandPreCert.created_at.desc())
        )
    ).scalars().all()
    out = []
    for c in rows:
        item = PreCertOut.model_validate(c)
        item.die_line_url = _url(c.die_line_file_path)
        item.badge_qr_url = _url(c.badge_qr_path)
        item.audit_report_url = _url(c.audit_report_pdf_path)
        out.append(item)
    return out


@router.get("/verify-badge/{badge_token}")
async def verify_badge(badge_token: str, db: DbSession) -> dict:
    """Public verification of a Digital Trust Mark.

    Open by design: a shopper scanning the QR on a pack must be able to confirm
    the badge is genuine without an account. A trust mark nobody can check is
    just a sticker.
    """
    cert = (
        await db.execute(
            select(BrandPreCert).where(BrandPreCert.digital_badge_token == badge_token)
        )
    ).scalar_one_or_none()

    if cert is None or not cert.is_approved:
        return {
            "valid": False,
            "message": (
                "This badge token is not recognised. It may be counterfeit, or the "
                "certification may have been withdrawn."
            ),
        }

    return {
        "valid": True,
        "certificate_ref": cert.cert_ref,
        "brand_name": cert.brand_name,
        "product_name": cert.product_name,
        "compliance_score": cert.compliance_score,
        "issued_at": cert.created_at.isoformat() if cert.created_at else None,
        "artwork_sha256": cert.sha256_hash,
        "issuing_authority": "Legal Metrology Department, Ministry of Consumer Affairs",
        "message": (
            f"Verified. {cert.brand_name} certified this packaging artwork for "
            f"{cert.product_name} at a compliance score of {cert.compliance_score}/100 "
            "before printing."
        ),
    }


# ===========================================================================
# Dispute & appeal workflow -- spec 3.G
# ===========================================================================
@router.post("/disputes/open/{session_id}", response_model=dict)
async def open_dispute(session_id: str, user: CurrentUser, db: DbSession) -> dict:
    """Issue a secure dispute token for a violation notice.

    Called when a notice is served. The brand receives the token by email and
    has DISPUTE_WINDOW_DAYS to respond.
    """
    if not (user.is_officer or user.role == UserRole.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Officers only")

    session = (
        await db.execute(
            select(InspectionSession).where(InspectionSession.session_id == session_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    existing = (
        await db.execute(
            select(BrandDispute).where(BrandDispute.session_id == session.id)
        )
    ).scalar_one_or_none()
    if existing:
        return {
            "dispute_token": existing.dispute_token,
            "portal_url": f"/brand/dispute/{existing.dispute_token}",
            "expires_at": existing.token_expires_at.isoformat()
            if existing.token_expires_at else None,
            "window_days": settings.DISPUTE_WINDOW_DAYS,
            "already_issued": True,
        }

    token = generate_token("dsp")
    expires = datetime.now(timezone.utc) + timedelta(days=settings.DISPUTE_WINDOW_DAYS)
    db.add(BrandDispute(
        session_id=session.id,
        brand_name=session.brand_name,
        dispute_token=token,
        token_expires_at=expires,
        appellate_status=AppellateStatus.UNDER_REVIEW,
    ))
    session.status = SessionStatus.APPEALED
    await db.commit()

    return {
        "dispute_token": token,
        "portal_url": f"/brand/dispute/{token}",
        "expires_at": expires.isoformat(),
        "window_days": settings.DISPUTE_WINDOW_DAYS,
        "already_issued": False,
    }


@router.get("/disputes/{dispute_token}", response_model=DisputeOut)
async def view_dispute(dispute_token: str, db: DbSession) -> DisputeOut:
    """Token-addressed view of the case, including the cited pixel crops."""
    dispute = (
        await db.execute(
            select(BrandDispute)
            .where(BrandDispute.dispute_token == dispute_token)
            .options(
                selectinload(BrandDispute.session).selectinload(
                    InspectionSession.violations
                ),
                selectinload(BrandDispute.session).selectinload(
                    InspectionSession.images
                ),
            )
        )
    ).scalar_one_or_none()

    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute token not recognised")

    expires = as_utc(dispute.token_expires_at)
    expired = bool(expires and expires < datetime.now(timezone.utc))

    out = DisputeOut.model_validate(dispute)
    out.is_expired = expired
    out.window_days = settings.DISPUTE_WINDOW_DAYS

    s = dispute.session
    if s:
        out.session_ref = s.session_id
        out.product_name = s.product_name
        out.store_name = s.store_name
        out.overall_score = s.overall_score
        out.inspected_at = s.created_at
        out.estimated_penalty = s.estimated_penalty
        out.cited_violations = [
            {
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "legal_clause": v.legal_clause,
                "severity": v.severity,
                "evidence_text": v.evidence_text,
                "calculated_value": v.calculated_value,
                "expected_value": v.expected_value,
                "discrepancy": v.discrepancy,
                "penalty_amount": v.penalty_amount,
                # The exact pixels cited against the brand -- spec 3.G.
                "evidence_crop_url": _url(v.evidence_crop_path),
            }
            for v in sorted(s.violations, key=lambda v: v.rule_id)
            if v.status == "FAIL"
        ]
        out.evidence_images = [
            {"surface": i.surface_type, "url": _url(i.image_path),
             "sha256": i.sha256_hash}
            for i in s.images
        ]
    return out


@router.post("/disputes/{dispute_token}", response_model=Message)
async def submit_dispute(
    dispute_token: str, payload: DisputeSubmit, db: DbSession
) -> Message:
    """File grounds of appeal with counter-evidence."""
    dispute = (
        await db.execute(
            select(BrandDispute).where(BrandDispute.dispute_token == dispute_token)
        )
    ).scalar_one_or_none()
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute token not recognised")

    expires = as_utc(dispute.token_expires_at)
    if expires and expires < datetime.now(timezone.utc):
        raise HTTPException(
            status.HTTP_410_GONE,
            f"The {settings.DISPUTE_WINDOW_DAYS}-day appeal window for this notice "
            f"closed on {expires:%d %B %Y}.",
        )
    if dispute.appellate_status != AppellateStatus.UNDER_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This appeal was already decided as {dispute.appellate_status}.",
        )

    dispute.grounds_of_appeal = payload.grounds_of_appeal
    dispute.counter_evidence_urls = payload.evidence_documents or []
    await db.commit()

    return Message(
        detail=(
            "Appeal filed. An appellate officer will review your submission "
            "alongside the original inspection evidence."
        ),
        code="APPEAL_FILED",
    )


@router.get("/disputes", response_model=list[DisputeOut])
async def appellate_queue(
    user: SeniorUser,
    db: DbSession,
    pending_only: bool = Query(True),
) -> list[DisputeOut]:
    """Appellate officer's queue of filed appeals."""
    stmt = select(BrandDispute).options(selectinload(BrandDispute.session))
    if pending_only:
        stmt = stmt.where(
            BrandDispute.appellate_status == AppellateStatus.UNDER_REVIEW,
            BrandDispute.grounds_of_appeal.isnot(None),
        )
    rows = (
        await db.execute(stmt.order_by(BrandDispute.created_at.asc()))
    ).scalars().all()

    out = []
    for d in rows:
        item = DisputeOut.model_validate(d)
        item.window_days = settings.DISPUTE_WINDOW_DAYS
        if d.session:
            item.session_ref = d.session.session_id
            item.product_name = d.session.product_name
            item.store_name = d.session.store_name
            item.overall_score = d.session.overall_score
            item.estimated_penalty = d.session.estimated_penalty
        out.append(item)
    return out


@router.post("/disputes/{dispute_token}/decide", response_model=Message)
async def decide_dispute(
    dispute_token: str, payload: DisputeDecision, user: SeniorUser, db: DbSession
) -> Message:
    """Appellate decision on a filed appeal."""
    dispute = (
        await db.execute(
            select(BrandDispute)
            .where(BrandDispute.dispute_token == dispute_token)
            .options(selectinload(BrandDispute.session))
        )
    ).scalar_one_or_none()
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute token not recognised")
    if not dispute.grounds_of_appeal:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No appeal has been filed against this notice yet.",
        )

    dispute.appellate_status = payload.decision
    dispute.appellate_officer_id = user.id
    dispute.appellate_remarks = payload.remarks
    dispute.decided_at = datetime.now(timezone.utc)

    if dispute.session:
        dispute.session.status = (
            SessionStatus.RESOLVED
            if payload.decision == AppellateStatus.ACCEPTED
            else SessionStatus.FLAGGED
        )

    await db.commit()
    return Message(
        detail=(
            "Appeal accepted; the notice has been withdrawn."
            if payload.decision == AppellateStatus.ACCEPTED
            else "Appeal rejected; the notice stands."
        ),
        code=payload.decision,
    )


@router.get("/dashboard")
async def brand_dashboard(user: BrandUser, db: DbSession) -> dict:
    """A brand's own compliance position."""
    certs = (
        await db.execute(
            select(BrandPreCert).where(BrandPreCert.brand_id == user.id)
        )
    ).scalars().all()

    sessions = (
        await db.execute(
            select(InspectionSession)
            .where(InspectionSession.brand_name == user.brand_name)
            .options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()

    disputes = (
        await db.execute(
            select(BrandDispute).where(BrandDispute.brand_id == user.id)
        )
    ).scalars().all()

    scores = [s.overall_score for s in sessions if s.overall_score is not None]
    fails: dict[str, int] = {}
    for s in sessions:
        for v in s.violations:
            if v.status == "FAIL":
                fails[v.rule_name or v.rule_id] = fails.get(v.rule_name or v.rule_id, 0) + 1

    return {
        "brand_name": user.brand_name,
        "field_inspections": {
            "total": len(sessions),
            "avg_compliance_score": round(sum(scores) / len(scores), 1) if scores else None,
            "flagged": len([s for s in sessions if s.status == SessionStatus.FLAGGED]),
            "penalty_exposure": round(
                sum(s.estimated_penalty or 0 for s in sessions), 2
            ),
        },
        "pre_certifications": {
            "total": len(certs),
            "approved": len([c for c in certs if c.is_approved]),
            "rejected": len([c for c in certs if not c.is_approved]),
            "badges_issued": len([c for c in certs if c.digital_badge_token]),
        },
        "disputes": {
            "total": len(disputes),
            "under_review": len(
                [d for d in disputes if d.appellate_status == AppellateStatus.UNDER_REVIEW]
            ),
            "accepted": len(
                [d for d in disputes if d.appellate_status == AppellateStatus.ACCEPTED]
            ),
        },
        "most_common_findings": [
            {"finding": k, "count": v}
            for k, v in sorted(fails.items(), key=lambda kv: -kv[1])[:5]
        ],
        "guidance": (
            "Recurring findings usually trace to a single artwork template. "
            "Submitting your die-line to the pre-certification sandbox before "
            "the next print run will catch them at zero cost."
            if fails
            else "No open field findings against this brand."
        ),
    }
