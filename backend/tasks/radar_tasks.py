"""Price-gouging radar tasks -- spec tasks/radar_tasks.py, WORKER 2.

Runs the radar over the whole scan corpus on a schedule, marks the anomalies,
and dispatches leads into the officer queue and warnings to consumers.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from core.task_runner import QUEUE_RADAR, task
from intelligence.price_gouging_radar import analyse_barcode, cluster_hotspots, window_start

logger = logging.getLogger("metrix.tasks.radar")


@task("radar.sweep_anomalies", queue=QUEUE_RADAR)
def sweep_anomalies(max_products: int = 400) -> dict:
    """Periodic radar sweep across every scanned commodity."""
    return asyncio.run(_sweep(max_products))


async def _sweep(max_products: int) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from models.consumer_alert import ConsumerAlert
    from models.enums import AlertType
    from models.price_history import PriceHistoryScan

    since = window_start()

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(PriceHistoryScan).where(PriceHistoryScan.scanned_at >= since)
            )
        ).scalars().all()

        grouped: dict[str, list[PriceHistoryScan]] = defaultdict(list)
        for r in rows:
            grouped[r.barcode].append(r)

        all_findings = []
        flagged = 0
        revisions = 0

        for barcode, scans in list(grouped.items())[:max_products]:
            payload = [
                {
                    "scanned_mrp": s.scanned_mrp, "store_name": s.store_name,
                    "latitude": s.latitude, "longitude": s.longitude,
                    "scanned_at": s.scanned_at, "scanned_by_user_id": s.scanned_by_user_id,
                }
                for s in scans
            ]
            stats, findings, revision = analyse_barcode(
                barcode, payload,
                product_name=scans[0].product_name,
                brand_name=scans[0].brand_name,
            )
            if revision:
                revisions += 1
                # A lawful market-wide revision must clear any stale flags,
                # otherwise last month's correct baseline keeps accusing
                # retailers who are now charging the new legitimate price.
                for s in scans:
                    if s.is_anomalous:
                        s.is_anomalous = False
                        s.anomaly_reason = f"Cleared: {revision}"
                continue

            offending_stores = {f.store_name for f in findings}
            for s in scans:
                should_flag = (
                    s.store_name in offending_stores
                    and stats.modal_mrp
                    and s.scanned_mrp > stats.modal_mrp * 1.05
                )
                if should_flag and not s.is_anomalous:
                    s.is_anomalous = True
                    s.modal_mrp_at_scan = stats.modal_mrp
                    s.overcharge_pct = round(
                        (s.scanned_mrp - stats.modal_mrp) / stats.modal_mrp * 100, 2
                    )
                    s.anomaly_reason = (
                        f"Printed MRP Rs.{s.scanned_mrp:.2f} exceeds the modal MRP "
                        f"Rs.{stats.modal_mrp:.2f} by {s.overcharge_pct:.1f}%"
                    )
                    flagged += 1

            all_findings.extend(findings)

        # Warn consumers who scanned an affected product.
        alerts_created = 0
        priority = [f for f in all_findings if f.severity == "PRIORITY"]
        for finding in priority[:50]:
            scanners = {
                s.scanned_by_user_id
                for s in grouped.get(finding.barcode, [])
                if s.scanned_by_user_id
            }
            for uid in list(scanners)[:200]:
                exists = (
                    await db.execute(
                        select(ConsumerAlert).where(
                            ConsumerAlert.user_id == uid,
                            ConsumerAlert.barcode == finding.barcode,
                            ConsumerAlert.alert_type == AlertType.PRICE_SURGE,
                            ConsumerAlert.is_read.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                db.add(ConsumerAlert(
                    user_id=uid,
                    barcode=finding.barcode,
                    alert_type=AlertType.PRICE_SURGE,
                    severity="WARNING",
                    title="Overcharging detected near you",
                    message=(
                        f"{finding.product_name or 'A product you scanned'} is being "
                        f"sold at Rs.{finding.observed_mrp:.2f} at "
                        f"{finding.store_name}, against a standard MRP of "
                        f"Rs.{finding.modal_mrp:.2f}."
                    ),
                    action_url=f"/consumer/scan?barcode={finding.barcode}",
                ))
                alerts_created += 1

        await db.commit()

    hotspots = cluster_hotspots(all_findings)

    # Push to any dashboard watching.
    try:
        from core.websocket_manager import manager

        await manager.publish_topic("radar_alerts", {
            "event": "sweep_complete",
            "findings": len(all_findings),
            "priority": len(priority),
            "hotspots": len(hotspots),
        })
    except Exception as exc:
        logger.debug("Radar broadcast skipped: %s", exc)

    logger.info(
        "Radar sweep: %d scans, %d products, %d findings (%d priority), "
        "%d hotspots, %d newly flagged, %d market revisions detected",
        len(rows), min(len(grouped), max_products), len(all_findings),
        len(priority), len(hotspots), flagged, revisions,
    )

    return {
        "scans_analysed": len(rows),
        "products_analysed": min(len(grouped), max_products),
        "findings": len(all_findings),
        "priority_findings": len(priority),
        "hotspots": len(hotspots),
        "newly_flagged_scans": flagged,
        "market_revisions_detected": revisions,
        "consumer_alerts_created": alerts_created,
        "top_hotspots": [h.to_dict() for h in hotspots[:5]],
    }
