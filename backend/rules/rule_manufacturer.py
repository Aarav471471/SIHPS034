"""Manufacturer identity and address -- spec rules/rule_manufacturer.py.

Rule 6(1)(a) requires the name and complete address of the manufacturer, packer
or importer.  The PIN code is the operative part: without it the address is not
"complete", and an address that cannot be resolved is an address at which no
notice can be served -- which defeats the entire enforcement chain.
"""
from __future__ import annotations

import re

from rules.base import (
    CRITICAL,
    MAJOR,
    MINOR,
    PINCODE_RE,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
)

# An importer's address is mandatory for imported goods under Rule 6(1)(a).
IMPORTER_MARKERS = ("imported by", "importer", "imported and marketed by")
MANUFACTURER_MARKERS = (
    "manufactured by", "mfd by", "mfg by", "packed by", "marketed by",
    "manufactured and packed by", "a unit of",
)

# Generic strings that are not an identifiable legal entity.
VAGUE_NAMES = {
    "manufacturer", "packer", "importer", "company", "brand owner",
    "n/a", "na", "unknown",
}


class ManufacturerNameRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-MANUFACTURER"
    rule_name = "Name of Manufacturer / Packer / Importer"
    legal_clause = "Rule 6(1)(a) - Packaged Commodities Rules, 2011"
    field_name = "manufacturer_name"
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("manufacturer_name")

        if raw is None:
            return self.failed(
                "The name of the manufacturer, packer or importer is not declared on "
                "any captured surface. Rule 6(1)(a) requires this declaration so that "
                "responsibility for the commodity is identifiable.",
                severity=CRITICAL,
                expected_value="Name of the manufacturing or packing entity",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix=(
                    "Print 'Manufactured by / Packed by <legal entity name>' on the pack."
                ),
                penalty_amount=self.penalty_amount,
            )

        cleaned = re.sub(
            r"^\s*(?:" + "|".join(MANUFACTURER_MARKERS + IMPORTER_MARKERS) + r")\s*:?\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()

        if not cleaned or cleaned.lower() in VAGUE_NAMES:
            return self.failed(
                f"The manufacturer declaration reads '{raw}', which does not identify "
                "a specific legal entity.",
                calculated_value=raw,
                expected_value="A named legal entity",
                discrepancy="Manufacturer is not identifiable",
                suggested_fix="Declare the full registered name of the responsible entity.",
            )

        if len(cleaned) < 3:
            return self.warned(
                f"The manufacturer name '{cleaned}' is implausibly short and may have "
                "been only partially captured.",
                severity=MINOR,
                calculated_value=cleaned,
                penalty_amount=None,
            )

        return self.passed(
            f"Manufacturer / packer declared as '{cleaned}'.",
            calculated_value=cleaned,
            metadata={"entity": cleaned},
        )


class ManufacturerAddressRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-PINCODE"
    rule_name = "Complete Address with PIN Code"
    legal_clause = "Rule 6(1)(a) - Packaged Commodities Rules, 2011"
    field_name = "manufacturer_address"
    severity = MINOR
    penalty_amount = 10_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("manufacturer_address")

        if raw is None:
            return self.failed(
                "No manufacturer address is declared on any captured surface. "
                "Rule 6(1)(a) requires the complete address of the manufacturer, "
                "packer or importer.",
                severity=MAJOR,
                expected_value="Complete address including six-digit PIN code",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix="Print the complete address including the PIN code.",
                penalty_amount=25_000.0,
            )

        pin_match = PINCODE_RE.search(raw)

        if not pin_match:
            return self.failed(
                f"The declared address '{raw}' does not contain a six-digit PIN code. "
                "An address without a PIN code is not a complete address for the "
                "purposes of Rule 6(1)(a), and a statutory notice cannot reliably be "
                "served on it.",
                severity=MINOR,
                calculated_value=raw,
                expected_value="Address ending in a six-digit PIN code",
                discrepancy="PIN code absent from the declared address",
                suggested_fix="Append the six-digit PIN code to the printed address.",
                penalty_amount=self.penalty_amount,
            )

        pin = pin_match.group(1)

        # An address that is only a PIN code is not an address.
        without_pin = raw.replace(pin, "").strip(" ,-")
        if len(without_pin) < 10:
            return self.warned(
                f"The address declaration '{raw}' contains a PIN code but little else, "
                "and may be incomplete.",
                severity=MINOR,
                calculated_value=raw,
                expected_value="Street, locality, city, state and PIN code",
                discrepancy="Address appears truncated",
                penalty_amount=None,
            )

        return self.passed(
            f"Complete manufacturer address declared, including PIN code {pin}.",
            calculated_value=raw,
            metadata={"pincode": pin},
        )
