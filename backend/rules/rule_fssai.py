"""FSSAI licence declaration -- spec rules/rule_fssai.py.

The Food Safety and Standards (Packaging and Labelling) Regulations require the
FSSAI licence number of the manufacturer or packer on every pre-packaged food.

Only applies to food commodities: demanding a food licence on a bar of soap
would be a false finding, and false findings are what destroy an enforcement
system's credibility.
"""
from __future__ import annotations

from rules.base import (
    MAJOR,
    MINOR,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
)
from extraction.gs1_validator import validate_fssai

# Categories that are food or nutraceutical and therefore in FSSAI's scope.
FOOD_SECTORS = {"Food", "Healthcare"}
FOOD_CATEGORY_SLUGS = {
    "biscuits-cookies", "edible-oils", "dairy-products", "ghee-butter",
    "sweets-mithai", "spices-masala", "atta-flour", "rice-grains", "pulses-dal",
    "tea-coffee", "snacks-namkeen", "chocolates-confectionery", "beverages-juices",
    "instant-noodles", "baby-food", "breakfast-cereals", "sauces-condiments",
    "dry-fruits-nuts", "salt-sugar", "frozen-foods", "pharma-otc",
}


class FSSAILicenceRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-FSSAI"
    rule_name = "FSSAI Licence Number"
    legal_clause = "FSS (Packaging & Labelling) Regulations, 2011 - Regulation 2.2.2"
    field_name = "fssai_licence"
    severity = MAJOR
    penalty_amount = 50_000.0

    def _in_scope(self, ctx: RuleContext) -> bool:
        if ctx.category_slug:
            return ctx.category_slug in FOOD_CATEGORY_SLUGS
        sector = (ctx.metadata or {}).get("sector")
        if sector:
            return sector in FOOD_SECTORS
        # Unknown category: the presence of a declared licence is itself
        # evidence the commodity is a food, so verify what is there.
        return ctx.has("fssai_licence")

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("fssai_licence")
        in_scope = self._in_scope(ctx)

        if not in_scope:
            return self.passed(
                "FSSAI licence declaration is not applicable to this class of "
                "commodity.",
                metadata={"applicable": False},
            )

        if raw is None:
            return self.failed(
                "No FSSAI licence number is declared on any captured surface. Every "
                "pre-packaged food commodity must bear the licence number of the "
                "manufacturer or packer.",
                expected_value="A 14-digit FSSAI licence number",
                calculated_value="Not declared",
                discrepancy="Mandatory food licence declaration absent",
                suggested_fix=(
                    "Print 'FSSAI Lic. No. <14 digits>' on the label, adjacent to the "
                    "FSSAI logo."
                ),
                penalty_amount=self.penalty_amount,
            )

        check = validate_fssai(raw)

        if not check.is_valid_format:
            return self.failed(
                f"The declared FSSAI licence number '{raw}' is not valid: {check.note}.",
                calculated_value=raw,
                expected_value="A well-formed 14-digit FSSAI licence number",
                discrepancy=check.note,
                suggested_fix=(
                    "Correct the licence number to the 14-digit number issued by the "
                    "Food Safety and Standards Authority of India."
                ),
                penalty_amount=self.penalty_amount,
                metadata={"fssai_check": check.note},
            )

        # Format is sound but the issuing-authority code was not recognised. That
        # is reported as unverified, not as a violation -- the local reference
        # list is not authoritative enough to condemn a licence on its own.
        if check.state_name is None:
            return self.warned(
                f"FSSAI licence {check.number} is correctly formed, but its "
                f"issuing-authority code '{check.state_code}' was not recognised and "
                "could not be verified against the registry.",
                severity=MINOR,
                calculated_value=check.number,
                discrepancy="Issuing authority not verified",
                suggested_fix="Confirm the licence is current with the issuing authority.",
                penalty_amount=None,
                metadata={"fssai_check": check.note},
            )

        return self.passed(
            f"FSSAI licence {check.number} is a well-formed {check.licence_type} "
            f"issued by {check.state_name}.",
            calculated_value=check.number,
            metadata={
                "licence_type": check.licence_type,
                "issuing_authority": check.state_name,
                "year": check.year,
            },
        )
