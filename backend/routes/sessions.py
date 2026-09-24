"""Multi-surface inspection sessions -- spec routes/sessions.py.

The officer's core workflow:

    POST /inspections/session                  open a session
    POST /inspections/{id}/images              upload each surface (hash-sealed)
    POST /inspections/{id}/process             run the six-stage pipeline
    GET  /inspections/{id}                     results with evidence crops
    POST /inspections/{id}/escalate            send to senior peer review

Uploads are sealed on arrival and the session locks once processed, so the
evidence set behind a notice cannot be altered after the fact.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from core.deps import CurrentUser, DbSession, OfficerUser
from core.geofence import point_in_jurisdiction
from core.phash import compute_phash, find_duplicate
from core.security import generate_token, seal_evidence, sha256_bytes
from core.storage import build_key, get_storage
from core.task_runner import dispatch
from models.enums import (
    PeerReviewStatus,
    PeerReviewTrigger,
    SessionStatus,
    SourceType,
    SurfaceType,
    UserRole,
)
from models.extracted_field import ExtractedField
from models.inspection_session import InspectionSession
from models.peer_review import PeerReview
from models.session_image import SessionImage
from models.violation import Violation
from schemas.common import Message
from schemas.inspection import (
    EscalateRequest,
    ExtractedFieldOut,
    ImageUploadResponse,
    PeerReviewDecision,
    ProcessResponse,
    SessionCreate,
    SessionDetail,
    SessionImageOut,
    SessionListResponse,
    SessionSummary,
    ViolationOut,
)

logger = logging.getLogger("metrix.sessions")
router = APIRouter(prefix="/inspections", tags=["Inspections"])

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"}


def _url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return get_storage().url_for(path)
    except Exception:
        return None


async def _load(db, session_id: str, *, full: bool = False) -> InspectionSession:
    stmt = select(InspectionSession).where(InspectionSession.session_id == session_id)
    if full:
        stmt = stmt.options(
            selectinload(InspectionSession.images),
            selectinload(InspectionSession.fields),
            selectinload(InspectionSession.violations),
            selectinload(InspectionSession.officer),
        )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Session {session_id} not found")
    return obj


# ===========================================================================
@router.post("/session", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate, user: OfficerUser, db: DbSession
) -> SessionSummary:
    """Open an inspection session and stamp it against the officer's territory."""
    geo = point_in_jurisdiction(
        payload.latitude, payload.longitude,
        user.jurisdiction_geojson, user.jurisdiction_name,
    )

    area = None
    if payload.package_width_cm and payload.package_height_cm:
        area = round(payload.package_width_cm * payload.package_height_cm, 2)

    session = InspectionSession(
        session_id=generate_token("sess", 10),
        officer_id=user.id,
        source_type=SourceType.OFFICER,
        status=SessionStatus.PENDING,
        product_name=payload.product_name,
        brand_name=payload.brand_name,
        barcode=payload.barcode,
        category_id=payload.category_id,
        product_category=payload.product_category,
        package_width_cm=payload.package_width_cm,
        package_height_cm=payload.package_height_cm,
        surface_area_cm2=area,
        latitude=payload.latitude,
        longitude=payload.longitude,
        store_name=payload.store_name,
        location_address=payload.location_address,
        jurisdiction_status=geo.status,
        created_at=payload.captured_at or datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    out = SessionSummary.model_validate(session)
    out.violation_count = 0
    return out


@router.post(
    "/{session_id}/images",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_surface(
    session_id: str,
    user: OfficerUser,
    db: DbSession,
    file: UploadFile = File(...),
    surface_type: str = Form(default=SurfaceType.FRONT),
) -> ImageUploadResponse:
    """Upload one surface. Sealed with SHA-256 on arrival."""
    session = await _load(db, session_id, full=True)

    if session.is_locked:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This session is locked; its evidence set can no longer be modified.",
        )
    if session.officer_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your inspection session")

    if file.content_type and file.content_type.lower() not in ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported image type {file.content_type}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Image exceeds the {settings.MAX_UPLOAD_MB} MB limit",
        )

    digest = sha256_bytes(data)

    # The hash is UNIQUE in the schema, so the same photograph physically
    # cannot enter evidence twice.
    clash = (
        await db.execute(select(SessionImage).where(SessionImage.sha256_hash == digest))
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This exact image has already been submitted as evidence "
            f"(session image #{clash.id}).",
        )

    # Perceptual hash catches the same photo re-encoded or resized -- which
    # SHA-256 cannot. Reported as a warning: a legitimate re-shoot of the same
    # panel looks similar too, so this is for the officer to judge.
    phash = compute_phash(data)
    duplicate_warning = None
    if phash:
        existing = [i.perceptual_hash for i in session.images if i.perceptual_hash]
        match = find_duplicate(phash, existing)
        if match.is_duplicate:
            duplicate_warning = match.reason

    width = height = None
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
    except Exception as exc:
        logger.debug("Could not read image dimensions: %s", exc)

    key = build_key("uploads", f"{session.session_id}_{surface_type}_{digest[:8]}.jpg")
    get_storage().save(key, data, file.content_type or "image/jpeg")

    image = SessionImage(
        session_id=session.id,
        surface_type=surface_type.upper(),
        image_path=key,
        sha256_hash=digest,
        perceptual_hash=phash,
        image_width_px=width,
        image_height_px=height,
        file_size_bytes=len(data),
    )
    db.add(image)

    # Re-seal the session across its full evidence set.
    hashes = [i.sha256_hash for i in session.images] + [digest]
    session.evidence_seal = seal_evidence(session.session_id, hashes)

    await db.commit()
    await db.refresh(image)

    return ImageUploadResponse(
        image_id=image.id,
        surface_type=image.surface_type,
        sha256_hash=digest,
        perceptual_hash=phash,
        width_px=width,
        height_px=height,
        size_bytes=len(data),
        url=_url(key),
        duplicate_warning=duplicate_warning,
    )


