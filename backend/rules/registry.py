"""Rule registry and evaluation engine -- spec rules/registry.py.

Assembles the applicable rules for a commodity, runs them, and returns findings
plus a compliance score.

Category-specific pipelines exist because applying every rule to every commodity
produces false findings, and a system that cries wolf gets ignored by the
officers it is meant to help: an FSSAI licence check on a packet of pencils, or
a best-before date on a bag of salt, would each be a wrong answer confidently
delivered.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from extraction.confidence import compliance_score
from models.enums import ComplianceStatus, ViolationStatus
from rules.base import BaseRule, RuleContext, RuleResult
from rules.rule_dates import ExpiredStockRule, ExpiryDateRule, ManufactureDateRule
from rules.rule_declarations import CountryOfOriginRule, CustomerCareRule
from rules.rule_font_height import FontHeightRule, LetterHeightRule
from rules.rule_fssai import FSSAILicenceRule
from rules.rule_manufacturer import ManufacturerAddressRule, ManufacturerNameRule
from rules.rule_mrp_format import MRPFormatRule
from rules.rule_multi_surface import MultiSurfaceRule
from rules.rule_net_quantity import NetQuantityRule
from rules.rule_unit_price import UnitPriceRule

logger = logging.getLogger("metrix.rules")

# Registry key -> rule class
RULE_CLASSES: dict[str, type[BaseRule]] = {
    "mrp_format": MRPFormatRule,
    "net_quantity": NetQuantityRule,
    "unit_price": UnitPriceRule,
    "mfg_date": ManufactureDateRule,
    "expiry_date": ExpiryDateRule,
    "expired_stock": ExpiredStockRule,
    "manufacturer": ManufacturerNameRule,
    "pincode": ManufacturerAddressRule,
    "country_of_origin": CountryOfOriginRule,
    "customer_care": CustomerCareRule,
    "fssai": FSSAILicenceRule,
    "font_height": FontHeightRule,
    "letter_height": LetterHeightRule,
    "multi_surface": MultiSurfaceRule,
}

# Applies to every pre-packaged commodity regardless of type.
UNIVERSAL_PIPELINE = (
    "mrp_format",
    "net_quantity",
    "unit_price",
    "manufacturer",
    "pincode",
    "country_of_origin",
    "customer_care",
    "multi_surface",
    "font_height",
    "letter_height",
)

# Additional checks for commodities with a shelf life.
PERISHABLE_PIPELINE = ("mfg_date", "expiry_date", "expired_stock")

# Food and nutraceutical commodities also require an FSSAI licence.
FOOD_PIPELINE = PERISHABLE_PIPELINE + ("fssai",)

FOOD_CATEGORIES = {
    "biscuits-cookies", "edible-oils", "dairy-products", "ghee-butter",
    "sweets-mithai", "spices-masala", "atta-flour", "rice-grains", "pulses-dal",
    "tea-coffee", "snacks-namkeen", "chocolates-confectionery", "beverages-juices",
    "instant-noodles", "baby-food", "breakfast-cereals", "sauces-condiments",
    "dry-fruits-nuts", "salt-sugar", "frozen-foods", "pharma-otc",
}

# Non-food commodities that still carry a meaningful shelf life.
PERISHABLE_NON_FOOD = {"cosmetics", "personal-care", "hair-care", "oral-care"}


@dataclass
class EvaluationResult:
    results: list[RuleResult] = field(default_factory=list)
    score: int = 0
    compliance_status: str = ComplianceStatus.COMPLIANT
    total_penalty: float = 0.0
    has_contested_unit_price: bool = False
    pipeline: list[str] = field(default_factory=list)

    @property
    def violations(self) -> list[RuleResult]:
        return [r for r in self.results if r.is_violation]

    @property
    def failures(self) -> list[RuleResult]:
        return [r for r in self.results if r.status == ViolationStatus.FAIL]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if r.status == ViolationStatus.WARNING]

    @property
    def passes(self) -> list[RuleResult]:
        return [r for r in self.results if r.status == ViolationStatus.PASS]

    def summary(self) -> dict:
        return {
            "score": self.score,
            "compliance_status": self.compliance_status,
            "rules_evaluated": len(self.results),
            "passed": len(self.passes),
            "failed": len(self.failures),
            "warnings": len(self.warnings),
            "total_penalty": self.total_penalty,
            "contested_unit_price": self.has_contested_unit_price,
            "pipeline": self.pipeline,
        }


def pipeline_for(
    category_slug: str | None,
    explicit: list[str] | None = None,
) -> list[str]:
    """Resolve which rules apply to a commodity.

    An explicit pipeline stored on the category wins, so a policy change can be
    made in data without a code deployment.
    """
    if explicit:
        return [k for k in explicit if k in RULE_CLASSES]

    keys = list(UNIVERSAL_PIPELINE)
    slug = (category_slug or "").lower()

    if slug in FOOD_CATEGORIES:
        keys.extend(FOOD_PIPELINE)
    elif slug in PERISHABLE_NON_FOOD:
        keys.extend(PERISHABLE_PIPELINE)
    elif not slug:
        # Category unknown -- assess dates but not the FSSAI licence, since a
        # food-licence finding against an unidentified commodity would be unsound.
        keys.extend(PERISHABLE_PIPELINE)

    # De-duplicate, preserving order.
    seen: set[str] = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


def evaluate(ctx: RuleContext, explicit_pipeline: list[str] | None = None) -> EvaluationResult:
    """Run the applicable rules and aggregate the outcome."""
    keys = pipeline_for(ctx.category_slug, explicit_pipeline)
    results: list[RuleResult] = []

    for key in keys:
        rule_cls = RULE_CLASSES.get(key)
        if rule_cls is None:
            logger.warning("Unknown rule key %r in pipeline; skipping", key)
            continue
        results.append(rule_cls().run(ctx))

    contested = any(
        (r.metadata or {}).get("contested_unit_price") for r in results
    )

    total_penalty = sum(r.penalty_amount or 0.0 for r in results if r.is_violation)

    fails = [r for r in results if r.status == ViolationStatus.FAIL]
    warns = [r for r in results if r.status == ViolationStatus.WARNING]
    if fails:
        status = ComplianceStatus.NON_COMPLIANT
    elif warns:
        status = ComplianceStatus.WARNING
    else:
        status = ComplianceStatus.COMPLIANT

    violations = [r for r in results if r.is_violation]
    # Mean confidence over the rules that actually fired, so a low-confidence
    # extraction cannot yield a confident-looking score.
    confidences = [r.confidence for r in results if r.confidence is not None]
    mean_conf = sum(confidences) / len(confidences) if confidences else 1.0

    return EvaluationResult(
        results=results,
        score=compliance_score(violations, len(results), mean_conf),
        compliance_status=status,
        total_penalty=total_penalty,
        has_contested_unit_price=contested,
        pipeline=keys,
    )


def describe_rules() -> list[dict]:
    """Rule catalogue for the admin console and the policy dashboard."""
    out = []
    for key, cls in RULE_CLASSES.items():
        out.append({
            "key": key,
            "rule_id": cls.rule_id,
            "rule_name": cls.rule_name,
            "legal_clause": cls.legal_clause,
            "severity": cls.severity,
            "penalty_amount": cls.penalty_amount,
            "field_name": cls.field_name,
        })
    return out
