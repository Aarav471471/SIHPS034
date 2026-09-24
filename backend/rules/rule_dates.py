"""Manufacture, expiry and expired-stock rules -- spec rules/rule_dates.py.

Rule 6(1)(c) requires the month and year of manufacture or packing, and a
best-before date where the commodity has one.

Selling stock past its declared date is the most serious finding this engine
makes -- it is an offence under the Act in its own right, carries an immediate
public-health dimension, and is checked against the *inspection* date rather
than today's, so a case reviewed months later still reflects what the officer
actually found on the shelf.
"""
from __future__ import annotations

from datetime import date, timedelta

from rules.base import (
    CRITICAL,
    MAJOR,
    MINOR,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
    month_end,
    parse_date,
    today,
)

# Commodities with no meaningful shelf life are not required to bear a
# best-before date, so its absence must not be reported as a violation.
NO_EXPIRY_REQUIRED = {
    "salt-sugar", "stationery", "electronics-small", "paper-hygiene",
    "soaps-detergents", "home-cleaning",
}

# A manufacture date this far in the future is a misprint, not a fact.
FUTURE_TOLERANCE_DAYS = 45


class ManufactureDateRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-MFG-DATE"
    rule_name = "Month & Year of Manufacture"
    legal_clause = "Rule 6(1)(c) - Packaged Commodities Rules, 2011"
    field_name = "mfg_date"
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("mfg_date")
        reference = ctx.inspection_date or today()

        if raw is None:
            return self.failed(
                "The month and year of manufacture or packing is not declared on any "
                "captured surface. Rule 6(1)(c) requires this declaration on every "
                "pre-packaged commodity.",
                expected_value="Mfg Date: MM/YYYY",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix="Print the month and year of manufacture on the pack.",
                penalty_amount=self.penalty_amount,
            )

        parsed = parse_date(raw)
        if parsed is None:
            return self.failed(
                f"The manufacture date is printed as '{raw}', which cannot be read as "
                "a date.",
                calculated_value=raw,
                expected_value="A date in MM/YYYY or DD/MM/YYYY form",
                discrepancy="Manufacture date is unreadable",
                suggested_fix="Print the manufacture date in an unambiguous MM/YYYY form.",
            )

        mfg, precision = parsed

        if mfg > reference + timedelta(days=FUTURE_TOLERANCE_DAYS):
            return self.failed(
                f"The declared manufacture date {mfg:%m/%Y} is later than the date of "
                f"inspection ({reference:%d/%m/%Y}). A commodity cannot lawfully bear "
                "a future date of manufacture.",
                severity=MAJOR,
                calculated_value=f"{mfg:%m/%Y}",
                expected_value=f"On or before {reference:%m/%Y}",
                discrepancy=f"Manufacture date is {(mfg - reference).days} days in the future",
                suggested_fix="Correct the manufacture date printed on the pack.",
            )

        return self.passed(
            f"Month and year of manufacture declared as {mfg:%m/%Y}.",
            calculated_value=f"{mfg:%m/%Y}",
            metadata={"mfg_date": mfg.isoformat(), "precision": precision},
        )


class ExpiryDateRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-EXPIRY-DATE"
    rule_name = "Best Before / Use By Declaration"
    legal_clause = "Rule 6(1)(c) - Packaged Commodities Rules, 2011"
    field_name = "expiry_date"
    severity = MAJOR
    penalty_amount = 50_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("expiry_date")
        exempt = (ctx.category_slug or "") in NO_EXPIRY_REQUIRED

        if raw is None:
            if exempt:
                return self.passed(
                    "No best-before date is required for this class of commodity.",
                    metadata={"exempt": True},
                )
            return self.failed(
                "No best-before or use-by date is declared on any captured surface.",
                expected_value="Best Before: MM/YYYY or DD/MM/YYYY",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix="Print a best-before or use-by date on the pack.",
                penalty_amount=self.penalty_amount,
            )

        parsed = parse_date(raw)
        if parsed is None:
            return self.failed(
                f"The best-before date is printed as '{raw}', which cannot be read as "
                "a date.",
                calculated_value=raw,
                expected_value="A readable date",
                discrepancy="Best-before date is unreadable",
            )

        expiry, precision = parsed
        mfg_parsed = parse_date(ctx.get("mfg_date"))

        # A best-before earlier than manufacture is internally contradictory --
        # one of the two dates is misprinted.
        if mfg_parsed and expiry < mfg_parsed[0]:
            return self.failed(
                f"The best-before date {expiry:%d/%m/%Y} precedes the declared "
                f"manufacture date {mfg_parsed[0]:%m/%Y}. The two declarations "
                "contradict each other.",
                severity=MAJOR,
                calculated_value=f"{expiry:%d/%m/%Y}",
                expected_value=f"Later than {mfg_parsed[0]:%m/%Y}",
                discrepancy="Best-before date precedes manufacture date",
                suggested_fix="Correct whichever of the two dates is misprinted.",
            )

        return self.passed(
            f"Best-before date declared as {expiry:%d/%m/%Y}.",
            calculated_value=f"{expiry:%d/%m/%Y}",
            metadata={"expiry_date": expiry.isoformat(), "precision": precision},
        )


class ExpiredStockRule(BaseRule, _AlwaysRunnable):
    """Detects commodities offered for sale after their declared date."""

    rule_id = "R-EXPIRED-STOCK"
    rule_name = "Expired Commodity Offered for Sale"
    legal_clause = "Section 36, Legal Metrology Act 2009 r/w FSS Act 2006"
    field_name = "expiry_date"
    severity = CRITICAL
    penalty_amount = 100_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        parsed = parse_date(ctx.get("expiry_date"))
        if parsed is None:
            return self.passed(
                "No readable best-before date; shelf-life compliance not assessable "
                "by this rule.",
                metadata={"assessed": False},
            )

        expiry, precision = parsed
        reference = ctx.inspection_date or today()

        # A month-precision date is valid to the LAST day of that month. Using
        # the first would condemn stock that is still perfectly lawful to sell.
        effective = month_end(expiry) if precision == "month" else expiry

        if effective < reference:
            days = (reference - effective).days
            return self.failed(
                f"This commodity was offered for sale on {reference:%d/%m/%Y}, "
                f"{days} day{'s' if days != 1 else ''} after its declared best-before "
                f"date of {expiry:%d/%m/%Y}"
                + (" (valid to end of month)" if precision == "month" else "")
                + ". Sale of expired pre-packaged commodities is an offence.",
                severity=CRITICAL,
                calculated_value=f"Expired {days} days ago",
                expected_value=f"Best before on or after {reference:%d/%m/%Y}",
                discrepancy=f"Stock expired on {effective:%d/%m/%Y}",
                suggested_fix=(
                    "Withdraw the affected batch from sale immediately and remove it "
                    "from the shelf."
                ),
                penalty_amount=self.penalty_amount,
                metadata={"days_expired": days, "effective_expiry": effective.isoformat()},
            )

        remaining = (effective - reference).days
        if remaining <= 30:
            return self.warned(
                f"This commodity expires on {effective:%d/%m/%Y}, in {remaining} "
                f"day{'s' if remaining != 1 else ''}. Stock nearing expiry should be "
                "monitored at this retailer.",
                severity=MINOR,
                calculated_value=f"{remaining} days remaining",
                penalty_amount=None,
                metadata={"days_remaining": remaining},
            )

        return self.passed(
            f"Within shelf life: {remaining} days remain before the declared "
            f"best-before date of {effective:%d/%m/%Y}.",
            calculated_value=f"{remaining} days remaining",
            metadata={"days_remaining": remaining},
        )
