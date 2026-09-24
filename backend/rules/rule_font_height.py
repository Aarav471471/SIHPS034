"""Minimum declaration height -- spec rules/rule_font_height.py.

Rule 7 of the Packaged Commodities Rules ("Principal Display Panel -- its area,
size and letter etc.") sets a minimum height for the numerals and letters of the
mandatory declarations, scaled to the area of the principal display panel. Small
print is not a cosmetic complaint: an unreadable MRP is functionally an
undeclared MRP.

This is the only rule that requires a physical measurement, and therefore the
only one that can be wrong because of a geometry error upstream. It refuses to
produce a finding when the pixels-per-millimetre scale is unknown, rather than
converting an unfounded pixel count into millimetres and citing it.

Sources for the schedules below: the Second Schedule as reproduced in the full
text of the Rules on Indian Kanoon (doc/100694501, doc/151004919). The gazette
PDF on consumeraffairs.gov.in should be treated as the authority if the two ever
disagree -- see AUDIT.md.
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

# ---------------------------------------------------------------------------
# Rule 7(2) r/w the Second Schedule.
#
# There are two tables, and picking the wrong one is a real error rather than a
# rounding difference -- a 250 cm2 panel requires 2.5 mm under Table I but only
# 2.0 mm under Table II.
#
#   Table I  applies where net quantity is declared by WEIGHT or VOLUME.
#   Table II applies where it is declared by LENGTH, AREA or NUMBER.
#
# Each entry is (upper bound of panel area in cm2, minimum height in mm for the
# general case, minimum height in mm where the container is blown, formed,
# moulded, embossed or perforated -- the text being formed in the container
# rather than printed on it).
# ---------------------------------------------------------------------------
TABLE_I: list[tuple[float, float, float]] = [
    (50.0, 1.0, 1.5),
    (100.0, 1.5, 3.0),
    (500.0, 2.5, 4.0),
    (2500.0, 4.0, 6.0),
    (float("inf"), 6.0, 6.0),
]

TABLE_II: list[tuple[float, float, float]] = [
    (100.0, 1.0, 2.0),
    (500.0, 2.0, 4.0),
    (2500.0, 4.0, 6.0),
    (float("inf"), 6.0, 6.0),
]

# Rule 7(3): a floor for LETTERS that does not scale with panel area at all.
LETTER_MIN_MM = 1.0
LETTER_MIN_MOULDED_MM = 2.0

# Canonical units, as produced by rules.base.parse_quantity, grouped by which
# table of the Second Schedule they select.
WEIGHT_VOLUME_UNITS = frozenset({"kg", "g", "mg", "L", "ml"})
LENGTH_AREA_NUMBER_UNITS = frozenset({"N", "cm", "m", "cm2", "m2"})

# Declarations to which the numeral height requirement applies.
MEASURED_FIELDS = ("mrp", "net_quantity", "unit_price")

# Tolerance for measurement error in the imaging chain. Below this margin a
# shortfall is more likely a geometry artefact than a printing defect, and a
# penalty should not rest on it.
MEASUREMENT_TOLERANCE_MM = 0.25


def schedule_for(unit: str | None) -> tuple[list[tuple[float, float, float]], str]:
    """Select the Second Schedule table that governs this declaration.

    Defaults to Table I. Weight and volume cover the overwhelming majority of
    packaged commodities, and Table I is the stricter of the two at every
    overlapping area, so an unrecognised unit is not quietly given the easier
    standard.
    """
    if unit in LENGTH_AREA_NUMBER_UNITS:
        return TABLE_II, "II"
    return TABLE_I, "I"


def required_height_mm(
    panel_area_cm2: float | None,
    unit: str | None = None,
    moulded: bool = False,
) -> float | None:
    """Minimum permitted numeral height for a panel area and quantity kind."""
    if not panel_area_cm2 or panel_area_cm2 <= 0:
        return None
    table, _ = schedule_for(unit)
    for max_area, general, blown in table:
        # Bounds are inclusive of their upper value. The Schedule's own wording
        # mixes "less than" and "up to", and at an exact boundary the reading
        # that favours the packer is the defensible one for a penalty.
        if panel_area_cm2 <= max_area:
            return blown if moulded else general
    return None


def required_letter_height_mm(moulded: bool = False) -> float:
    """Rule 7(3) floor for letters, independent of panel area."""
    return LETTER_MIN_MOULDED_MM if moulded else LETTER_MIN_MM


class FontHeightRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-FONT-HEIGHT"
    rule_name = "Minimum Height of Declarations"
    legal_clause = "Rule 7(2) r/w Second Schedule - Packaged Commodities Rules, 2011"
    field_name = "net_quantity"
    severity = MINOR
    penalty_amount = 10_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        area = ctx.surface_area_cm2
        if not area and ctx.package_width_cm and ctx.package_height_cm:
            area = ctx.package_width_cm * ctx.package_height_cm

        if not area:
            return self.warned(
                "Declaration height could not be assessed: the dimensions of the "
                "package were not recorded, so the minimum permitted height under "
                "the Second Schedule cannot be determined.",
                severity=MINOR,
                penalty_amount=None,
                metadata={"assessed": False},
            )

        measured = {
            name: mm for name, mm in (ctx.font_heights_mm or {}).items()
            if name in MEASURED_FIELDS and mm and mm > 0
        }

        if not measured:
            return self.warned(
                "Declaration height could not be assessed: no character height was "
                "measurable from the captured surfaces. This normally means the "
                "physical scale of the image could not be established.",
                severity=MINOR,
                penalty_amount=None,
                metadata={"assessed": False, "panel_area_cm2": round(area, 1)},
            )

        # Which table applies turns on how net quantity is declared, so it is
        # read from the declaration itself rather than assumed.
        from rules.base import parse_quantity

        qty = parse_quantity(ctx.get("net_quantity"))
        unit = qty[1] if qty else None
        _, table_name = schedule_for(unit)

        # A blown or moulded container gets the more lenient column of the
        # Schedule, since the text is formed in the container rather than printed.
        moulded = bool((ctx.metadata or {}).get("is_moulded_container"))
        required = required_height_mm(area, unit=unit, moulded=moulded)
        if required is None:
            return self.warned(
                f"No minimum height is defined for a display panel area of "
                f"{area:.1f} cm2.",
                severity=MINOR,
                penalty_amount=None,
            )

        cite = (
            f"Table {table_name} of the Second Schedule"
            f"{', blown/moulded column' if moulded else ''}"
        )

        undersized = {
            name: mm for name, mm in measured.items()
            if mm < required - MEASUREMENT_TOLERANCE_MM
        }

        if not undersized:
            smallest = min(measured.items(), key=lambda kv: kv[1])
            return self.passed(
                f"All measured declarations meet the {required:.1f} mm minimum set by "
                f"{cite} for a {area:.0f} cm2 display panel (smallest measured: "
                f"{smallest[0]} at {smallest[1]:.2f} mm).",
                calculated_value=f"{smallest[1]:.2f} mm",
                expected_value=f"{required:.1f} mm minimum",
                metadata={
                    "panel_area_cm2": round(area, 1),
                    "measured": measured,
                    "schedule_table": table_name,
                    "quantity_unit": unit,
                    "moulded": moulded,
                },
            )

        worst_name, worst_mm = min(undersized.items(), key=lambda kv: kv[1])
        listed = ", ".join(
            f"{n} at {mm:.2f} mm" for n, mm in sorted(undersized.items(), key=lambda kv: kv[1])
        )

        return self.failed(
            f"{len(undersized)} mandatory declaration"
            f"{'s are' if len(undersized) > 1 else ' is'} printed below the minimum "
            f"height required by Rule 7(2). For a display panel of {area:.0f} cm2 the "
            f"minimum numeral height under {cite} is {required:.1f} mm; measured: "
            f"{listed}.",
            field_name=worst_name,
            severity=MAJOR if worst_mm < required * 0.6 else MINOR,
            calculated_value=f"{worst_mm:.2f} mm",
            expected_value=f"{required:.1f} mm minimum",
            discrepancy=(
                f"{worst_name} is {required - worst_mm:.2f} mm below the permitted minimum"
            ),
            suggested_fix=(
                f"Increase the {worst_name} declaration to at least {required:.1f} mm "
                "character height for this pack size."
            ),
            penalty_amount=self.penalty_amount,
            metadata={
                "panel_area_cm2": round(area, 1),
                "required_mm": required,
                "measured": measured,
                "undersized": undersized,
                "tolerance_mm": MEASUREMENT_TOLERANCE_MM,
                "schedule_table": table_name,
                "quantity_unit": unit,
                "moulded": moulded,
            },
        )


class LetterHeightRule(BaseRule, _AlwaysRunnable):
    """Rule 7(3) -- a floor for letters that does not scale with panel area.

    Separate from the numeral rule because it is a different sub-rule with a
    different test: 1 mm everywhere, 2 mm on a moulded container, regardless of
    how large the panel is. A pack can satisfy the Table I numeral height and
    still fail this on its lettering.
    """

    rule_id = "R-LETTER-HEIGHT"
    rule_name = "Minimum Height of Lettering"
    legal_clause = "Rule 7(3) - Packaged Commodities Rules, 2011"
    field_name = "manufacturer_name"
    severity = MINOR
    penalty_amount = 10_000.0

    # Declarations that are lettering rather than numerals.
    LETTER_FIELDS = (
        "manufacturer_name",
        "manufacturer_address",
        "country_of_origin",
        "customer_care",
        "common_name",
    )

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        measured = {
            name: mm for name, mm in (ctx.font_heights_mm or {}).items()
            if name in self.LETTER_FIELDS and mm and mm > 0
        }

        if not measured:
            return self.warned(
                "Lettering height could not be assessed: no letter height was "
                "measurable from the captured surfaces.",
                severity=MINOR,
                penalty_amount=None,
                metadata={"assessed": False},
            )

        moulded = bool((ctx.metadata or {}).get("is_moulded_container"))
        required = required_letter_height_mm(moulded)

        undersized = {
            name: mm for name, mm in measured.items()
            if mm < required - MEASUREMENT_TOLERANCE_MM
        }

        if not undersized:
            smallest = min(measured.items(), key=lambda kv: kv[1])
            return self.passed(
                f"All measured lettering meets the {required:.1f} mm minimum under "
                f"Rule 7(3) (smallest measured: {smallest[0]} at {smallest[1]:.2f} mm).",
                calculated_value=f"{smallest[1]:.2f} mm",
                expected_value=f"{required:.1f} mm minimum",
                metadata={"measured": measured, "moulded": moulded},
            )

        worst_name, worst_mm = min(undersized.items(), key=lambda kv: kv[1])
        listed = ", ".join(
            f"{n} at {mm:.2f} mm" for n, mm in sorted(undersized.items(), key=lambda kv: kv[1])
        )

        return self.failed(
            f"Lettering is printed below the {required:.1f} mm minimum required by "
            f"Rule 7(3)"
            f"{' for a blown or moulded container' if moulded else ''}; measured: "
            f"{listed}.",
            field_name=worst_name,
            severity=MINOR,
            calculated_value=f"{worst_mm:.2f} mm",
            expected_value=f"{required:.1f} mm minimum",
            discrepancy=f"{worst_name} is {required - worst_mm:.2f} mm below the minimum",
            suggested_fix=(
                f"Increase the {worst_name} lettering to at least {required:.1f} mm."
            ),
            penalty_amount=self.penalty_amount,
            metadata={
                "required_mm": required,
                "measured": measured,
                "undersized": undersized,
                "tolerance_mm": MEASUREMENT_TOLERANCE_MM,
                "moulded": moulded,
            },
        )
