"""Consumer APIs -- spec routes/consumer.py, section 6.A.

"Scan Before You Buy", citizen reporting with the gamified trust score, and the
alert inbox.

The scan endpoint is the one a shopper uses standing at a shelf, so it works
without an account. Signing in adds personalisation (alerts, trust score) but is
never a precondition for finding out whether you are being overcharged.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.config import settings
from core.deps import ConsumerUser, CurrentUser, DbSession, OptionalUser
from core.reputation import (
    apply_verdict,
    category_weight,
    is_rate_limited,
    priority_score,
)
from core.security import generate_reference, sha256_bytes
from core.storage import build_key, get_storage
from intelligence.price_gouging_radar import (
    analyse_barcode,
    check_scan,
    compute_price_stats,
    window_start,
)
from models.category import Category
from models.citizen_report import CitizenReport
from models.consumer_alert import ConsumerAlert
from models.enums import ReportStatus, UserRole, badge_for_score
from models.inspection_session import InspectionSession
from models.price_history import PriceHistoryScan
from models.product import Product
from models.user import User
from models.violation import Violation
from schemas.common import Message
from schemas.consumer import (
    AlertOut,
    CitizenReportOut,
    ReportSubmitResponse,
    ScanResponse,
    TrustProfile,
)

logger = logging.getLogger("metrix.consumer")
router = APIRouter(prefix="/consumer", tags=["Consumer"])


@router.get("/scan", response_model=ScanResponse)
async def scan_before_you_buy(
    db: DbSession,
    user: OptionalUser,
    barcode: str = Query(min_length=6, max_length=20),
    mrp: float | None = Query(default=None, ge=0, description="Price printed on the pack"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    store_name: str | None = None,
) -> ScanResponse:
    """Instant compliance and price verdict for a scanned barcode.

    Anonymous by design -- a shopper must be able to check a price without
    creating an account first.
    """
    digits = "".join(ch for ch in barcode if ch.isdigit())

    product = (
        await db.execute(select(Product).where(Product.barcode == digits))
    ).scalar_one_or_none()

    # --- price history for the radar baseline ---
    since = window_start()
    rows = (
        await db.execute(
            select(PriceHistoryScan)
            .where(PriceHistoryScan.barcode == digits, PriceHistoryScan.scanned_at >= since)
            .order_by(PriceHistoryScan.scanned_at.desc())
            .limit(500)
        )
    ).scalars().all()

    stats = compute_price_stats([r.scanned_mrp for r in rows], digits)
    verdict = check_scan(mrp, product.official_mrp if product else None, stats)

    # --- compliance history ---
    last_inspected = None
    past_violations = 0
    if product:
        last_inspected = product.last_inspected_at
        past_violations = (
            await db.execute(
                select(func.count(Violation.id))
                .select_from(Violation)
                .join(InspectionSession, Violation.session_id == InspectionSession.id)
                .where(
                    InspectionSession.barcode == digits,
                    Violation.status == "FAIL",
                )
            )
        ).scalar_one()

    # --- record the scan (this is what feeds the radar) ---
    if mrp and mrp > 0:
        db.add(PriceHistoryScan(
            barcode=digits,
            product_name=product.product_name if product else None,
            brand_name=product.brand_name if product else None,
            scanned_mrp=mrp,
            modal_mrp_at_scan=stats.modal_mrp,
            scanned_by_user_id=user.id if user else None,
            source="CONSUMER",
            store_name=store_name,
            latitude=lat,
            longitude=lng,
            is_anomalous=verdict.is_gouged,
            anomaly_reason=verdict.warning,
            overcharge_pct=verdict.overcharge_pct,
        ))
        await db.commit()

    if product is None:
        return ScanResponse(
            barcode=digits,
            found=False,
            message=(
                "This barcode is not yet in the compliance catalogue. Your scan has "
                "been recorded and will help build the price history for this product."
            ),
            scanned_mrp=mrp,
            is_price_gouged=verdict.is_gouged,
            anomaly_warning=verdict.warning,
            crowd_modal_mrp=stats.modal_mrp,
            crowd_sample_count=stats.usable_count,
        )

    unit_price = product.unit_price_display
    score = product.avg_score

    return ScanResponse(
        barcode=digits,
        found=True,
        product_name=product.product_name,
        brand_name=product.brand_name,
        category=product.category.name if product.category else None,
        official_mrp=product.official_mrp,
        net_quantity=product.net_quantity,
        unit_price=f"Rs. {unit_price}" if unit_price else None,
        country_of_origin=product.country_of_origin,
        compliance_score=int(score) if score is not None else None,
        badge_level=product.badge_level or badge_for_score(score),
        fssai_number=product.fssai_number,
        fssai_verified=bool(product.fssai_number),
        past_violations=past_violations,
        total_inspections=product.total_inspections,
        last_inspected=last_inspected,
        scanned_mrp=mrp,
        is_price_gouged=verdict.is_gouged,
        gouging_severity=verdict.severity,
        overcharge_amount=verdict.overcharge_amount,
        overcharge_pct=verdict.overcharge_pct,
        anomaly_warning=verdict.warning,
        crowd_modal_mrp=stats.modal_mrp,
        crowd_sample_count=stats.usable_count,
        message=(
            verdict.warning
            if verdict.is_gouged
            else "The price on this pack matches its declared MRP."
            if mrp
            else "Scan the printed price to check for overcharging."
        ),
    )


@router.get("/price-history/{barcode}")
async def price_history(barcode: str, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict:
    """Price trend and any detected gouging hotspots for a commodity."""
    digits = "".join(ch for ch in barcode if ch.isdigit())
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        await db.execute(
            select(PriceHistoryScan)
            .where(PriceHistoryScan.barcode == digits, PriceHistoryScan.scanned_at >= since)
            .order_by(PriceHistoryScan.scanned_at.asc())
        )
    ).scalars().all()

    product = (
        await db.execute(select(Product).where(Product.barcode == digits))
    ).scalar_one_or_none()

    scans = [
        {
            "scanned_mrp": r.scanned_mrp,
            "store_name": r.store_name,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "scanned_at": r.scanned_at,
            "scanned_by_user_id": r.scanned_by_user_id,
        }
        for r in rows
    ]
    stats, findings, revision_note = analyse_barcode(
        digits, scans,
        product_name=product.product_name if product else None,
        brand_name=product.brand_name if product else None,
    )

    return {
        "barcode": digits,
        "product_name": product.product_name if product else None,
        "official_mrp": product.official_mrp if product else None,
        "window_days": days,
        "statistics": {
            "modal_mrp": stats.modal_mrp,
            "median_mrp": stats.median_mrp,
            "sample_count": stats.sample_count,
            "usable_count": stats.usable_count,
            "outliers_rejected": stats.outliers_rejected,
            "price_spread": stats.price_spread,
            "confidence": stats.confidence,
            "is_stable": stats.is_stable,
            "note": stats.note,
        },
        "market_revision_detected": revision_note,
        "gouging_findings": [f.to_dict() for f in findings],
        "series": [
            {
                "date": r.scanned_at.isoformat(),
                "mrp": r.scanned_mrp,
                "store": r.store_name,
                "anomalous": r.is_anomalous,
            }
            for r in rows
        ],
    }


@router.post(
    "/report", response_model=ReportSubmitResponse, status_code=status.HTTP_201_CREATED
)
async def submit_citizen_report(
    user: ConsumerUser,
    db: DbSession,
    store_name: str = Form(..., max_length=150),
    violation_category: str = Form(...),
    remarks: str | None = Form(default=None, max_length=2000),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    store_address: str | None = Form(default=None),
    barcode: str | None = Form(default=None),
    claimed_mrp: float | None = Form(default=None),
    charged_price: float | None = Form(default=None),
    image: UploadFile | None = File(default=None),
) -> ReportSubmitResponse:
    """Submit a suspected violation. Queue position follows reporter trust."""
    # --- anti-spam shield ---
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = (
        await db.execute(
            select(func.count(CitizenReport.id)).where(
                CitizenReport.reporter_id == user.id,
                CitizenReport.created_at >= hour_ago,
            )
        )
    ).scalar_one()

    limited, reason = is_rate_limited(recent)
    if limited:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, reason)

    image_path = None
    if image is not None:
        data = await image.read()
        if data:
            if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"Image exceeds the {settings.MAX_UPLOAD_MB} MB limit",
                )
            key = build_key(
                "uploads", f"report_{user.id}_{sha256_bytes(data)[:10]}.jpg"
            )
            get_storage().save(key, data, image.content_type or "image/jpeg")
            image_path = key

    weight = category_weight(violation_category)
    priority = priority_score(
        user.citizen_trust_score,
        weight,
        has_photo=image_path is not None,
        has_gps=latitude is not None and longitude is not None,
    )

    count = (await db.execute(select(func.count(CitizenReport.id)))).scalar_one()
    report = CitizenReport(
        report_ref=generate_reference("rep", 1000 + count + 1),
        reporter_id=user.id,
        store_name=store_name,
        store_address=store_address,
        latitude=latitude,
        longitude=longitude,
        violation_category=violation_category,
        citizen_remarks=remarks,
        image_path=image_path,
        barcode="".join(ch for ch in (barcode or "") if ch.isdigit()) or None,
        claimed_mrp=claimed_mrp,
        charged_price=charged_price,
        status=ReportStatus.SUBMITTED,
        priority_score=priority,
    )
    db.add(report)
    user.reports_submitted = (user.reports_submitted or 0) + 1
    await db.commit()
    await db.refresh(report)

    # Notify any officer dashboard watching the queue.
    try:
        from core.websocket_manager import manager

        await manager.publish_topic("citizen_reports", {
            "event": "new_report",
            "report_ref": report.report_ref,
            "store_name": store_name,
            "category": violation_category,
            "priority_score": priority,
            "verified_reporter": user.verified_reporter,
        })
    except Exception as exc:
        logger.debug("Could not broadcast citizen report: %s", exc)

    guidance = (
        "Your report goes to the top of the officer queue because of your "
        "verified reporter status."
        if user.citizen_trust_score > settings.TRUST_SCORE_VERIFIED_THRESHOLD
        else "Your report has been queued for officer review."
    )
    if image_path is None:
        guidance += " Adding a photograph next time will raise its priority."

    return ReportSubmitResponse(
        report_id=report.report_ref,
        status="QUEUED_FOR_OFFICER_REVIEW",
        reporter_trust_score=user.citizen_trust_score,
        priority_score=priority,
        queue_guidance=guidance,
    )


@router.get("/reports", response_model=list[CitizenReportOut])
async def my_reports(user: ConsumerUser, db: DbSession) -> list[CitizenReportOut]:
    rows = (
        await db.execute(
            select(CitizenReport)
            .where(CitizenReport.reporter_id == user.id)
            .order_by(CitizenReport.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [CitizenReportOut.model_validate(r) for r in rows]


@router.get("/alerts", response_model=list[AlertOut])
async def my_alerts(
    user: CurrentUser,
    db: DbSession,
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertOut]:
    """Recall, expiry and price-surge notices for this consumer."""
    stmt = select(ConsumerAlert).where(ConsumerAlert.user_id == user.id)
    if unread_only:
        stmt = stmt.where(ConsumerAlert.is_read.is_(False))
    rows = (
        await db.execute(stmt.order_by(ConsumerAlert.created_at.desc()).limit(limit))
    ).scalars().all()
    return [AlertOut.model_validate(a) for a in rows]


@router.post("/alerts/{alert_id}/read", response_model=Message)
async def mark_alert_read(alert_id: int, user: CurrentUser, db: DbSession) -> Message:
    alert = (
        await db.execute(
            select(ConsumerAlert).where(
                ConsumerAlert.id == alert_id, ConsumerAlert.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert.is_read = True
    await db.commit()
    return Message(detail="Marked as read")


@router.get("/trust", response_model=TrustProfile)
async def my_trust_profile(user: ConsumerUser, db: DbSession) -> TrustProfile:
    """The gamified reputation view -- spec 3.B."""
    confirmed = (
        await db.execute(
            select(func.count(CitizenReport.id)).where(
                CitizenReport.reporter_id == user.id,
                CitizenReport.status == ReportStatus.VERIFIED,
            )
        )
    ).scalar_one()
    rejected = (
        await db.execute(
            select(func.count(CitizenReport.id)).where(
                CitizenReport.reporter_id == user.id,
                CitizenReport.status == ReportStatus.REJECTED,
            )
        )
    ).scalar_one()
    submitted = (
        await db.execute(
            select(func.count(CitizenReport.id)).where(
                CitizenReport.reporter_id == user.id
            )
        )
    ).scalar_one()

    # Rank among consumers, so the score means something socially.
    better = (
        await db.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.CONSUMER,
                User.citizen_trust_score > user.citizen_trust_score,
            )
        )
    ).scalar_one()
    total = (
        await db.execute(
            select(func.count(User.id)).where(User.role == UserRole.CONSUMER)
        )
    ).scalar_one()

    to_next = max(0.0, settings.TRUST_SCORE_VERIFIED_THRESHOLD + 0.01 - user.citizen_trust_score)
    reports_needed = int(-(-to_next // settings.TRUST_SCORE_CONFIRMED_DELTA)) if to_next else 0

    return TrustProfile(
        trust_score=user.citizen_trust_score,
        badge=user.trust_badge or "CITIZEN",
        verified_reporter=user.verified_reporter,
        reports_submitted=submitted,
        reports_confirmed=confirmed,
        reports_rejected=rejected,
        accuracy_rate=(
            round(confirmed / (confirmed + rejected) * 100, 1)
            if (confirmed + rejected)
            else None
        ),
        rank=better + 1,
        total_reporters=total,
        next_badge=(
            None
            if user.citizen_trust_score > settings.TRUST_SCORE_VERIFIED_THRESHOLD
            else "VERIFIED_VIGILANT_CITIZEN"
        ),
        reports_to_next_badge=reports_needed or None,
        how_it_works=(
            f"A confirmed report adds {settings.TRUST_SCORE_CONFIRMED_DELTA:.0f} points; "
            f"a report found to be false costs {abs(settings.TRUST_SCORE_SPAM_DELTA):.0f}. "
            f"Above {settings.TRUST_SCORE_VERIFIED_THRESHOLD:.0f} you become a Verified "
            "Vigilant Citizen and your reports jump to the top of the officer queue."
        ),
    )


@router.get("/leaderboard")
async def leaderboard(db: DbSession, limit: int = Query(20, ge=1, le=100)) -> dict:
    """Top reporters. First names only -- no full identities on a public board."""
    rows = (
        await db.execute(
            select(User)
            .where(User.role == UserRole.CONSUMER, User.reports_confirmed > 0)
            .order_by(User.citizen_trust_score.desc(), User.reports_confirmed.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "display_name": (u.full_name or u.username).split()[0],
                "trust_score": u.citizen_trust_score,
                "badge": u.trust_badge,
                "reports_confirmed": u.reports_confirmed,
                "verified": u.verified_reporter,
            }
            for i, u in enumerate(rows)
        ],
        "note": (
            "Only first names are shown. Reporter identities are never published."
        ),
    }
