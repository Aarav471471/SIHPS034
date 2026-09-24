"""MRP declaration -- spec rules/rule_mrp_format.py.

Rule 6(1)(e) requires a retail sale price on the principal display panel, and
Rule 2(m) defines that price as inclusive of all taxes.  The "inclusive of all
taxes" wording is not decorative: without it a retailer can argue tax is payable
on top, which is the most common form of lawful-looking overcharging.
"""
from __future__ import annotations

from rules.base import (
    CRITICAL,
    MAJOR,
    MINOR,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
    parse_currency,
)

INCLUSIVE_PHRASES = (
    "incl. of all taxes", "inclusive of all taxes", "incl of all taxes",
    "incl. all taxes", "including all taxes", "inclusive of taxes",
    "incl.of all taxes", "all taxes included", "incl taxes",
    "mrp (incl", "max retail price (incl",
)

EXCLUSIVE_RED_FLAGS = (
    "exclusive of taxes", "excl. of taxes", "plus taxes", "extra taxes",
    "taxes extra", "+ gst", "plus gst", "gst extra",
)


class MRPFormatRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-MRP-FORMAT"
    rule_name = "Retail Sale Price Declaration"
    legal_clause = "Rule 6(1)(e) r/w Rule 2(m) - Packaged Commodities Rules, 2011"
    field_name = "mrp"
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("mrp")

        if raw is None:
            return self.failed(
                "No retail sale price is declared on any captured surface of this "
                "package. Rule 6(1)(e) requires the retail sale price to appear on "
                "the principal display panel.",
                severity=CRITICAL,
                expected_value="MRP Rs. <amount> (Incl. of all taxes)",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix=(
                    "Print the retail sale price on the principal display panel in "
                    "the form 'MRP Rs. <amount> (Incl. of all taxes)'."
                ),
                penalty_amount=self.penalty_amount,
            )

        amount = parse_currency(raw)
        lowered = raw.lower()

        if amount is None:
            return self.failed(
                f"The retail sale price is printed as '{raw}', from which no "
                "monetary amount can be read.",
                calculated_value=raw,
                expected_value="A numeric amount in rupees",
                discrepancy="Price declaration is not a readable amount",
                suggested_fix="Print the price as a clear numeric rupee amount.",
            )

        if amount <= 0:
            return self.failed(
                f"The declared retail sale price of Rs.{amount:.2f} is not a valid price.",
                calculated_value=f"Rs.{amount:.2f}",
                expected_value="An amount greater than zero",
                discrepancy="Non-positive retail sale price",
            )

        # Explicitly claiming taxes are extra is worse than merely omitting the
        # inclusive wording -- it asserts the opposite of what the law requires.
        for flag in EXCLUSIVE_RED_FLAGS:
            if flag in lowered:
                return self.failed(
                    f"The price declaration states '{raw}', indicating that taxes are "
                    "charged in addition to the printed price. Rule 2(m) defines the "
                    "retail sale price as the maximum price inclusive of all taxes; no "
                    "amount may lawfully be charged above it.",
                    severity=CRITICAL,
                    calculated_value=raw,
                    expected_value=f"MRP Rs. {amount:.2f} (Incl. of all taxes)",
                    discrepancy="Price declared exclusive of taxes",
                    suggested_fix=(
                        "Remove the exclusive-of-taxes wording and declare the price "
                        "as inclusive of all taxes."
                    ),
                    penalty_amount=50_000.0,
                )

        has_inclusive = any(p in lowered for p in INCLUSIVE_PHRASES)
        if not has_inclusive:
            return self.warned(
                f"The retail sale price Rs.{amount:.2f} is declared without the "
                "mandatory 'inclusive of all taxes' wording required by Rule 2(m).",
                severity=MINOR,
                calculated_value=raw,
                expected_value=f"MRP Rs. {amount:.2f} (Incl. of all taxes)",
                discrepancy="Inclusive-of-taxes wording not found",
                suggested_fix=(
                    "Add '(Incl. of all taxes)' adjacent to the retail sale price."
                ),
                penalty_amount=10_000.0,
                metadata={"parsed_mrp": amount},
            )

        return self.passed(
            f"Retail sale price Rs.{amount:.2f} is declared inclusive of all taxes, "
            "as required.",
            calculated_value=f"Rs.{amount:.2f}",
            metadata={"parsed_mrp": amount},
        )
