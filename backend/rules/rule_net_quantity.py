"""Net quantity declaration -- spec rules/rule_net_quantity.py.

Rule 6(1)(d) requires a net quantity declaration; Rule 8 requires it in metric
units.  Non-metric declarations (ounces, pounds, pints) are a distinct and
serious violation rather than a formatting nitpick: they make per-unit price
comparison impossible for a shopper, which is the whole purpose of the rule.
"""
from __future__ import annotations

import re

from rules.base import (
    CRITICAL,
    MAJOR,
    MINOR,
    NON_METRIC_UNITS,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
    parse_quantity,
)

# Rule 8 permits weight in g/kg, volume in ml/l, and count in numbers.
UNIT_DOMAIN = {"g": "weight", "kg": "weight", "mg": "weight",
               "ml": "volume", "L": "volume", "N": "count"}

# Categories where a specific measurement domain is expected. A "1 L" pack of
# biscuits or a "500 g" bottle of oil signals a mis-declaration.
EXPECTED_DOMAIN: dict[str, str] = {
    "edible-oils": "volume",
    "beverages-juices": "volume",
    "dairy-products": "volume",
    "biscuits-cookies": "weight",
    "atta-flour": "weight",
    "rice-grains": "weight",
    "pulses-dal": "weight",
    "spices-masala": "weight",
    "salt-sugar": "weight",
    "dry-fruits-nuts": "weight",
}


class NetQuantityRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-NET-QTY"
    rule_name = "Net Quantity Declaration"
    legal_clause = "Rule 6(1)(d) r/w Rule 8 - Packaged Commodities Rules, 2011"
    field_name = "net_quantity"
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("net_quantity")

        if raw is None:
            return self.failed(
                "No net quantity is declared on any captured surface. Rule 6(1)(d) "
                "requires the net quantity of the commodity to be declared on the "
                "principal display panel.",
                severity=CRITICAL,
                expected_value="Net Qty: <value> <metric unit>",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix=(
                    "Declare the net quantity in metric units on the principal "
                    "display panel, e.g. 'Net Qty: 250 g'."
                ),
                penalty_amount=self.penalty_amount,
            )

        lowered = raw.lower()

        # Non-metric units are checked before parsing, because parse_quantity
        # only recognises metric units and would otherwise report the pack as
        # having no quantity at all -- the wrong finding for the wrong reason.
        for unit in NON_METRIC_UNITS:
            if re.search(rf"\b{re.escape(unit)}\b", lowered):
                return self.failed(
                    f"The net quantity is declared as '{raw}', using the non-metric "
                    f"unit '{unit}'. Rule 8 requires net quantity to be declared in "
                    "metric units only.",
                    severity=MAJOR,
                    calculated_value=raw,
                    expected_value="Metric units: g, kg, ml, L or number (N)",
                    discrepancy=f"Non-metric unit '{unit}' used",
                    suggested_fix=(
                        f"Re-declare the net quantity in metric units instead of {unit}."
                    ),
                    penalty_amount=25_000.0,
                )

        parsed = parse_quantity(raw)
        if parsed is None:
            return self.failed(
                f"The net quantity is printed as '{raw}', from which no quantity and "
                "unit can be read.",
                calculated_value=raw,
                expected_value="A numeric value followed by a metric unit",
                discrepancy="Net quantity declaration is unreadable",
                suggested_fix="Print the net quantity as a number followed by its unit.",
            )

        value, unit = parsed

        if value <= 0:
            return self.failed(
                f"The declared net quantity of {value:g} {unit} is not a valid quantity.",
                calculated_value=f"{value:g} {unit}",
                expected_value="A quantity greater than zero",
                discrepancy="Non-positive net quantity",
            )

        # Cross-check the measurement domain against the commodity type.
        domain = UNIT_DOMAIN.get(unit)
        expected_domain = EXPECTED_DOMAIN.get(ctx.category_slug or "")
        if expected_domain and domain and domain != expected_domain:
            return self.warned(
                f"The net quantity is declared as {value:g} {unit}, a {domain} "
                f"measurement, but commodities in this category are ordinarily "
                f"declared by {expected_domain}.",
                severity=MINOR,
                calculated_value=f"{value:g} {unit}",
                expected_value=f"A {expected_domain} declaration",
                discrepancy=f"{domain.title()} unit used where {expected_domain} expected",
                suggested_fix=(
                    f"Confirm the declaration; {expected_domain} units are expected "
                    "for this commodity."
                ),
                penalty_amount=None,
                metadata={"value": value, "unit": unit, "domain": domain},
            )

        return self.passed(
            f"Net quantity {value:g} {unit} is declared in metric units, as required.",
            calculated_value=f"{value:g} {unit}",
            metadata={"value": value, "unit": unit, "domain": domain},
        )
