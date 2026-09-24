"""Product compliance audit -- spec routes/products.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from core.deps import DbSession, OptionalUser
from core.storage import get_storage
from intelligence.price_gouging_radar import analyse_barcode, compute_price_stats, window_start
from models.enums import badge_for_score
from models.inspection_session import InspectionSession
from models.price_history import PriceHistoryScan
from models.product import Product

router = APIRouter(prefix="/products", tags=["Catalogue"])


@router.get("")
async def list_products(
    db: DbSession,
    user: OptionalUser,
    search: str | None = None,
    brand: str | None = None,
    category_id: int | None = None,
    badge: str | None = None,
    flagged_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> dict:
    stmt = select(Product)
    count_stmt = select(func.count(Product.id))

    conditions = []
    if search:
        like = f"%{search}%"
        conditions.append(
            or_(Product.product_name.ilike(like), Product.brand_name.ilike(like),
                Product.barcode.ilike(like))
        )
    if brand:
        conditions.append(Product.brand_name.ilike(f"%{brand}%"))
    if category_id:
        conditions.append(Product.category_id == category_id)
    if badge:
        conditions.append(Product.badge_level == badge.upper())
    if flagged_only:
        conditions.append(Product.avg_score < 70)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(Product.avg_score.desc().nulls_last())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": p.id,
                "product_name": p.product_name,
                "brand_name": p.brand_name,
                "barcode": p.barcode,
                "official_mrp": p.official_mrp,
                "net_quantity": p.net_quantity,
                "unit_price": p.unit_price_display,
                "country_of_origin": p.country_of_origin,
                "fssai_number": p.fssai_number,
                "avg_score": p.avg_score,
                "badge_level": p.badge_level or badge_for_score(p.avg_score),
                "total_inspections": p.total_inspections,
                "violation_count": p.violation_count,
                "last_inspected_at": p.last_inspected_at,
            }
            for p in rows
        ],
    }


@router.get("/{barcode}")
async def product_detail(barcode: str, db: DbSession, user: OptionalUser) -> dict:
    """Full compliance dossier for one commodity."""
    digits = "".join(ch for ch in barcode if ch.isdigit())
    product = (
        await db.execute(
            select(Product).where(Product.barcode == digits)
            .options(selectinload(Product.category))
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Barcode {digits} not found")

    sessions = (
        await db.execute(
            select(InspectionSession)
            .where(InspectionSession.barcode == digits)
            .options(selectinload(InspectionSession.violations))
            .order_by(InspectionSession.created_at.desc())
            .limit(25)
        )
    ).scalars().all()

    scans = (
        await db.execute(
            select(PriceHistoryScan).where(
                PriceHistoryScan.barcode == digits,
                PriceHistoryScan.scanned_at >= window_start(),
            )
        )
    ).scalars().all()

    stats = compute_price_stats([s.scanned_mrp for s in scans], digits)
    _st, findings, revision = analyse_barcode(
        digits,
        [
            {
                "scanned_mrp": s.scanned_mrp, "store_name": s.store_name,
                "latitude": s.latitude, "longitude": s.longitude,
                "scanned_at": s.scanned_at, "scanned_by_user_id": s.scanned_by_user_id,
            }
            for s in scans
        ],
        product_name=product.product_name,
        brand_name=product.brand_name,
    )

    storage = get_storage()

    def url(p):
        try:
            return storage.url_for(p) if p else None
        except Exception:
            return None

    return {
        "product": {
            "id": product.id,
            "product_name": product.product_name,
            "brand_name": product.brand_name,
            "barcode": product.barcode,
            "category": product.category.name if product.category else None,
            "category_slug": product.category.slug if product.category else None,
            "official_mrp": product.official_mrp,
            "net_quantity": product.net_quantity,
            "unit_price": product.unit_price_display,
            "country_of_origin": product.country_of_origin,
            "fssai_number": product.fssai_number,
            "avg_score": product.avg_score,
            "badge_level": product.badge_level or badge_for_score(product.avg_score),
            "total_inspections": product.total_inspections,
            "violation_count": product.violation_count,
            "last_inspected_at": product.last_inspected_at,
        },
        "price_intelligence": {
            "modal_mrp": stats.modal_mrp,
            "median_mrp": stats.median_mrp,
            "sample_count": stats.usable_count,
            "outliers_rejected": stats.outliers_rejected,
            "confidence": stats.confidence,
            "note": stats.note,
            "market_revision": revision,
            "gouging_findings": [f.to_dict() for f in findings[:10]],
        },
        "inspection_history": [
            {
                "session_id": s.session_id,
                "store_name": s.store_name,
                "created_at": s.created_at,
                "overall_score": s.overall_score,
                "compliance_status": s.compliance_status,
                "status": s.status,
                "violations": [
                    {
                        "rule_id": v.rule_id, "rule_name": v.rule_name,
                        "severity": v.severity, "status": v.status,
                        "legal_clause": v.legal_clause,
                        "evidence_text": v.evidence_text,
                        "crop_url": url(v.evidence_crop_path),
                    }
                    for v in s.violations if v.status == "FAIL"
                ],
            }
            for s in sessions
        ],
    }
