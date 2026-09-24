"""Unit sale price -- spec rules/rule_unit_price.py.

Rule 6(11) requires a unit sale price so shoppers can compare packs of different
sizes. This is the one rule that does real arithmetic rather than pattern
matching, and it is the strongest check in the engine: MRP divided by net
quantity is a fact, not an opinion, so a mismatch is provable and a vision
model's misreading of either input shows up here as a contradiction.

That is also why a contested unit price is one of the three peer-review triggers
in spec 3.E -- when the arithmetic disagrees with the pack, something was
misread and a human should look before a notice issues.

On the clause: unit sale price was substituted into Rule 6 as sub-rule (11) by
the Legal Metrology (Packaged Commodities) Amendment Rules, 2021, brought into
force on 1 October 2022. Earlier drafts of this file cited Rule 6(2), which is a
different sub-rule. The amendment also prescribes the DENOMINATOR rather than
leaving it to the packer, which is what the arithmetic below now enforces.
"""
from __future__ import annotations

from rules.base import (
    MAJOR,
    MINOR,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
    parse_currency,
    parse_quantity,
    to_base_units,
)

# Rule 6(11): the unit in which the price must be expressed is fixed by the size
# of the pack, not chosen by the packer.
#
#   weight  -- per gram below 1 kg, per kilogram above
#   volume  -- per millilitre below 1 litre, per litre above
#   length  -- per centimetre below 1 metre, per metre above
#   number  -- per number or unit
#
# Keyed by the base unit that rules.base.to_base_units produces.
PRESCRIBED_UNIT: dict[str, tuple[float, str, str]] = {
    # base unit: (threshold in base units, small-pack unit, large-pack unit)
    "g": (1000.0, "g", "kg"),
    "ml": (1000.0, "ml", "L"),
    "cm": (100.0, "cm", "m"),
    "N": (float("inf"), "N", "N"),
}

# How many base units make up the prescribed larger unit.
LARGER_UNIT_FACTOR: dict[str, float] = {"kg": 1000.0, "L": 1000.0, "m": 100.0, "N": 1.0}

# Rule 26 exempts packages whose net quantity is below 10 g or 10 ml from the
# Rules, and the unit-sale-price requirement is exempted in alignment with it.
# (An earlier draft carried these same thresholds but attributed them to
# Rule 6(2), which does not contain them.)  Tobacco is carved out of the Rule 26
# exemption by proviso, so it is checked separately below.
RULE_26_EXEMPTION = {"g": 10.0, "ml": 10.0}
TOBACCO_CATEGORIES = frozenset({"tobacco", "tobacco-products", "cigarettes"})

# Rule 6(11) requires the figure rounded to two decimal places, so the pack's
# own rounding is lawful and must not be reported as a discrepancy.
ROUNDING_DP = 2
ABSOLUTE_TOLERANCE = 0.005 + 1e-9   # half of the last retained decimal place
RELATIVE_TOLERANCE = 0.05           # 5%, for reading error in either input


def prescribed_unit(base_value: float, base_unit: str) -> tuple[float, str] | None:
    """Return (quantity expressed in the prescribed unit, that unit's name)."""
    spec = PRESCRIBED_UNIT.get(base_unit)
    if not spec:
        return None
    threshold, small, large = spec
    # "less than one kilogram ... more than one kilogram" leaves the exact
    # boundary undrafted; treating exactly 1 kg as the smaller unit keeps the
    # engine from failing a pack on an ambiguity in the text.
    if base_value <= threshold:
        return base_value, small
    return base_value / LARGER_UNIT_FACTOR[large], large


class UnitPriceRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-UNIT-PRICE"
    rule_name = "Unit Sale Price Declaration"
    legal_clause = "Rule 6(11) - Packaged Commodities Rules, 2011 (as amended 2021)"
    field_name = "unit_price"
    severity = MAJOR
    penalty_amount = 10_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        declared = ctx.get("unit_price")
        mrp = parse_currency(ctx.get("mrp"))
        qty = parse_quantity(ctx.get("net_quantity"))

        # Without MRP and net quantity there is nothing to compute against;
        # those absences are reported by their own rules, not duplicated here.
        if mrp is None or qty is None:
            if declared is None:
                return self.warned(
                    "Unit sale price could not be assessed: the retail sale price "
                    "and/or net quantity were not extracted, so the required unit "
                    "price cannot be computed for comparison.",
                    severity=MINOR,
                    penalty_amount=None,
                )
            return self.warned(
                f"A unit sale price of '{declared}' is declared, but it could not be "
                "verified because the retail sale price and/or net quantity were not "
                "extracted.",
                severity=MINOR,
                calculated_value=declared,
                penalty_amount=None,
            )

        value, unit = qty
        base = to_base_units(value, unit)
        if base is None:
            return self.warned(
                f"Unit sale price could not be computed for the unit '{unit}'.",
                severity=MINOR,
                penalty_amount=None,
            )
        base_value, base_unit = base

        if base_value <= 0:
            return self.warned(
                "Unit sale price could not be computed from a zero net quantity.",
                severity=MINOR,
                penalty_amount=None,
            )

        # Rule 26: below 10 g / 10 ml the package falls outside the Rules
        # altogether, save for tobacco, which the proviso keeps within them.
        threshold = RULE_26_EXEMPTION.get(base_unit)
        is_tobacco = (ctx.category_slug or "") in TOBACCO_CATEGORIES
        if threshold is not None and base_value < threshold and not is_tobacco:
            return self.passed(
                f"Unit sale price is not required: the net quantity "
                f"({value:g} {unit}) is below the 10 {base_unit} threshold at which "
                "Rule 26 exempts a package from these Rules.",
                metadata={"exempt": True, "reason": "rule_26_small_package"},
            )

        pres = prescribed_unit(base_value, base_unit)
        if pres is None:
            return self.warned(
                f"Rule 6(11) prescribes no unit of comparison for '{base_unit}'.",
                severity=MINOR,
                penalty_amount=None,
            )
        pres_qty, pres_unit = pres
        expected = round(mrp / pres_qty, ROUNDING_DP) if pres_qty else None

        if expected is None:
            return self.warned(
                "Unit sale price could not be computed from a zero net quantity.",
                severity=MINOR,
                penalty_amount=None,
            )

        expected_str = f"Rs. {expected:.2f} per {pres_unit}"

        # Second proviso to Rule 6(11): where the retail sale price and the unit
        # sale price are the same figure, no separate declaration is required.
        # A single-unit pack is the ordinary case -- one 500 ml bottle priced per
        # bottle needs no "per bottle" restatement of its own MRP.
        if abs(expected - round(mrp, ROUNDING_DP)) <= ABSOLUTE_TOLERANCE:
            return self.passed(
                "No separate unit sale price is required: the unit sale price and "
                "the retail sale price are the same figure "
                f"({expected_str}), which the second proviso to Rule 6(11) exempts.",
                calculated_value=declared or "Not declared",
                expected_value=expected_str,
                metadata={"exempt": True, "reason": "rsp_equals_usp"},
            )

        if declared is None:
            return self.failed(
                "No unit sale price is declared. Rule 6(11) requires the unit sale "
                "price to be stated so that packages of different sizes can be "
                f"compared. For this package it is Rs.{mrp:.2f} / {pres_qty:g} "
                f"{pres_unit} = {expected_str}.",
                calculated_value="Not declared",
                expected_value=expected_str,
                discrepancy="Mandatory unit sale price absent",
                suggested_fix=(
                    f"Print '{expected_str}' adjacent to the retail sale price."
                ),
                penalty_amount=self.penalty_amount,
                metadata={
                    "expected_unit_price": expected,
                    "prescribed_quantity": pres_qty,
                    "prescribed_unit": pres_unit,
                },
            )

        # A unit price IS declared -- verify the arithmetic.
        declared_amount = parse_currency(declared)
        if declared_amount is None:
            return self.warned(
                f"The unit sale price is printed as '{declared}', from which no "
                "amount can be read for verification.",
                severity=MINOR,
                calculated_value=declared,
                expected_value=expected_str,
                penalty_amount=None,
            )

        tolerance = max(ABSOLUTE_TOLERANCE, expected * RELATIVE_TOLERANCE)

        if abs(declared_amount - expected) <= tolerance:
            return self.passed(
                f"Declared unit sale price Rs.{declared_amount:.2f} per {pres_unit} "
                f"is consistent with Rs.{mrp:.2f} / {pres_qty:g} {pres_unit}.",
                calculated_value=f"Rs. {declared_amount:.2f} per {pres_unit}",
                expected_value=expected_str,
                metadata={"expected_unit_price": expected, "verified": True},
            )

        # Before failing, check whether the pack simply used the other unit of
        # the pair. That is the wrong unit under Rule 6(11), but it is a
        # different and much lesser fault than bad arithmetic, and saying so
        # accurately is the difference between a fixable label note and an
        # accusation of mispricing.
        other = self._other_unit_value(mrp, base_value, base_unit, pres_unit)
        if other is not None:
            other_value, other_unit = other
            if abs(declared_amount - other_value) <= max(
                ABSOLUTE_TOLERANCE, other_value * RELATIVE_TOLERANCE
            ):
                return self.warned(
                    f"The unit sale price is arithmetically correct but expressed per "
                    f"{other_unit}. For a net quantity of {value:g} {unit}, Rule 6(11) "
                    f"prescribes the price per {pres_unit} ({expected_str}).",
                    severity=MINOR,
                    calculated_value=f"Rs. {declared_amount:.2f} per {other_unit}",
                    expected_value=expected_str,
                    discrepancy=f"Declared per {other_unit}; Rule 6(11) prescribes per {pres_unit}",
                    suggested_fix=f"Restate the unit sale price as {expected_str}.",
                    penalty_amount=None,
                    metadata={"wrong_prescribed_unit": True,
                              "declared_unit": other_unit,
                              "prescribed_unit": pres_unit},
                )

        pct = ((declared_amount - expected) / expected * 100) if expected else 0.0
        return self.failed(
            f"The declared unit sale price of Rs.{declared_amount:.2f} per {pres_unit} "
            f"does not follow from the declarations on the pack. Rs.{mrp:.2f} divided "
            f"by {pres_qty:g} {pres_unit} gives {expected_str}, a discrepancy of "
            f"{pct:+.1f}%.",
            severity=MAJOR,
            calculated_value=f"Rs. {declared_amount:.2f} per {pres_unit}",
            expected_value=expected_str,
            discrepancy=(
                f"Declared unit price differs from MRP / net quantity by {pct:+.1f}%"
            ),
            suggested_fix=(
                f"Correct the unit sale price to {expected_str}, or correct the "
                "retail sale price / net quantity it is derived from."
            ),
            penalty_amount=self.penalty_amount,
            # Flagged for the confidence layer: a contested unit price is a
            # peer-review trigger under spec 3.E.
            metadata={
                "contested_unit_price": True,
                "declared": declared_amount,
                "expected": expected,
                "deviation_pct": round(pct, 2),
            },
        )

    @staticmethod
    def _other_unit_value(
        mrp: float, base_value: float, base_unit: str, pres_unit: str,
    ) -> tuple[float, str] | None:
        """The price expressed in the pair's other unit, for diagnosis only."""
        spec = PRESCRIBED_UNIT.get(base_unit)
        if not spec:
            return None
        _, small, large = spec
        if small == large:
            return None
        other = large if pres_unit == small else small
        factor = LARGER_UNIT_FACTOR[large] if other == large else 1.0
        qty = base_value / factor
        if qty <= 0:
            return None
        return round(mrp / qty, ROUNDING_DP), other
