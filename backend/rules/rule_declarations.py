"""Country of origin and consumer care -- spec rules/rule_declarations.py.

Rule 6(1)(f) requires the country of origin, and Rule 6(1)(g) requires consumer
care contact details.

Country of origin is the sharper of the two.  It is mandatory on every imported
commodity, and its omission is the standard way an importer obscures provenance
that a shopper might otherwise weigh -- so the rule treats a known-imported pack
without it far more seriously than a domestic pack that merely omits the line.
"""
from __future__ import annotations

import re

from rules.base import (
    EMAIL_RE,
    MAJOR,
    MINOR,
    PHONE_RE,
    BaseRule,
    RuleContext,
    RuleResult,
    _AlwaysRunnable,
)

INDIA_TERMS = ("india", "bharat", "made in india", "product of india")

# Set when the barcode's GS1 prefix or the extracted text indicates import.
FOREIGN_HINTS = (
    "china", "usa", "united states", "germany", "france", "italy", "spain",
    "japan", "korea", "thailand", "vietnam", "malaysia", "singapore",
    "indonesia", "netherlands", "belgium", "switzerland", "uk",
    "united kingdom", "australia", "new zealand", "brazil", "iran", "turkey",
    "uae", "saudi", "nepal", "sri lanka", "bangladesh",
)


class CountryOfOriginRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-COUNTRY-ORIGIN"
    rule_name = "Country of Origin Declaration"
    legal_clause = "Rule 6(1)(f) - Packaged Commodities Rules, 2011"
    field_name = "country_of_origin"
    severity = MAJOR
    penalty_amount = 25_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("country_of_origin")

        # The barcode's GS1 prefix is independent evidence of provenance and
        # does not depend on the pack admitting anything.
        gs1_country = (ctx.metadata or {}).get("gs1_country")
        gs1_is_foreign = bool(gs1_country) and "india" not in str(gs1_country).lower()

        if raw is None:
            if gs1_is_foreign:
                return self.failed(
                    "No country of origin is declared, although the article's GS1 "
                    f"prefix indicates it was issued in {gs1_country}. Rule 6(1)(f) "
                    "requires the country of origin on every imported commodity.",
                    severity=MAJOR,
                    calculated_value="Not declared",
                    expected_value=f"Country of Origin: {gs1_country}",
                    discrepancy="Origin omitted on an apparently imported commodity",
                    suggested_fix="Declare the country of origin on the label.",
                    penalty_amount=self.penalty_amount,
                    metadata={"gs1_country": gs1_country},
                )
            return self.failed(
                "No country of origin is declared on any captured surface. "
                "Rule 6(1)(f) requires this declaration.",
                calculated_value="Not declared",
                expected_value="Country of Origin: <country>",
                discrepancy="Mandatory declaration absent",
                suggested_fix="Print 'Country of Origin: India' or the country of import.",
                penalty_amount=self.penalty_amount,
            )

        cleaned = re.sub(
            r"^\s*(?:country of origin|origin|made in|product of)\s*:?\s*",
            "", raw, flags=re.IGNORECASE,
        ).strip(" .,-")

        if not cleaned:
            return self.failed(
                f"The country of origin declaration reads '{raw}' but names no country.",
                calculated_value=raw,
                expected_value="A named country",
                discrepancy="Origin declared but not specified",
            )

        lowered = cleaned.lower()
        declared_india = any(t in lowered for t in INDIA_TERMS)

        # A pack declaring India while carrying a foreign GS1 prefix is a
        # substantive contradiction, not a formatting issue.
        if declared_india and gs1_is_foreign:
            return self.warned(
                f"The pack declares '{cleaned}' as the country of origin, but the "
                f"article's GS1 prefix was issued in {gs1_country}. The two are "
                "inconsistent and the declaration should be substantiated.",
                severity=MAJOR,
                calculated_value=cleaned,
                expected_value=f"Consistent with the GS1 prefix ({gs1_country})",
                discrepancy="Declared origin conflicts with the barcode prefix",
                suggested_fix=(
                    "Verify the country of origin against import documentation. A GS1 "
                    "prefix reflects where the number was issued, which is strong but "
                    "not conclusive evidence of manufacture."
                ),
                penalty_amount=None,
                metadata={"declared": cleaned, "gs1_country": gs1_country},
            )

        return self.passed(
            f"Country of origin declared as '{cleaned}'.",
            calculated_value=cleaned,
            metadata={"country": cleaned, "is_india": declared_india},
        )


class CustomerCareRule(BaseRule, _AlwaysRunnable):
    rule_id = "R-CUSTOMER-CARE"
    rule_name = "Consumer Care Details"
    legal_clause = "Rule 6(1)(g) - Packaged Commodities Rules, 2011"
    field_name = "customer_care"
    severity = MINOR
    penalty_amount = 10_000.0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        raw = ctx.get("customer_care")

        if raw is None:
            return self.failed(
                "No consumer care details are declared on any captured surface. "
                "Rule 6(1)(g) requires the name, address, telephone number or email "
                "of the person who can be contacted with a consumer complaint.",
                severity=MINOR,
                expected_value="A consumer care telephone number and/or email address",
                calculated_value="Not declared",
                discrepancy="Mandatory declaration absent",
                suggested_fix=(
                    "Print a consumer care telephone number and email address on the pack."
                ),
                penalty_amount=self.penalty_amount,
            )

        phone = PHONE_RE.search(raw)
        email = EMAIL_RE.search(raw)

        if not phone and not email:
            return self.failed(
                f"The consumer care declaration reads '{raw}' but contains neither a "
                "usable telephone number nor an email address, so a consumer has no "
                "means of making a complaint.",
                severity=MINOR,
                calculated_value=raw,
                expected_value="A contactable telephone number or email address",
                discrepancy="No usable contact channel in the declaration",
                suggested_fix="Include a working telephone number or email address.",
                penalty_amount=self.penalty_amount,
            )

        channels = []
        if phone:
            channels.append(f"telephone {phone.group(0)}")
        if email:
            channels.append(f"email {email.group(0)}")

        return self.passed(
            "Consumer care contact declared: " + " and ".join(channels) + ".",
            calculated_value=raw,
            metadata={
                "phone": phone.group(0) if phone else None,
                "email": email.group(0) if email else None,
            },
        )
