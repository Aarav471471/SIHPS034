"""Officer intelligence APIs -- spec routes/officer.py, section 6.B.

Predictive patrol routing, the citizen-lead queue, and the senior peer-review
queue. This is the pillar that changes how an officer spends their day.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from core.deps import DbSession, OfficerUser, SeniorUser
from core.geofence import bounding_box, haversine_km
from core.reputation import apply_verdict
from intelligence.agency_graph import propagate_to_retailers
from intelligence.festival_calendar import upcoming
from intelligence.price_gouging_radar import (
    analyse_barcode,
    cluster_hotspots,
    window_start,
)
from intelligence.risk_routing_engine import StoreRisk, build_route, score_store, weighted_history
from models.base import age_days, as_utc
from models.citizen_report import CitizenReport
from models.cross_agency import CrossAgencyLink
from models.enums import PeerReviewStatus, ReportStatus, SessionStatus
from models.inspection_session import InspectionSession
from models.peer_review import PeerReview
from models.price_history import PriceHistoryScan
from models.user import User
from models.violation import Violation
from schemas.common import Message
from schemas.officer import (
    LeadOut,
    LeadVerdict,
    PeerReviewOut,
    RadarSummary,
)

logger = logging.getLogger("metrix.officer")
router = APIRouter(prefix="/officer", tags=["Officer Intelligence"])


# ===========================================================================
# Predictive patrol routing -- spec 3.C
# ===========================================================================
@router.get("/route-suggestions")
async def route_suggestions(
    user: OfficerUser,
    db: DbSession,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=None, gt=0, le=100),
    max_stops: int = Query(default=None, ge=1, le=20),
) -> dict:
    """Today's priority patrol route, ordered for travel and risk."""
    reach = radius_km or settings.ROUTE_DEFAULT_RADIUS_KM
    stops = max_stops or settings.ROUTE_MAX_STOPS
    today = date.today()

    # Cheap bounding-box prefilter before paying for haversine per row.
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, reach)

    sessions = (
        await db.execute(
            select(InspectionSession)
            .where(
                InspectionSession.latitude.between(min_lat, max_lat),
                InspectionSession.longitude.between(min_lng, max_lng),
                InspectionSession.store_name.isnot(None),
            )
            .options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()

    reports = (
        await db.execute(
            select(CitizenReport).where(
                CitizenReport.latitude.between(min_lat, max_lat),
                CitizenReport.longitude.between(min_lng, max_lng),
            )
        )
    ).scalars().all()

    anomalies = (
        await db.execute(
            select(PriceHistoryScan).where(
                PriceHistoryScan.is_anomalous.is_(True),
                PriceHistoryScan.latitude.between(min_lat, max_lat),
                PriceHistoryScan.longitude.between(min_lng, max_lng),
                PriceHistoryScan.scanned_at >= window_start(),
            )
        )
    ).scalars().all()

    # Brand-level regulatory risk propagates to the shops that stock them.
    agency_rows = (await db.execute(select(CrossAgencyLink))).scalars().all()
    brand_risk = {a.brand_name: a.risk_index for a in agency_rows}

    # --- assemble per-store evidence ---
    stores: dict[str, dict] = defaultdict(
        lambda: {
            "lat": [], "lng": [], "address": None,
            "violation_dates": [], "violations": 0,
            "leads": 0, "verified_leads": 0,
            "anomalies": 0, "max_over": 0.0,
            "last_inspected": None, "categories": defaultdict(int),
            "brands": set(),
        }
    )

    for s in sessions:
        if s.latitude is None or s.longitude is None:
            continue
        slot = stores[s.store_name]
        slot["lat"].append(s.latitude)
        slot["lng"].append(s.longitude)
        slot["address"] = slot["address"] or s.location_address
        fails = [v for v in s.violations if v.status == "FAIL"]
        slot["violations"] += len(fails)
        slot["violation_dates"].extend(s.created_at for _ in fails)
        if s.created_at and (slot["last_inspected"] is None or s.created_at > slot["last_inspected"]):
            slot["last_inspected"] = s.created_at
        if s.product_category:
            slot["categories"][s.product_category] += 1
        if s.brand_name:
            slot["brands"].add(s.brand_name)

    for r in reports:
        if r.latitude is None or r.longitude is None:
            continue
        slot = stores[r.store_name]
        slot["lat"].append(r.latitude)
        slot["lng"].append(r.longitude)
        slot["address"] = slot["address"] or r.store_address
        slot["leads"] += 1
        if r.status == ReportStatus.VERIFIED:
            slot["verified_leads"] += 1

    for a in anomalies:
        if not a.store_name or a.latitude is None:
            continue
        slot = stores[a.store_name]
        slot["lat"].append(a.latitude)
        slot["lng"].append(a.longitude)
        slot["anomalies"] += 1
        slot["max_over"] = max(slot["max_over"], a.overcharge_pct or 0.0)

    # --- score ---
    from models.category import Category

    cats = (await db.execute(select(Category))).scalars().all()
    slug_by_name = {c.name: c.slug for c in cats}

    risks: list[StoreRisk] = []
    for name, data in stores.items():
        if not data["lat"]:
            continue
        centre_lat = sum(data["lat"]) / len(data["lat"])
        centre_lng = sum(data["lng"]) / len(data["lng"])
        if haversine_km(lat, lng, centre_lat, centre_lng) > reach:
            continue

        days_since = age_days(data["last_inspected"])
        top_cats = [
            slug_by_name.get(c, c)
            for c, _n in sorted(data["categories"].items(), key=lambda kv: -kv[1])[:3]
        ]

        sr = StoreRisk(
            store_name=name,
            latitude=centre_lat,
            longitude=centre_lng,
            address=data["address"],
            historical_violations=data["violations"],
            weighted_history=weighted_history(data["violation_dates"]),
            citizen_leads=data["leads"],
            verified_leads=data["verified_leads"],
            price_anomalies=data["anomalies"],
            max_overcharge_pct=data["max_over"],
            days_since_inspection=days_since,
            top_categories=top_cats,
        )
        sr = score_store(sr, on=today)

        # Fold in supply-side regulatory risk.
        brand_contrib, brand_reasons = propagate_to_retailers(
            brand_risk, sorted(data["brands"])
        )
        if brand_contrib:
            sr.risk_score = round(min(100.0, sr.risk_score + brand_contrib * 2.0), 2)
            sr.risk_reasons.extend(brand_reasons)
            sr.components["supply_chain"] = round(brand_contrib * 2.0, 2)

        risks.append(sr)

    route = build_route(risks, lat, lng, max_stops=stops, radius_km=reach, on=today)
    payload = route.to_dict()
    payload["officer"] = {
        "name": user.full_name,
        "officer_id": user.officer_id,
        "jurisdiction": user.jurisdiction_name,
    }
    payload["candidates_considered"] = len(risks)
    payload["upcoming_festivals"] = upcoming(within_days=30)[:3]
    return payload


# ===========================================================================
# Citizen lead queue
# ===========================================================================
@router.get("/leads", response_model=list[LeadOut])
async def lead_queue(
    user: OfficerUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> list[LeadOut]:
    """Citizen reports ordered by reporter trust -- spec 3.B."""
    stmt = select(CitizenReport).options(selectinload(CitizenReport.reporter))
    stmt = stmt.where(
        CitizenReport.status == (status_filter or ReportStatus.SUBMITTED)
    )
    rows = (
        await db.execute(
            stmt.order_by(
                CitizenReport.priority_score.desc(), CitizenReport.created_at.asc()
            ).limit(limit)
        )
    ).scalars().all()

    out = []
    for r in rows:
        item = LeadOut.model_validate(r)
        if r.reporter:
            item.reporter_name = (r.reporter.full_name or r.reporter.username).split()[0]
            item.reporter_trust_score = r.reporter.citizen_trust_score
            item.reporter_verified = r.reporter.verified_reporter
        item.image_url = None
        if r.image_path:
            from core.storage import get_storage

            try:
                item.image_url = get_storage().url_for(r.image_path)
            except Exception:
                pass
        out.append(item)
    return out


@router.post("/leads/{report_ref}/verdict", response_model=Message)
async def decide_lead(
    report_ref: str, payload: LeadVerdict, user: OfficerUser, db: DbSession
) -> Message:
    """Record an officer's finding on a citizen report.

    This is the feedback loop that makes the trust score mean something: the
    verdict adjusts the reporter's standing, which changes where their next
    report lands in this queue.
    """
    report = (
        await db.execute(
            select(CitizenReport)
            .where(CitizenReport.report_ref == report_ref)
            .options(selectinload(CitizenReport.reporter))
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Report {report_ref} not found")

    if report.status in (ReportStatus.VERIFIED, ReportStatus.REJECTED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This report was already decided as {report.status}.",
        )

    report.status = payload.verdict
    report.officer_notes = payload.notes
    report.assigned_officer_id = user.id
    if payload.verdict in (ReportStatus.VERIFIED, ReportStatus.REJECTED):
        report.verified_at = datetime.now(timezone.utc)

    trust_note = "Reporter trust score unchanged."
    if report.reporter:
        update = apply_verdict(report.reporter.citizen_trust_score, payload.verdict)
        report.reporter.citizen_trust_score = update.new_score
        report.reporter.verified_reporter = (
            update.new_score > settings.TRUST_SCORE_VERIFIED_THRESHOLD
        )
        if payload.verdict == ReportStatus.VERIFIED:
            report.reporter.reports_confirmed = (report.reporter.reports_confirmed or 0) + 1
        if update.delta:
            trust_note = (
                f"Reporter trust {update.previous_score:.0f} -> {update.new_score:.0f} "
                f"({update.delta:+.0f})."
            )
            if update.badge_changed:
                trust_note += f" Badge is now {update.badge}."

    await db.commit()
    return Message(
        detail=f"Report {report_ref} recorded as {payload.verdict}. {trust_note}",
        code=payload.verdict,
    )


# ===========================================================================
# Peer review queue -- spec 3.E
# ===========================================================================
@router.get("/peer-reviews/pending", response_model=list[PeerReviewOut])
async def pending_peer_reviews(
    user: SeniorUser, db: DbSession, limit: int = Query(50, ge=1, le=200)
) -> list[PeerReviewOut]:
    """Senior officer queue of escalated cases."""
    rows = (
        await db.execute(
            select(PeerReview)
            .where(PeerReview.review_status == PeerReviewStatus.PENDING)
            .options(
                selectinload(PeerReview.session).selectinload(InspectionSession.violations),
                selectinload(PeerReview.requested_by),
            )
            .order_by(PeerReview.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    out = []
    for r in rows:
        item = PeerReviewOut.model_validate(r)
        if r.session:
            item.session_ref = r.session.session_id
            item.brand_name = r.session.brand_name
            item.product_name = r.session.product_name
            item.store_name = r.session.store_name
            item.overall_score = r.session.overall_score
            item.estimated_penalty = r.session.estimated_penalty
            item.violation_count = len(
                [v for v in r.session.violations if v.status == "FAIL"]
            )
        if r.requested_by:
            item.requested_by_name = r.requested_by.full_name
        out.append(item)
    return out


# ===========================================================================
# Radar summary for the officer dashboard
# ===========================================================================
@router.get("/radar", response_model=RadarSummary)
async def radar_summary(
    user: OfficerUser,
    db: DbSession,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = Query(15.0, gt=0, le=200),
    limit_products: int = Query(40, ge=1, le=200),
) -> RadarSummary:
    """Price-gouging hotspots in this officer's area."""
    since = window_start()
    stmt = select(PriceHistoryScan).where(PriceHistoryScan.scanned_at >= since)

    if lat is not None and lng is not None:
        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
        stmt = stmt.where(
            PriceHistoryScan.latitude.between(min_lat, max_lat),
            PriceHistoryScan.longitude.between(min_lng, max_lng),
        )

    rows = (await db.execute(stmt.limit(8000))).scalars().all()

    by_barcode: dict[str, list[PriceHistoryScan]] = defaultdict(list)
    for r in rows:
        by_barcode[r.barcode].append(r)

    all_findings = []
    for barcode, scans in list(by_barcode.items())[:limit_products]:
        payload = [
            {
                "scanned_mrp": s.scanned_mrp,
                "store_name": s.store_name,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "scanned_at": s.scanned_at,
                "scanned_by_user_id": s.scanned_by_user_id,
            }
            for s in scans
        ]
        _stats, findings, _note = analyse_barcode(
            barcode, payload,
            product_name=scans[0].product_name,
            brand_name=scans[0].brand_name,
        )
        all_findings.extend(findings)

    hotspots = cluster_hotspots(all_findings)

    return RadarSummary(
        window_days=settings.RADAR_WINDOW_DAYS,
        scans_analysed=len(rows),
        products_analysed=min(len(by_barcode), limit_products),
        findings=len(all_findings),
        priority_findings=len([f for f in all_findings if f.severity == "PRIORITY"]),
        hotspots=[h.to_dict() for h in hotspots[:12]],
        top_findings=[f.to_dict() for f in sorted(
            all_findings, key=lambda f: -f.overcharge_pct
        )[:15]],
    )


@router.get("/dashboard")
async def officer_dashboard(user: OfficerUser, db: DbSession) -> dict:
    """Headline counters for the officer's home screen."""
    mine = InspectionSession.officer_id == user.id
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    async def count(stmt) -> int:
        return (await db.execute(stmt)).scalar_one()

    total = await count(select(func.count(InspectionSession.id)).where(mine))
    this_week = await count(
        select(func.count(InspectionSession.id)).where(mine, InspectionSession.created_at >= week_ago)
    )
    flagged = await count(
        select(func.count(InspectionSession.id)).where(
            mine, InspectionSession.status == SessionStatus.FLAGGED
        )
    )
    pending_leads = await count(
        select(func.count(CitizenReport.id)).where(
            CitizenReport.status == ReportStatus.SUBMITTED
        )
    )
    awaiting_review = await count(
        select(func.count(PeerReview.id)).where(
            PeerReview.review_status == PeerReviewStatus.PENDING
        )
    )
    penalty = (
        await db.execute(select(func.sum(InspectionSession.estimated_penalty)).where(mine))
    ).scalar() or 0.0

    return {
        "officer": {
            "name": user.full_name,
            "officer_id": user.officer_id,
            "jurisdiction": user.jurisdiction_name,
            "is_senior": user.is_senior,
        },
        "inspections": {
            "total": total,
            "this_week": this_week,
            "flagged": flagged,
            "penalty_exposure": round(penalty, 2),
        },
        "queues": {
            "citizen_leads_pending": pending_leads,
            "peer_reviews_pending": awaiting_review,
        },
        "upcoming_festivals": upcoming(within_days=30)[:3],
    }
