"""Consumer notification tasks -- spec notification_dispatch queue.

Automated recall and expiry alerts for consumers who scanned an affected
product. This is the half of the consumer pillar that works when nobody is
looking at the app.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from core.task_runner import QUEUE_NOTIFY, task

logger = logging.getLogger("metrix.tasks.notify")

# How far ahead of a scanned product's expiry to warn the consumer.
EXPIRY_WARNING_DAYS = 21


@task("notify.scan_expiring_products", queue=QUEUE_NOTIFY)
def scan_expiring_products() -> dict:
    """Alert consumers whose scanned products are near or past their date."""
    return asyncio.run(_scan_expiring())


async def _scan_expiring() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from models.consumer_alert import ConsumerAlert
    from models.enums import AlertType
    from models.extracted_field import ExtractedField
    from models.inspection_session import InspectionSession
    from models.price_history import PriceHistoryScan
    from rules.base import month_end, parse_date

    now = datetime.now(timezone.utc)
    horizon = now.date() + timedelta(days=EXPIRY_WARNING_DAYS)
    created = 0

    async with AsyncSessionLocal() as db:
        # Expiry dates the pipeline actually read off real packs.
        rows = (
            await db.execute(
                select(ExtractedField, InspectionSession)
                .join(
                    InspectionSession,
                    ExtractedField.session_id == InspectionSession.id,
                )
                .where(
                    ExtractedField.field_name == "expiry_date",
                    ExtractedField.detected_value.isnot(None),
                    InspectionSession.barcode.isnot(None),
                )
            )
        ).all()

        at_risk: dict[str, tuple[str, int]] = {}
        for field, session in rows:
            parsed = parse_date(field.detected_value)
            if not parsed:
                continue
            when, precision = parsed
            # Month-precision dates are valid to the last day of the month.
            effective = month_end(when) if precision == "month" else when
            if effective > horizon:
                continue
            days = (effective - now.date()).days
            code = session.barcode
            if code not in at_risk or days < at_risk[code][1]:
                at_risk[code] = (session.product_name or "A product", days)

        if not at_risk:
            return {"alerts_created": 0, "products_at_risk": 0}

        scans = (
            await db.execute(
                select(PriceHistoryScan).where(
                    PriceHistoryScan.barcode.in_(list(at_risk)),
                    PriceHistoryScan.scanned_by_user_id.isnot(None),
                )
            )
        ).scalars().all()

        seen: set[tuple[int, str]] = set()
        for scan in scans:
            key = (scan.scanned_by_user_id, scan.barcode)
            if key in seen:
                continue
            seen.add(key)

            name, days = at_risk[scan.barcode]
            expired = days < 0

            # Never alert the same person twice about the same product.
            exists = (
                await db.execute(
                    select(ConsumerAlert).where(
                        ConsumerAlert.user_id == scan.scanned_by_user_id,
                        ConsumerAlert.barcode == scan.barcode,
                        ConsumerAlert.alert_type == AlertType.EXPIRED_BATCH_WARNING,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                continue

            db.add(ConsumerAlert(
                user_id=scan.scanned_by_user_id,
                barcode=scan.barcode,
                alert_type=AlertType.EXPIRED_BATCH_WARNING,
                severity="CRITICAL" if expired else "WARNING",
                title="Expired stock reported" if expired else "Product nearing expiry",
                message=(
                    f"{name}, which you scanned recently, "
                    + (
                        f"passed its best-before date {abs(days)} days ago."
                        if expired
                        else f"expires in {days} days."
                    )
                    + " Check the batch code on any pack you still hold."
                ),
                action_url=f"/consumer/scan?barcode={scan.barcode}",
            ))
            created += 1

        await db.commit()

    logger.info(
        "Expiry sweep: %d alerts raised across %d at-risk products",
        created, len(at_risk),
    )
    return {"alerts_created": created, "products_at_risk": len(at_risk)}


@task("notify.product_recall", queue=QUEUE_NOTIFY)
def product_recall(barcode: str, reason: str) -> dict:
    """Broadcast a recall to everyone who scanned the affected product."""
    return asyncio.run(_recall(barcode, reason))


async def _recall(barcode: str, reason: str) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from models.consumer_alert import ConsumerAlert
    from models.enums import AlertType
    from models.price_history import PriceHistoryScan
    from models.product import Product

    async with AsyncSessionLocal() as db:
        product = (
            await db.execute(select(Product).where(Product.barcode == barcode))
        ).scalar_one_or_none()

        scans = (
            await db.execute(
                select(PriceHistoryScan).where(
                    PriceHistoryScan.barcode == barcode,
                    PriceHistoryScan.scanned_by_user_id.isnot(None),
                )
            )
        ).scalars().all()

        notified: set[int] = set()
        for scan in scans:
            if scan.scanned_by_user_id in notified:
                continue
            notified.add(scan.scanned_by_user_id)
            db.add(ConsumerAlert(
                user_id=scan.scanned_by_user_id,
                barcode=barcode,
                alert_type=AlertType.PRODUCT_RECALL,
                severity="CRITICAL",
                title="Product recall notice",
                message=(
                    f"{product.product_name if product else 'A product you scanned'} "
                    f"has been recalled. {reason}"
                ),
                action_url=f"/consumer/scan?barcode={barcode}",
            ))
        await db.commit()

    logger.info("Recall for %s notified %d consumers", barcode, len(notified))
    return {"barcode": barcode, "consumers_notified": len(notified)}
