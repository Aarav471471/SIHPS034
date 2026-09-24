"""Inter-agency graph sync -- spec tasks/agency_tasks.py, WORKER 4."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from core.task_runner import QUEUE_AGENCY, task
from intelligence.agency_graph import AgencyNode, evaluate_node

logger = logging.getLogger("metrix.tasks.agency")


@task("agency.sync_graph", queue=QUEUE_AGENCY)
def sync_graph() -> dict:
    """Recompute every brand's cross-agency risk index and referrals."""
    return asyncio.run(_sync())


async def _sync() -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from models.cross_agency import CrossAgencyLink
    from models.inspection_session import InspectionSession
    from models.product import Product

    async with AsyncSessionLocal() as db:
        links = (await db.execute(select(CrossAgencyLink))).scalars().all()
        products = (await db.execute(select(Product))).scalars().all()
        sessions = (
            await db.execute(
                select(InspectionSession).options(
                    selectinload(InspectionSession.violations)
                )
            )
        ).scalars().all()

        by_brand: dict[str, list] = defaultdict(list)
        for p in products:
            by_brand[p.brand_name].append(p)

        violations: dict[str, int] = defaultdict(int)
        criticals: dict[str, int] = defaultdict(int)
        penalties: dict[str, float] = defaultdict(float)
        for s in sessions:
            if not s.brand_name:
                continue
            fails = [v for v in s.violations if v.status == "FAIL"]
            violations[s.brand_name] += len(fails)
            criticals[s.brand_name] += len(
                [v for v in fails if v.severity == "CRITICAL"]
            )
            penalties[s.brand_name] += s.estimated_penalty or 0.0

        escalations = 0
        high_risk = 0

        for link in links:
            members = by_brand.get(link.brand_name, [])
            scores = [p.avg_score for p in members if p.avg_score is not None]

            node = evaluate_node(AgencyNode(
                brand_name=link.brand_name,
                legal_entity_name=link.legal_entity_name,
                fssai_number=link.fssai_number,
                fssai_valid=link.fssai_valid,
                fssai_expiry=link.fssai_expiry.date() if link.fssai_expiry else None,
                bis_reg_number=link.bis_reg_number,
                bis_valid=link.bis_valid,
                gstin=link.gstin,
                gstin_active=link.gstin_active,
                lm_violation_count=violations.get(link.brand_name, 0),
                lm_critical_count=criticals.get(link.brand_name, 0),
                products_flagged=len([p for p in members if (p.avg_score or 100) < 70]),
                total_products=len(members),
                avg_compliance_score=(
                    round(sum(scores) / len(scores), 1) if scores else None
                ),
                total_penalty_exposure=penalties.get(link.brand_name, 0.0),
            ))

            link.risk_index = node.risk_index
            link.lm_violation_count = violations.get(link.brand_name, 0)
            link.escalation_notes = (
                "; ".join(r["reason"] for r in node.referrals) or None
            )
            link.last_synced_at = datetime.now(timezone.utc)

            escalations += len(node.referrals)
            if node.risk_index >= 5.0:
                high_risk += 1

        await db.commit()

    logger.info(
        "Agency graph synced: %d entities, %d high-risk, %d referrals",
        len(links), high_risk, escalations,
    )
    return {
        "entities": len(links),
        "high_risk_entities": high_risk,
        "referrals_raised": escalations,
    }
