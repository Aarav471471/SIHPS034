"""E-commerce cross-verification -- spec routes/ecom.py, section 6.D."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from core.deps import CurrentUser, DbSession, OfficerUser
from intelligence.ecom_crosschecker import (
    SeededAdapter,
    compare,
    platform_scorecard,
)
from models.ecom_listing import EcomListingCrosscheck
from models.product import Product

logger = logging.getLogger("metrix.ecom")
router = APIRouter(prefix="/ecom", tags=["E-Commerce"])


async def _rows_for(db, barcode: str | None) -> list[dict]:
    stmt = select(EcomListingCrosscheck)
    if barcode:
        stmt = stmt.where(EcomListingCrosscheck.barcode == barcode)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "barcode": r.barcode,
            "platform_name": r.platform_name,
            "listing_url": r.listing_url,
            "listing_title": r.listing_title,
            "scraped_mrp": r.scraped_mrp,
            "online_net_qty": r.online_net_qty,
            "country_of_origin_found": r.country_of_origin_found,
            "manufacturer_found": r.manufacturer_found,
            "customer_care_found": r.customer_care_found,
        }
        for r in rows
    ]


@router.get("/cross-check")
async def cross_check(
    db: DbSession,
    user: CurrentUser,
    barcode: str = Query(min_length=6, max_length=20),
) -> dict:
    """Compare a physical pack against its e-commerce listings -- spec 3.H."""
    digits = "".join(ch for ch in barcode if ch.isdigit())

    product = (
        await db.execute(select(Product).where(Product.barcode == digits))
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Barcode {digits} is not in the compliance catalogue, so there is no "
            "verified physical pack to compare listings against.",
        )

    listings = SeededAdapter(await _rows_for(db, digits)).fetch(digits)
    result = compare(
        digits,
        listings,
        physical_mrp=product.official_mrp,
        physical_net_qty=product.net_quantity,
        physical_origin=product.country_of_origin,
        product_name=product.product_name,
    )

    payload = result.to_dict()
    payload["data_source"] = {
        "adapter": "seeded",
        "note": (
            "Listings are served from the platform's curated dataset. Live fetching "
            "requires a data-sharing agreement with each marketplace; the comparison "
            "logic is identical either way."
        ),
    }
    return payload


@router.get("/platform-scorecard")
async def scorecard(db: DbSession, user: CurrentUser, limit: int = Query(200, ge=1, le=2000)) -> dict:
    """Platform-level compliance ranking -- what justifies a notice to an operator."""
    rows = await _rows_for(db, None)

    by_barcode: dict[str, list[dict]] = {}
    for r in rows[:limit]:
        by_barcode.setdefault(r["barcode"] or "", []).append(r)

    products = (await db.execute(select(Product))).scalars().all()
    by_code = {p.barcode: p for p in products if p.barcode}

    results = []
    for code, items in by_barcode.items():
        product = by_code.get(code)
        if product is None:
            continue
        results.append(compare(
            code,
            SeededAdapter(items).fetch(code),
            physical_mrp=product.official_mrp,
            physical_net_qty=product.net_quantity,
            physical_origin=product.country_of_origin,
            product_name=product.product_name,
        ))

    cards = platform_scorecard(results)
    total_listings = sum(c["listings_checked"] for c in cards)
    total_bad = sum(c["non_compliant_listings"] for c in cards)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products_compared": len(results),
        "listings_checked": total_listings,
        "non_compliant_listings": total_bad,
        "overall_non_compliance_rate": (
            round(total_bad / total_listings * 100, 1) if total_listings else 0.0
        ),
        "platforms": cards,
        "legal_basis": (
            "Rule 6(10) of the Legal Metrology (Packaged Commodities) Rules, 2011 "
            "requires every mandatory declaration to appear on an e-commerce listing."
        ),
    }


@router.get("/listings")
async def listings(
    db: DbSession,
    user: CurrentUser,
    platform: str | None = None,
    non_compliant_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Raw stored cross-check records."""
    stmt = select(EcomListingCrosscheck)
    if platform:
        stmt = stmt.where(EcomListingCrosscheck.platform_name == platform)
    if non_compliant_only:
        stmt = stmt.where(EcomListingCrosscheck.is_compliant.is_(False))

    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(EcomListingCrosscheck.last_checked_at.desc()).limit(limit)
        )
    ).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "barcode": r.barcode,
                "platform": r.platform_name,
                "listing_url": r.listing_url,
                "listing_title": r.listing_title,
                "listed_mrp": r.scraped_mrp,
                "physical_mrp": r.physical_pack_mrp,
                "mrp_discrepancy": r.mrp_discrepancy,
                "country_of_origin_found": r.country_of_origin_found,
                "online_net_qty": r.online_net_qty,
                "physical_net_qty": r.physical_net_qty,
                "is_compliant": r.is_compliant,
                "violation_notes": r.violation_notes,
                "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
            }
            for r in rows
        ],
    }


@router.post("/recheck")
async def queue_recheck(user: OfficerUser, barcode: str | None = None) -> dict:
    """Queue an e-commerce re-crawl."""
    from core.task_runner import dispatch

    handle = dispatch("ecom.sweep_listings", barcode)
    return {
        "task_id": handle.task_id,
        "queue": handle.queue,
        "status": "queued",
        "scope": barcode or "all catalogued products",
    }
