"""Category leaderboards and product catalogue -- spec routes/categories.py + products.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.deps import CurrentUser, DbSession, OptionalUser
from intelligence.festival_calendar import seasonal_multiplier
from models.category import Category
from models.enums import badge_for_score
from models.inspection_session import InspectionSession
from models.product import Product
from models.violation import Violation
from rules.registry import pipeline_for

router = APIRouter(prefix="/categories", tags=["Catalogue"])


@router.get("")
async def list_categories(db: DbSession, user: OptionalUser, sector: str | None = None) -> dict:
    """Category leaderboard, ranked by average compliance."""
    stmt = select(Category)
    if sector:
        stmt = stmt.where(Category.sector == sector)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for c in rows:
        ctx = seasonal_multiplier(c.slug)
        items.append({
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "sector": c.sector,
            "icon": c.icon,
            "total_inspections": c.total_inspections,
            "avg_compliance_score": c.avg_compliance_score,
            "badge": badge_for_score(c.avg_compliance_score),
            "rules_applied": len(pipeline_for(c.slug, c.rule_pipeline)),
            "seasonal_multiplier": ctx.multiplier,
            "seasonal_reason": ctx.reasons[0] if ctx.reasons else None,
        })

    items.sort(key=lambda x: -(x["avg_compliance_score"] or 0))
    for i, item in enumerate(items):
        item["rank"] = i + 1

    sectors: dict[str, list] = {}
    for item in items:
        sectors.setdefault(item["sector"] or "Other", []).append(item["avg_compliance_score"] or 0)

    return {
        "categories": items,
        "sectors": [
            {
                "sector": k,
                "categories": len(v),
                "avg_compliance_score": round(sum(v) / len(v), 1) if v else None,
            }
            for k, v in sorted(sectors.items(), key=lambda kv: -sum(kv[1]) / max(len(kv[1]), 1))
        ],
    }


@router.get("/{slug}")
async def category_detail(slug: str, db: DbSession, user: OptionalUser) -> dict:
    cat = (
        await db.execute(select(Category).where(Category.slug == slug))
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Category '{slug}' not found")

    products = (
        await db.execute(
            select(Product).where(Product.category_id == cat.id)
            .order_by(Product.avg_score.desc().nulls_last())
        )
    ).scalars().all()

    since = datetime.now(timezone.utc) - timedelta(days=180)
    sessions = (
        await db.execute(
            select(InspectionSession)
            .where(
                InspectionSession.category_id == cat.id,
                InspectionSession.created_at >= since,
            )
            .options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()

    fails: dict[str, int] = {}
    for s in sessions:
        for v in s.violations:
            if v.status == "FAIL":
                key = v.rule_name or v.rule_id
                fails[key] = fails.get(key, 0) + 1

    ctx = seasonal_multiplier(cat.slug)
    return {
        "id": cat.id,
        "slug": cat.slug,
        "name": cat.name,
        "sector": cat.sector,
        "icon": cat.icon,
        "total_inspections": cat.total_inspections,
        "avg_compliance_score": cat.avg_compliance_score,
        "badge": badge_for_score(cat.avg_compliance_score),
        "rule_pipeline": pipeline_for(cat.slug, cat.rule_pipeline),
        "seasonal": {
            "multiplier": ctx.multiplier,
            "active_festivals": ctx.active,
            "reasons": ctx.reasons,
        },
        "product_count": len(products),
        "top_products": [
            {
                "id": p.id, "product_name": p.product_name, "brand_name": p.brand_name,
                "barcode": p.barcode, "avg_score": p.avg_score, "badge_level": p.badge_level,
            }
            for p in products[:10]
        ],
        "flagged_products": [
            {
                "id": p.id, "product_name": p.product_name, "brand_name": p.brand_name,
                "barcode": p.barcode, "avg_score": p.avg_score, "badge_level": p.badge_level,
                "violation_count": p.violation_count,
            }
            for p in products if (p.avg_score or 100) < 70
        ][:10],
        "common_findings": [
            {"finding": k, "count": v}
            for k, v in sorted(fails.items(), key=lambda kv: -kv[1])[:8]
        ],
        "recent_inspections": len(sessions),
    }
