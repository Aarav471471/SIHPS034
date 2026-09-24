"""Policymaker & inter-agency APIs -- spec routes/policy.py, section 6.D.

Macro compliance trends, the most-violated-clause ranking, the unified
regulatory graph, and post-amendment impact analysis.

Every statistic here reports its sample size, and refuses to claim a trend it
cannot support. A ministry dashboard that overstates confidence is worse than
one that says "not enough data yet" -- policy gets made from these numbers.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.deps import CurrentUser, DbSession
from intelligence.agency_graph import AgencyNode, build_graph, evaluate_node
from intelligence.festival_calendar import upcoming
from intelligence.policy_analytics import (
    amendment_impact,
    compute_category_trends,
    compute_clause_stats,
    geographic_summary,
    period_bounds,
)
from models.category import Category
from models.cross_agency import CrossAgencyLink
from models.enums import ComplianceStatus, SessionStatus
from models.inspection_session import InspectionSession
from models.product import Product
from models.violation import Violation
from rules.registry import RULE_CLASSES, pipeline_for

logger = logging.getLogger("metrix.policy")
router = APIRouter(prefix="/policy", tags=["Policy"])


@router.get("/macro-trends")
async def macro_trends(
    db: DbSession,
    user: CurrentUser,
    days: int = Query(90, ge=7, le=730),
) -> dict:
    """National compliance picture over two comparable windows."""
    prev_start, cur_start, now = period_bounds(days)

    sessions = (
        await db.execute(
            select(InspectionSession)
            .where(InspectionSession.created_at >= prev_start)
            .options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()

    current = [s for s in sessions if s.created_at and s.created_at >= cur_start]
    previous = [s for s in sessions if s.created_at and s.created_at < cur_start]

    cats = (await db.execute(select(Category))).scalars().all()
    name_by_id = {c.id: c.name for c in cats}
    slug_by_id = {c.id: c.slug for c in cats}
    names = {c.slug: c.name for c in cats}

    def by_category(rows) -> dict[str, list[float]]:
        out: dict[str, list[float]] = defaultdict(list)
        for s in rows:
            if s.overall_score is None:
                continue
            slug = slug_by_id.get(s.category_id) or (s.product_category or "uncategorised")
            out[slug].append(float(s.overall_score))
        return out

    trends = compute_category_trends(by_category(current), by_category(previous), names)

    # --- clause statistics, with a real denominator ---
    cur_ids = {s.id for s in current}
    prev_ids = {s.id for s in previous}

    def clause_inputs(rows, ids):
        violations = []
        applicable: dict[str, int] = defaultdict(int)
        for s in rows:
            slug = slug_by_id.get(s.category_id)
            for key in pipeline_for(slug):
                cls = RULE_CLASSES.get(key)
                if cls:
                    applicable[cls.rule_id] += 1
            for v in s.violations:
                if v.status == "FAIL":
                    violations.append({
                        "rule_id": v.rule_id,
                        "rule_name": v.rule_name,
                        "legal_clause": v.legal_clause,
                        "severity": v.severity,
                        "penalty_amount": v.penalty_amount,
                    })
        return violations, applicable

    cur_v, cur_app = clause_inputs(current, cur_ids)
    prev_v, prev_app = clause_inputs(previous, prev_ids)

    prev_stats = compute_clause_stats(prev_v, prev_app)
    prev_rates = {s.rule_id: s.violation_rate for s in prev_stats}
    clause_stats = compute_clause_stats(cur_v, cur_app, prev_rates)

    scored = [s.overall_score for s in current if s.overall_score is not None]
    compliant = len([s for s in current if s.compliance_status == ComplianceStatus.COMPLIANT])

    return {
        "window": {
            "days": days,
            "current_from": cur_start.isoformat(),
            "previous_from": prev_start.isoformat(),
            "generated_at": now.isoformat(),
        },
        "headline": {
            "inspections_current": len(current),
            "inspections_previous": len(previous),
            "overall_compliance_rate": (
                round(compliant / len(current) * 100, 1) if current else None
            ),
            "avg_compliance_score": (
                round(sum(scored) / len(scored), 1) if scored else None
            ),
            "total_penalty_exposure": round(
                sum(s.estimated_penalty or 0 for s in current), 2
            ),
            "cases_escalated": len(
                [s for s in current if s.status == SessionStatus.PEER_REVIEW]
            ),
        },
        "most_violated_clauses": [s.to_dict() for s in clause_stats[:12]],
        "degrading_categories": [
            t.to_dict() for t in trends if t.direction == "degrading"
        ][:8],
        "improving_categories": [
            t.to_dict() for t in trends if t.direction == "improving"
        ][:8],
        "all_category_trends": [t.to_dict() for t in trends],
        "upcoming_enforcement_windows": upcoming(within_days=60)[:5],
        "methodology": (
            "Clause statistics are violation rates over inspections where the rule "
            "was applicable, not raw counts -- a raw count would simply rank rules "
            "by how often they are checked. Category trends are suppressed unless "
            "both comparison periods carry at least 8 inspections."
        ),
    }


@router.get("/agency-graph")
async def agency_graph(
    db: DbSession,
    user: CurrentUser,
    brand_name: str | None = Query(default=None),
) -> dict:
    """Unified compliance graph across LM, FSSAI, BIS and GST -- spec 3.I."""
    stmt = select(CrossAgencyLink)
    if brand_name:
        stmt = stmt.where(CrossAgencyLink.brand_name.ilike(f"%{brand_name}%"))
    links = (await db.execute(stmt)).scalars().all()

    products = (await db.execute(select(Product))).scalars().all()
    by_brand: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by_brand[p.brand_name].append(p)

    sessions = (
        await db.execute(
            select(InspectionSession).options(selectinload(InspectionSession.violations))
        )
    ).scalars().all()
    penalties: dict[str, float] = defaultdict(float)
    criticals: dict[str, int] = defaultdict(int)
    for s in sessions:
        if not s.brand_name:
            continue
        penalties[s.brand_name] += s.estimated_penalty or 0.0
        criticals[s.brand_name] += len(
            [v for v in s.violations if v.severity == "CRITICAL" and v.status == "FAIL"]
        )

    nodes = []
    for link in links:
        members = by_brand.get(link.brand_name, [])
        scores = [p.avg_score for p in members if p.avg_score is not None]
        nodes.append(AgencyNode(
            brand_name=link.brand_name,
            legal_entity_name=link.legal_entity_name,
            fssai_number=link.fssai_number,
            fssai_valid=link.fssai_valid,
            fssai_expiry=link.fssai_expiry.date() if link.fssai_expiry else None,
            bis_reg_number=link.bis_reg_number,
            bis_valid=link.bis_valid,
            gstin=link.gstin,
            gstin_active=link.gstin_active,
            lm_violation_count=link.lm_violation_count,
            lm_critical_count=criticals.get(link.brand_name, 0),
            products_flagged=len([p for p in members if (p.avg_score or 100) < 70]),
            total_products=len(members),
            avg_compliance_score=round(sum(scores) / len(scores), 1) if scores else None,
            total_penalty_exposure=penalties.get(link.brand_name, 0.0),
        ))

    return build_graph(nodes)


@router.get("/geographic")
async def geographic_compliance(
    db: DbSession,
    user: CurrentUser,
    days: int = Query(180, ge=7, le=730),
    grid_deg: float = Query(0.05, gt=0.005, le=1.0),
) -> dict:
    """Compliance aggregated onto a grid, for choropleth mapping."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(InspectionSession).where(
                InspectionSession.created_at >= since,
                InspectionSession.latitude.isnot(None),
            )
        )
    ).scalars().all()

    cells = geographic_summary(
        [
            {
                "latitude": s.latitude,
                "longitude": s.longitude,
                "overall_score": s.overall_score,
                "compliance_status": s.compliance_status,
            }
            for s in rows
        ],
        grid_deg=grid_deg,
    )

    return {
        "window_days": days,
        "grid_size_deg": grid_deg,
        "cells": cells,
        "inspections_mapped": len(rows),
        "privacy_note": (
            "Results are aggregated to grid cells rather than exact coordinates, so "
            "individual retailers are not identifiable from this dashboard before "
            "adjudication."
        ),
    }


