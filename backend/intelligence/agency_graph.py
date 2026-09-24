"""Unified regulatory graph -- spec intelligence/agency_graph.py, section 3.I.

Correlates a Legal Metrology offender with its FSSAI licence, BIS registration
and GSTIN, so repeat packaging fraud triggers the right sister authority instead
of dying inside one department.

The genuinely useful output is not the links themselves but the *escalation
recommendation*: a brand with mounting LM violations AND a lapsed FSSAI licence
is a different problem from one with mounting violations and clean paperwork.
The first is a food-safety referral; the second is a metrology prosecution.

Risk propagates along the graph. A brand's risk raises the risk of the retailers
that stock it, which feeds the patrol routing engine -- that is how a
manufacturing-side problem becomes a field-inspection priority.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

logger = logging.getLogger("metrix.agency")

# Which authority owns which failure.
AUTHORITIES = {
    "LM": "Legal Metrology Department, Ministry of Consumer Affairs",
    "FSSAI": "Food Safety and Standards Authority of India",
    "BIS": "Bureau of Indian Standards",
    "GSTN": "Goods and Services Tax Network",
    "MCA": "Ministry of Corporate Affairs",
}


@dataclass
class AgencyNode:
    """One regulated entity as seen across all registries."""

    brand_name: str
    legal_entity_name: str | None = None

    fssai_number: str | None = None
    fssai_valid: bool = True
    fssai_expiry: date | None = None

    bis_reg_number: str | None = None
    bis_valid: bool = True

    gstin: str | None = None
    gstin_active: bool = True

    lm_violation_count: int = 0
    lm_critical_count: int = 0
    products_flagged: int = 0
    total_products: int = 0
    avg_compliance_score: float | None = None
    total_penalty_exposure: float = 0.0

    risk_index: float = 0.0
    flags: list[str] = field(default_factory=list)
    referrals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brand_name": self.brand_name,
            "legal_entity_name": self.legal_entity_name,
            "identifiers": {
                "fssai": {
                    "number": self.fssai_number,
                    "valid": self.fssai_valid,
                    "expiry": self.fssai_expiry.isoformat() if self.fssai_expiry else None,
                },
                "bis": {"number": self.bis_reg_number, "valid": self.bis_valid},
                "gstin": {"number": self.gstin, "active": self.gstin_active},
            },
            "legal_metrology": {
                "violation_count": self.lm_violation_count,
                "critical_count": self.lm_critical_count,
                "products_flagged": self.products_flagged,
                "total_products": self.total_products,
                "avg_compliance_score": self.avg_compliance_score,
                "penalty_exposure": round(self.total_penalty_exposure, 2),
            },
            "risk_index": round(self.risk_index, 2),
            "flags": self.flags,
            "referrals": self.referrals,
        }


def _fssai_expired(node: AgencyNode, on: date) -> bool:
    return bool(node.fssai_expiry and node.fssai_expiry < on)


def evaluate_node(node: AgencyNode, on: date | None = None) -> AgencyNode:
    """Score an entity and decide which authorities should be told what.

    Risk index is on a 0-10 scale so it can multiply store risk directly in the
    routing engine.
    """
    day = on or date.today()
    flags: list[str] = []
    referrals: list[dict] = []

    # --- Legal Metrology exposure ---
    compliance_gap = (
        (100.0 - node.avg_compliance_score) / 10.0 if node.avg_compliance_score is not None else 0.0
    )
    violation_pressure = min(4.0, node.lm_violation_count * 0.25)
    critical_pressure = min(3.0, node.lm_critical_count * 0.9)

    risk = compliance_gap * 0.4 + violation_pressure + critical_pressure

    if node.lm_critical_count:
        flags.append(
            f"{node.lm_critical_count} critical Legal Metrology violation"
            f"{'s' if node.lm_critical_count != 1 else ''} recorded"
        )
    if node.total_products and node.products_flagged:
        share = node.products_flagged / node.total_products
        if share >= 0.4:
            flags.append(
                f"{node.products_flagged} of {node.total_products} products in this "
                f"brand's range are flagged ({share * 100:.0f}%) -- indicates a "
                "systemic labelling process failure rather than isolated packs"
            )
            risk += 1.5

    # --- Cross-agency correlations ---
    # A lapsed food licence alongside packaging violations is materially more
    # serious than either alone: it suggests the entity is operating outside
    # regulatory oversight generally, not failing one specific check.
    if node.fssai_number and (not node.fssai_valid or _fssai_expired(node, day)):
        detail = (
            f"FSSAI licence {node.fssai_number} is "
            + ("expired" if _fssai_expired(node, day) else "recorded as invalid")
            + (f" (expiry {node.fssai_expiry:%d %b %Y})" if node.fssai_expiry else "")
        )
        flags.append(detail)
        risk += 2.0
        referrals.append({
            "authority": "FSSAI",
            "authority_name": AUTHORITIES["FSSAI"],
            "priority": "HIGH" if node.lm_violation_count else "MEDIUM",
            "reason": detail,
            "recommended_action": (
                "Refer for licence verification. Pre-packaged food is being sold "
                "under a licence that is not current."
            ),
            "supporting_evidence": (
                f"{node.lm_violation_count} Legal Metrology violations recorded "
                f"against this brand's packaging."
            ),
        })

    if node.bis_reg_number and not node.bis_valid:
        flags.append(f"BIS registration {node.bis_reg_number} is not valid")
        risk += 1.2
        referrals.append({
            "authority": "BIS",
            "authority_name": AUTHORITIES["BIS"],
            "priority": "MEDIUM",
            "reason": f"BIS registration {node.bis_reg_number} could not be validated",
            "recommended_action": (
                "Refer for standards-mark verification; the ISI mark may be "
                "displayed without a current registration."
            ),
            "supporting_evidence": f"Average compliance score {node.avg_compliance_score}",
        })

    if node.gstin and not node.gstin_active:
        detail = f"GSTIN {node.gstin} is inactive"
        flags.append(detail)
        risk += 1.8
        # An inactive GSTIN combined with active retail presence is the
        # classic shell-company signature.
        priority = "HIGH" if node.total_products >= 3 else "MEDIUM"
        referrals.append({
            "authority": "GSTN",
            "authority_name": AUTHORITIES["GSTN"],
            "priority": priority,
            "reason": detail,
            "recommended_action": (
                "Refer for tax-status verification. Goods bearing this brand are "
                "present in retail while its GST registration is inactive, which "
                "is consistent with a shell entity."
            ),
            "supporting_evidence": (
                f"{node.total_products} products from this brand observed in the field."
            ),
        })

    # Compounding: multiple lapsed registrations is qualitatively worse than one.
    lapsed = sum([
        bool(node.fssai_number and not node.fssai_valid),
        bool(node.bis_reg_number and not node.bis_valid),
        bool(node.gstin and not node.gstin_active),
    ])
    if lapsed >= 2:
        risk += 1.5
        flags.append(
            f"{lapsed} separate registrations are lapsed or invalid -- this entity "
            "appears to be operating outside regulatory oversight generally"
        )
        referrals.append({
            "authority": "MCA",
            "authority_name": AUTHORITIES["MCA"],
            "priority": "HIGH",
            "reason": f"{lapsed} concurrent registration failures across agencies",
            "recommended_action": (
                "Refer for corporate-status verification and consider coordinated "
                "multi-agency action."
            ),
            "supporting_evidence": "; ".join(flags[:3]),
        })

    if node.total_penalty_exposure > 200_000:
        flags.append(
            f"Aggregate penalty exposure Rs.{node.total_penalty_exposure:,.0f} "
            "across recorded violations"
        )
        risk += 0.8

    node.risk_index = round(max(0.0, min(10.0, risk)), 2)
    node.flags = flags or ["No adverse regulatory correlations found"]
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    node.referrals = sorted(referrals, key=lambda r: order.get(r["priority"], 3))
    return node


def propagate_to_retailers(
    brand_risks: dict[str, float], stocked_brands: list[str]
) -> tuple[float, list[str]]:
    """Convert the brands a retailer stocks into a risk contribution.

    The mean would let one severely flagged brand vanish among twenty clean
    ones, which is the wrong signal -- a shop stocking a suspended-licence brand
    is worth visiting regardless of what else is on its shelves. The maximum
    dominates, with a small contribution from breadth.
    """
    if not stocked_brands:
        return 0.0, []

    scored = [(b, brand_risks.get(b, 0.0)) for b in stocked_brands]
    scored = [(b, r) for b, r in scored if r > 0]
    if not scored:
        return 0.0, []

    scored.sort(key=lambda x: -x[1])
    worst_brand, worst = scored[0]
    breadth = min(2.0, len(scored) * 0.3)

    reasons = [
        f"Stocks {worst_brand}, which carries a regulatory risk index of {worst:.1f}"
    ]
    if len(scored) > 1:
        reasons.append(
            f"{len(scored)} stocked brands carry open regulatory flags"
        )

    return round(min(10.0, worst + breadth), 2), reasons


def build_graph(nodes: list[AgencyNode], on: date | None = None) -> dict:
    """Whole-graph view for the ministry dashboard."""
    evaluated = [evaluate_node(n, on) for n in nodes]
    evaluated.sort(key=lambda n: -n.risk_index)

    by_authority: dict[str, list[dict]] = {}
    for node in evaluated:
        for ref in node.referrals:
            by_authority.setdefault(ref["authority"], []).append({
                "brand_name": node.brand_name,
                "risk_index": node.risk_index,
                **ref,
            })

    high_risk = [n for n in evaluated if n.risk_index >= 5.0]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(evaluated),
        "high_risk_count": len(high_risk),
        "entities": [n.to_dict() for n in evaluated],
        "referrals_by_authority": {
            k: {
                "authority_name": AUTHORITIES.get(k, k),
                "count": len(v),
                "high_priority": len([r for r in v if r["priority"] == "HIGH"]),
                "items": v,
            }
            for k, v in sorted(by_authority.items(), key=lambda kv: -len(kv[1]))
        },
        "summary": {
            "entities_with_lapsed_fssai": len(
                [n for n in evaluated if n.fssai_number and not n.fssai_valid]
            ),
            "entities_with_invalid_bis": len(
                [n for n in evaluated if n.bis_reg_number and not n.bis_valid]
            ),
            "entities_with_inactive_gstin": len(
                [n for n in evaluated if n.gstin and not n.gstin_active]
            ),
            "total_referrals": sum(len(v) for v in by_authority.values()),
            "aggregate_penalty_exposure": round(
                sum(n.total_penalty_exposure for n in evaluated), 2
            ),
        },
    }