@router.post("/{session_id}/process", response_model=ProcessResponse)
async def process_session(
    session_id: str, user: OfficerUser, db: DbSession
) -> ProcessResponse:
    """Queue the six-stage inspection pipeline."""
    session = await _load(db, session_id, full=True)

    if not session.images:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Upload at least one surface before processing.",
        )
    if session.status == SessionStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This session is already processing.")
    if session.is_locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "This session is locked.")

    # Re-running replaces prior findings rather than appending to them.
    for table in (ExtractedField, Violation):
        for row in (
            await db.execute(select(table).where(table.session_id == session.id))
        ).scalars():
            await db.delete(row)

    session.status = SessionStatus.PENDING
    session.processing_error = None
    await db.commit()

    handle = dispatch("pipeline.process_session", session.id)

    return ProcessResponse(
        session_id=session.session_id,
        task_id=handle.task_id,
        status="queued",
        message=(
            f"Inspection queued across {len(session.images)} surface(s). "
            "Subscribe to the WebSocket for live pipeline progress."
        ),
        websocket_url=f"/api/ws/sessions/{session.session_id}",
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    mine: bool = Query(False, description="Restrict to the caller's own sessions"),
    search: str | None = None,
) -> SessionListResponse:
    stmt = select(InspectionSession)
    count_stmt = select(func.count(InspectionSession.id))

    if status_filter:
        stmt = stmt.where(InspectionSession.status == status_filter)
        count_stmt = count_stmt.where(InspectionSession.status == status_filter)
    if mine or user.role == UserRole.OFFICER:
        stmt = stmt.where(InspectionSession.officer_id == user.id)
        count_stmt = count_stmt.where(InspectionSession.officer_id == user.id)
    if search:
        like = f"%{search}%"
        cond = (
            InspectionSession.brand_name.ilike(like)
            | InspectionSession.product_name.ilike(like)
            | InspectionSession.store_name.ilike(like)
            | InspectionSession.barcode.ilike(like)
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(InspectionSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()

    items = []
    for s in rows:
        summary = SessionSummary.model_validate(s)
        summary.violation_count = len([v for v in s.violations if v.status == "FAIL"])
        items.append(summary)

    return SessionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, user: CurrentUser, db: DbSession) -> SessionDetail:
    """Full session with evidence crops, for officer review and the notice."""
    session = await _load(db, session_id, full=True)

    detail = SessionDetail.model_validate(session)
    detail.violation_count = len([v for v in session.violations if v.status == "FAIL"])

    if session.officer:
        detail.officer_name = session.officer.full_name
        detail.officer_id_code = session.officer.officer_id

    detail.images = []
    for img in session.images:
        out = SessionImageOut.model_validate(img)
        out.url = _url(img.image_path)
        detail.images.append(out)

    detail.fields = []
    for f in sorted(session.fields, key=lambda x: x.field_name):
        out = ExtractedFieldOut.model_validate(f)
        out.crop_url = _url(f.raw_pixel_crop_path)
        out.effective_confidence = f.effective_confidence
        detail.fields.append(out)

    # Most severe findings first -- an officer reads the top of the list.
    order = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    detail.violations = []
    for v in sorted(
        session.violations,
        key=lambda x: (order.get(x.severity or "MAJOR", 3), x.rule_id),
    ):
        out = ViolationOut.model_validate(v)
        out.crop_url = _url(v.evidence_crop_path)
        detail.violations.append(out)

    return detail


@router.post("/{session_id}/escalate", response_model=Message)
async def escalate(
    session_id: str, payload: EscalateRequest, user: OfficerUser, db: DbSession
) -> Message:
    """Refer a borderline case to senior peer review -- spec 3.E."""
    session = await _load(db, session_id)

    existing = (
        await db.execute(
            select(PeerReview).where(
                PeerReview.session_id == session.id,
                PeerReview.review_status == PeerReviewStatus.PENDING,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This session is already awaiting peer review."
        )

    db.add(PeerReview(
        session_id=session.id,
        requested_by_id=user.id,
        trigger_reason=PeerReviewTrigger.MANUAL,
        trigger_detail=payload.reason or "Referred manually by the inspecting officer",
        triggering_confidence=session.confidence_score,
    ))
    session.status = SessionStatus.PEER_REVIEW
    await db.commit()

    return Message(detail="Referred to senior officer review", code="ESCALATED")


@router.post("/{session_id}/peer-review", response_model=Message)
async def decide_peer_review(
    session_id: str, payload: PeerReviewDecision, user: CurrentUser, db: DbSession
) -> Message:
    """Senior officer's decision on an escalated case."""
    if not user.is_senior:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a senior officer may decide a peer review.",
        )

    session = await _load(db, session_id)
    review = (
        await db.execute(
            select(PeerReview)
            .where(
                PeerReview.session_id == session.id,
                PeerReview.review_status == PeerReviewStatus.PENDING,
            )
            .order_by(PeerReview.created_at.desc())
        )
    ).scalars().first()

    if review is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No pending peer review for this session."
        )

    review.review_status = payload.decision
    review.reviewer_id = user.id
    review.reviewer_remarks = payload.remarks
    review.reviewed_at = datetime.now(timezone.utc)

    if payload.decision == PeerReviewStatus.APPROVED:
        session.status = SessionStatus.FLAGGED
        session.is_locked = True
    elif payload.decision == PeerReviewStatus.REJECTED:
        session.status = SessionStatus.RESOLVED
        session.is_locked = True
    else:
        session.status = SessionStatus.COMPLETED

    await db.commit()
    return Message(
        detail=f"Peer review recorded as {payload.decision}",
        code=payload.decision,
    )


@router.get("/{session_id}/evidence-seal", response_model=dict)
async def verify_evidence_seal(session_id: str, user: CurrentUser, db: DbSession) -> dict:
    """Re-verify the tamper-evident seal over a session's evidence set."""
    session = await _load(db, session_id, full=True)
    hashes = [i.sha256_hash for i in session.images]
    expected = seal_evidence(session.session_id, hashes)
    intact = bool(session.evidence_seal) and session.evidence_seal == expected

    return {
        "session_id": session.session_id,
        "seal": session.evidence_seal,
        "recomputed": expected,
        "intact": intact,
        "image_count": len(hashes),
        "image_hashes": hashes,
        "verdict": (
            "Evidence set is intact and matches the recorded seal."
            if intact
            else "SEAL MISMATCH: the evidence set has changed since it was sealed."
        ),
    }
