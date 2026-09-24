"""E-commerce crawler tasks -- spec tasks/ecom_tasks.py, WORKER 3."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from core.task_runner import QUEUE_ECOM, task
from intelligence.ecom_crosschecker import SeededAdapter, compare

logger = logging.getLogger("metrix.tasks.ecom")


@task("ecom.sweep_listings", queue=QUEUE_ECOM)
def sweep_listings(barcode: str | None = None, limit: int = 300) -> dict:
    """Re-run the cross-check over stored listings and persist the verdicts."""
    return asyncio.run(_sweep(barcode, limit))


async def _sweep(barcode: str | None, limit: int) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from models.ecom_listing import EcomListingCrosscheck
    from models.product import Product

    async with AsyncSessionLocal() as db:
        stmt = select(EcomListingCrosscheck)
        if barcode:
            stmt = stmt.where(EcomListingCrosscheck.barcode == barcode)
        rows = (await db.execute(stmt.limit(limit))).scalars().all()

        products = (await db.execute(select(Product))).scalars().all()
        by_code = {p.barcode: p for p in products if p.barcode}

        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r.barcode or "", []).append(r)

        checked = 0
        non_compliant = 0

        for code, items in grouped.items():
            product = by_code.get(code)
            if product is None:
                continue

            payload = [
                {
                    "barcode": r.barcode, "platform_name": r.platform_name,
                    "listing_url": r.listing_url, "listing_title": r.listing_title,
                    "scraped_mrp": r.scraped_mrp, "online_net_qty": r.online_net_qty,
                    "country_of_origin_found": r.country_of_origin_found,
                    "manufacturer_found": r.manufacturer_found,
                    "customer_care_found": r.customer_care_found,
                }
                for r in items
            ]
            result = compare(
                code, SeededAdapter(payload).fetch(code),
                physical_mrp=product.official_mrp,
                physical_net_qty=product.net_quantity,
                physical_origin=product.country_of_origin,
                product_name=product.product_name,
            )

            by_platform: dict[str, list] = {}
            for f in result.findings:
                by_platform.setdefault(f.platform, []).append(f)

            for r in items:
                findings = by_platform.get(r.platform_name, [])
                r.physical_pack_mrp = product.official_mrp
                r.physical_net_qty = product.net_quantity
                r.is_compliant = not findings
                r.mrp_discrepancy = any("MRP" in f.issue for f in findings)
                r.net_qty_discrepancy = any(
                    "net quantity" in f.issue.lower() for f in findings
                )
                r.violation_notes = " | ".join(f.issue for f in findings) or None
                r.last_checked_at = datetime.now(timezone.utc)
                checked += 1
                if findings:
                    non_compliant += 1

        await db.commit()

    logger.info(
        "E-com sweep: %d listings checked, %d non-compliant", checked, non_compliant
    )
    return {
        "listings_checked": checked,
        "non_compliant": non_compliant,
        "products": len(grouped),
        "scope": barcode or "all",
    }
