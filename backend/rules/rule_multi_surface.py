"""Principal display panel aggregation -- spec rules/rule_multi_surface.py.

Rule 7 defines the *principal display panel* -- the face a shopper sees on the
shelf -- and requires the mandatory declarations to appear on it, not merely
somewhere on the package. An MRP printed only on the underside of a carton
satisfies nobody. Rule 9 is a separate requirement about how the declarations
are printed (legibility, contrast, script); earlier drafts of this file cited it
for panel placement, which was the wrong clause.

This rule differs from the others in that it reasons about *where* declarations
were found rather than what they say, and it is also the rule that guards
against a false accusation: if an officer only photographed the front, a
declaration missing from that one image is unproven, not absent.  Saying so
plainly is what stops an incomplete capture becoming a wrongful notice.
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

# Rule 7 -- declarations that must appear on the principal display panel.
PRINCIPAL_PANEL_FIELDS = ("mrp", "net_quantity")

# Declarations that may lawfully appear on any panel.
ANY_PANEL_FIELDS = (
    "mfg_date", "expiry_date", "manufacturer_name", "manufacturer_address",
    "country_of_origin", "customer_care", "fssai_licence", "batch_number",
)

FRONT_SURFACES = {"FRONT", "DIE_LINE"}


class MultiSurfaceRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-MULTI-SURFACE"
    rule_name = "Principal Display Panel Requirements"
    legal_clause = "Rule 7 r/w Rule 9 - Packaged Commodities Rules, 2011"
    field_name = None
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        captured = {s.upper() for s in (ctx.surfaces or [])}

        if not captured:
            return self.warned(
                "No surfaces were recorded for this inspection, so panel placement "
                "could not be assessed.",
                severity=MINOR,
                penalty_amount=None,
                metadata={"assessed": False},
            )

        has_front = bool(captured & FRONT_SURFACES)
        single_surface = len(captured) == 1

        # Three distinct states, which must not be collapsed into two:
        #   missing   -- the declaration was not found at all
        #   unlocated -- it WAS found, but which panel it sits on was not recorded
        #   placed    -- found, with a known panel
        # Treating "unlocated" as "missing" would report a pack that carries a
        # perfectly valid MRP as having none, purely because surface metadata
        # was absent. That is a wrongful finding, not a conservative one.
        placement: dict[str, str | None] = {}
        missing: list[str] = []
        unlocated: list[str] = []
        for name in PRINCIPAL_PANEL_FIELDS:
            if not ctx.has(name):
                missing.append(name)
                placement[name] = None
                continue
            surface = ctx.surface_of(name)
            placement[name] = surface
            if surface is None:
                unlocated.append(name)

        misplaced = [
            n for n, s in placement.items()
            if s is not None and s.upper() not in FRONT_SURFACES
        ]

        # A declaration absent from a single captured surface is unproven, not
        # absent. Issuing a notice on that basis would be unsound -- the
        # remedy is to photograph the remaining panels.
        if missing and single_surface:
            return self.warned(
                f"Only the {next(iter(captured))} surface was captured. "
                f"{', '.join(missing)} was not found on it, but may be printed on a "
                "panel that was not photographed. Capture the remaining surfaces "
                "before treating this as a violation.",
                severity=MINOR,
                calculated_value=f"1 surface captured: {next(iter(captured))}",
                expected_value="FRONT and BACK surfaces at minimum",
                discrepancy="Insufficient capture coverage to conclude absence",
                suggested_fix=(
                    "Photograph the remaining panels of the package and re-run the "
                    "inspection."
                ),
                penalty_amount=None,
                metadata={"surfaces": sorted(captured), "unproven": missing},
            )

        if not has_front:
            return self.warned(
                "The principal display panel was not among the captured surfaces "
                f"({', '.join(sorted(captured))}), so compliance with Rule 9 placement "
                "requirements could not be established.",
                severity=MINOR,
                calculated_value=", ".join(sorted(captured)),
                expected_value="FRONT surface capture",
                discrepancy="Principal display panel not photographed",
                suggested_fix="Capture the front face of the package.",
                penalty_amount=None,
                metadata={"surfaces": sorted(captured)},
            )

        if misplaced:
            listed = ", ".join(f"{n} (found on {placement[n]})" for n in misplaced)
            return self.failed(
                f"Rule 9 requires the retail sale price and net quantity to appear on "
                f"the principal display panel. The following were found only on other "
                f"panels: {listed}.",
                field_name=misplaced[0],
                severity=MAJOR,
                calculated_value=listed,
                expected_value="Declared on the FRONT (principal display) panel",
                discrepancy="Mandatory declaration not on the principal display panel",
                suggested_fix=(
                    "Move the affected declarations onto the principal display panel."
                ),
                penalty_amount=self.penalty_amount,
                metadata={"placement": placement, "surfaces": sorted(captured)},
            )

        if missing:
            # Multiple surfaces were captured including the front, so absence
            # here is a substantiated finding.
            return self.failed(
                f"{', '.join(missing)} was not found on any of the "
                f"{len(captured)} captured surfaces ({', '.join(sorted(captured))}), "
                "including the principal display panel.",
                field_name=missing[0],
                severity=MAJOR,
                calculated_value="Not found on any captured surface",
                expected_value="Declared on the principal display panel",
                discrepancy="Mandatory principal-panel declaration absent",
                suggested_fix=(
                    "Print the missing declaration on the principal display panel."
                ),
                penalty_amount=self.penalty_amount,
                metadata={"placement": placement, "surfaces": sorted(captured)},
            )

        coverage = len([n for n in ANY_PANEL_FIELDS if ctx.has(n)])

        if unlocated:
            # Present and correct as far as can be told; the panel simply was
            # not recorded against them. Reported, but never as a violation.
            return self.passed(
                f"All principal-panel declarations are present "
                f"({', '.join(PRINCIPAL_PANEL_FIELDS)}). The specific panel was not "
                f"recorded for {', '.join(unlocated)}, so Rule 9 placement could not "
                f"be confirmed. {len(captured)} surface"
                f"{'s' if len(captured) != 1 else ''} captured "
                f"({', '.join(sorted(captured))}); {coverage} further declarations located.",
                calculated_value=", ".join(sorted(captured)),
                metadata={
                    "placement": placement,
                    "surfaces": sorted(captured),
                    "placement_unconfirmed": unlocated,
                },
            )

        return self.passed(
            f"All principal-panel declarations appear on the front face. "
            f"{len(captured)} surface{'s' if len(captured) != 1 else ''} captured "
            f"({', '.join(sorted(captured))}); {coverage} further declarations located.",
            calculated_value=", ".join(sorted(captured)),
            metadata={"placement": placement, "surfaces": sorted(captured)},
        )
