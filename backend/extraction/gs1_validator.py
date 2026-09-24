"""GS1 / EAN validation and FSSAI licence checks -- spec extraction/gs1_validator.py.

Two independent identity checks that need no network and no third-party API:

  * GS1 check digits.  EAN-13, EAN-8, UPC-A and GTIN-14 all carry a modulo-10
    check digit. Verifying it locally catches misread and fabricated barcodes
    before they are ever used to look up a product.

  * FSSAI licence structure.  A licence number is 14 digits with a defined
    layout; format alone rules out a large share of invalid declarations.

The spec also names the GS1 DataKart and FSSAI registries. Those are commercial
and non-public respectively, so lookup goes through a swappable client
interface: structural validation is real and always runs, while registry
confirmation runs against a seeded dataset until credentials exist.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("metrix.gs1")

# GS1 prefixes relevant to Indian enforcement
GS1_PREFIXES: dict[str, str] = {
    "890": "India",
    "690": "China", "691": "China", "692": "China", "693": "China",
    "694": "China", "695": "China", "696": "China", "697": "China",
    "00": "USA / Canada", "01": "USA / Canada", "03": "USA / Canada",
    "50": "United Kingdom", "45": "Japan", "49": "Japan",
    "88": "Singapore", "94": "New Zealand", "93": "Australia",
    "471": "Taiwan", "489": "Hong Kong", "955": "Malaysia",
    "628": "Saudi Arabia", "729": "Israel", "769": "Switzerland",
    "80": "Italy", "84": "Spain", "40": "Germany", "30": "France",
}


@dataclass
class EANValidation:
    code: str | None
    normalised: str | None
    length: int
    symbology: str | None
    checksum_valid: bool | None
    expected_check_digit: str | None
    gs1_prefix: str | None
    issuing_country: str | None
    is_indian: bool
    note: str


def _gs1_check_digit(digits: str) -> str:
    """Modulo-10 check digit over the payload (check digit excluded).

    Weights alternate 3 and 1 from the RIGHTMOST payload digit leftwards. Fixing
    the weighting to position-from-the-left instead breaks for odd-length codes,
    which is why this is computed on the reversed string.
    """
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return str((10 - total % 10) % 10)


SYMBOLOGY_BY_LENGTH = {8: "EAN-8", 12: "UPC-A", 13: "EAN-13", 14: "GTIN-14"}


def validate_ean(code: str | None) -> EANValidation:
    """Structural + check-digit validation of a GS1 article number."""
    if not code:
        return EANValidation(
            code=None, normalised=None, length=0, symbology=None,
            checksum_valid=None, expected_check_digit=None, gs1_prefix=None,
            issuing_country=None, is_indian=False, note="No barcode supplied",
        )

    digits = re.sub(r"\D", "", str(code))
    length = len(digits)

    if length not in SYMBOLOGY_BY_LENGTH:
        return EANValidation(
            code=str(code), normalised=digits or None, length=length, symbology=None,
            checksum_valid=None, expected_check_digit=None, gs1_prefix=None,
            issuing_country=None, is_indian=False,
            note=(
                f"{length} digits is not a valid GS1 article number length "
                "(expected 8, 12, 13 or 14)"
            ),
        )

    payload, actual = digits[:-1], digits[-1]
    expected = _gs1_check_digit(payload)
    valid = expected == actual

    prefix, country = None, None
    if length in (13, 14):
        base = digits[1:] if length == 14 else digits
        for size in (3, 2):
            candidate = base[:size]
            if candidate in GS1_PREFIXES:
                prefix, country = candidate, GS1_PREFIXES[candidate]
                break
        if prefix is None:
            prefix = base[:3]

    return EANValidation(
        code=str(code),
        normalised=digits,
        length=length,
        symbology=SYMBOLOGY_BY_LENGTH[length],
        checksum_valid=valid,
        expected_check_digit=expected,
        gs1_prefix=prefix,
        issuing_country=country,
        is_indian=prefix == "890",
        note=(
            f"Valid {SYMBOLOGY_BY_LENGTH[length]} check digit"
            + (f"; GS1 prefix {prefix} ({country})" if country else "")
            if valid
            else (
                f"Check digit mismatch: barcode ends in {actual}, "
                f"but the preceding digits require {expected}"
            )
        ),
    )


# ---------------------------------------------------------------------------
# FSSAI licence
# ---------------------------------------------------------------------------
@dataclass
class FSSAIValidation:
    number: str | None
    is_valid_format: bool
    licence_type: str | None
    state_code: str | None
    state_name: str | None
    year: str | None
    note: str


# Digits 2-3 of an FSSAI licence encode the issuing authority/state.
# "00" is used by the Central Licensing Authority, which issues a large share of
# the licences that appear on nationally distributed packaged commodities.
FSSAI_STATE_CODES: dict[str, str] = {
    "00": "Central Licensing Authority",
    "10": "Central Licensing Authority", "11": "Andhra Pradesh",
    "12": "Arunachal Pradesh", "13": "Assam", "14": "Bihar",
    "15": "Chhattisgarh", "16": "Goa", "17": "Gujarat", "18": "Haryana",
    "19": "Himachal Pradesh", "20": "Jammu & Kashmir", "21": "Jharkhand",
    "22": "Karnataka", "23": "Kerala", "24": "Madhya Pradesh",
    "25": "Maharashtra", "26": "Manipur", "27": "Meghalaya", "28": "Mizoram",
    "29": "Nagaland", "30": "Odisha", "31": "Punjab", "32": "Rajasthan",
    "33": "Sikkim", "34": "Tamil Nadu", "35": "Telangana", "36": "Tripura",
    "37": "Uttar Pradesh", "38": "Uttarakhand", "39": "West Bengal",
    "40": "Delhi", "41": "Puducherry", "42": "Chandigarh",
    "43": "Andaman & Nicobar", "44": "Dadra & Nagar Haveli", "45": "Daman & Diu",
    "46": "Lakshadweep", "47": "Ladakh",
}

LICENCE_TYPE = {"1": "Central Licence", "2": "State Licence"}


def validate_fssai(number: str | None) -> FSSAIValidation:
    """Structural validation of a 14-digit FSSAI licence number.

    Layout: [1 licence type][2 state code][2 year][2 authority][7 serial].
    This proves the number is well-formed, not that the licence is live --
    currency is confirmed against the registry by the inter-agency graph.
    """
    if not number:
        return FSSAIValidation(
            number=None, is_valid_format=False, licence_type=None,
            state_code=None, state_name=None, year=None,
            note="No FSSAI licence number declared",
        )

    digits = re.sub(r"\D", "", str(number))
    if len(digits) != 14:
        return FSSAIValidation(
            number=str(number), is_valid_format=False, licence_type=None,
            state_code=None, state_name=None, year=None,
            note=(
                f"FSSAI licence must be exactly 14 digits; {len(digits)} found"
            ),
        )

    lic_type = digits[0]
    state_code = digits[1:3]
    year = digits[3:5]

    # Only structural facts that are certain are treated as format failures.
    # The published state-code list is not authoritative enough to justify
    # calling a licence malformed purely because a code is unfamiliar -- that
    # would put an unfounded assertion into an enforcement notice. An unknown
    # code is reported as unverified instead, and currency is confirmed against
    # the registry by the inter-agency graph.
    if lic_type not in LICENCE_TYPE:
        return FSSAIValidation(
            number=digits, is_valid_format=False, licence_type=None,
            state_code=state_code, state_name=None,
            year=f"20{year}" if year.isdigit() else None,
            note=(
                f"Malformed FSSAI licence: first digit must be 1 (Central) or "
                f"2 (State), found '{lic_type}'"
            ),
        )

    state_name = FSSAI_STATE_CODES.get(state_code)
    return FSSAIValidation(
        number=digits,
        is_valid_format=True,
        licence_type=LICENCE_TYPE[lic_type],
        state_code=state_code,
        state_name=state_name,
        year=f"20{year}" if year.isdigit() else None,
        note=(
            f"Well-formed {LICENCE_TYPE[lic_type]} issued by {state_name}"
            if state_name
            else (
                f"Well-formed {LICENCE_TYPE[lic_type]}; issuing-authority code "
                f"'{state_code}' not in the local reference list and was not verified"
            )
        ),
    )


# ---------------------------------------------------------------------------
# Registry lookup (swappable)
# ---------------------------------------------------------------------------
@dataclass
class RegistryRecord:
    barcode: str
    found: bool
    brand_name: str | None = None
    product_name: str | None = None
    net_quantity: str | None = None
    declared_mrp: float | None = None
    source: str = "local"


class GS1RegistryClient:
    """Product-identity lookup.

    GS1 DataKart is a paid subscription service, so no public endpoint exists to
    call. The interface is real and the local catalogue is authoritative for
    this deployment; swapping in a DataKart HTTP client later changes only this
    class.
    """

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    async def lookup(self, barcode: str) -> RegistryRecord:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from models.product import Product

        factory = self._session_factory or AsyncSessionLocal
        async with factory() as db:
            product = (
                await db.execute(select(Product).where(Product.barcode == barcode))
            ).scalar_one_or_none()

        if product is None:
            return RegistryRecord(barcode=barcode, found=False)
        return RegistryRecord(
            barcode=barcode,
            found=True,
            brand_name=product.brand_name,
            product_name=product.product_name,
            net_quantity=product.net_quantity,
            declared_mrp=product.official_mrp,
            source="metrix-catalogue",
        )


registry_client = GS1RegistryClient()