@router.get("/amendment-impact")
async def measure_amendment(
    db: DbSession,
    user: CurrentUser,
    effective_date: str = Query(..., description="ISO date the change took effect"),
    amendment_name: str = Query("Rule amendment"),
    window_days: int = Query(120, ge=14, le=730),
    category_slug: str | None = None,
) -> dict:
    """Did a rule change measurably improve compliance? -- the policy feedback loop."""
    try:
        effective = datetime.fromisoformat(effective_date).replace(tzinfo=timezone.utc)
    except ValueError:
        return {"error": f"'{effective_date}' is not a valid ISO date"}

    before_from = effective - timedelta(days=window_days)
    after_to = effective + timedelta(days=window_days)

    stmt = select(InspectionSession).where(
        InspectionSession.created_at >= before_from,
        InspectionSession.created_at <= after_to,
        InspectionSession.overall_score.isnot(None),
    )
    if category_slug:
        cat = (
            await db.execute(select(Category).where(Category.slug == category_slug))
        ).scalar_one_or_none()
        if cat:
            stmt = stmt.where(InspectionSession.category_id == cat.id)

    rows = (await db.execute(stmt)).scalars().all()
    before = [float(s.overall_score) for s in rows if s.created_at < effective]
    after = [float(s.overall_score) for s in rows if s.created_at >= effective]

    result = amendment_impact(before, after, amendment_name)
    result["effective_date"] = effective.date().isoformat()
    result["window_days"] = window_days
    result["category"] = category_slug
    return result


@router.get("/rules")
async def rule_catalogue(user: CurrentUser) -> dict:
    """The rule book the engine enforces, for transparency."""
    from rules.registry import describe_rules

    return {
        "rules": describe_rules(),
        "count": len(RULE_CLASSES),
        "note": (
            "Every finding cites one of these rules and the clause behind it. "
            "The rule set applied to a commodity depends on its category."
        ),
    }
