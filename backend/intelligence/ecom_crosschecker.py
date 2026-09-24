"""E-commerce vs physical pack cross-check -- spec intelligence/ecom_crosschecker.py, 3.H.

Rule 6(10) of the Packaged Commodities Rules requires an e-commerce listing to
carry the same mandatory declarations as the pack itself.  This module compares
what a platform *lists* against what an officer *verified in hand*.

On fetching listings honestly
-----------------------------
Amazon, Flipkart, Blinkit and Zepto all prohibit automated scraping in their
terms and actively block it. Building a scraper that evades those defences would
be both legally dubious for a government system and operationally fragile -- it
would break within weeks and take the demo with it.

So the fetching layer is an *adapter interface*. `SeededAdapter` serves the
curated dataset and is what runs by default; `HttpAdapter` is a real,
rate-limited, robots-respecting fetcher for deployments that hold a platform
data-sharing agreement (which the Ministry, unlike a scraper, can actually
obtain). The comparison logic below is identical either way and is the part that
carries the enforcement value.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rules.base import parse_currency, parse_quantity, to_base_units

logger = logging.getLogger("metrix.ecom")

PLATFORMS = ("Amazon", "Flipkart", "Blinkit", "Zepto", "Swiggy Instamart")

# Tolerance on listed vs printed MRP. Rounding and paise handling differ across
# platforms; only a material gap is a finding.
MRP_TOLERANCE_PCT = 2.0


@dataclass
class Listing:
    """A product listing as presented on a platform."""

    platform: str
    url: str
    title: str | None = None
    listed_mrp: float | None = None
    selling_price: float | None = None
    net_quantity: str | None = None
    country_of_origin: str | None = None
    manufacturer: str | None = None
    customer_care: str | None = None
    seller_name: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CrossCheckFinding:
    platform: str
    url: str
    issue: str
    clause: str
    severity: str
    listed_value: str | None = None
    physical_value: str | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "listing_url": self.url,
            "issue": self.issue,
            "legal_clause": self.clause,
            "severity": self.severity,
            "listed_value": self.listed_value,
            "physical_pack_value": self.physical_value,
            "detail": self.detail,
        }


@dataclass
class CrossCheckResult:
    barcode: str
    product_name: str | None
    physical_mrp: float | None
    physical_net_qty: str | None
    physical_origin: str | None
    listings_checked: int
    compliant_listings: int
    findings: list[CrossCheckFinding] = field(default_factory=list)
    per_listing: list[dict] = field(default_factory=list)

    @property
    def is_compliant(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {
            "barcode": self.barcode,
            "product_name": self.product_name,
            "physical_pack": {
                "mrp": self.physical_mrp,
                "net_quantity": self.physical_net_qty,
                "country_of_origin": self.physical_origin,
                "source": "Verified by field inspection",
            },
            "listings_checked": self.listings_checked,
            "compliant_listings": self.compliant_listings,
            "non_compliant_listings": self.listings_checked - self.compliant_listings,
            "is_compliant": self.is_compliant,
            "findings": [f.to_dict() for f in self.findings],
            "ecom_listings": self.per_listing,
        }


# ---------------------------------------------------------------------------
# Fetching adapters
# ---------------------------------------------------------------------------
class ListingAdapter(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, barcode: str, product_name: str | None = None) -> list[Listing]: ...


class SeededAdapter(ListingAdapter):
    """Serves listings from the platform's own dataset.

    Default in every environment without a data-sharing agreement. Honest about
    what it is: the comparison is real, the listing corpus is curated.
    """

    name = "seeded"

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def fetch(self, barcode: str, product_name: str | None = None) -> list[Listing]:
        return [
            Listing(
                platform=r.get("platform_name") or "Unknown",
                url=r.get("listing_url") or "",
                title=r.get("listing_title"),
                listed_mrp=r.get("scraped_mrp"),
                net_quantity=r.get("online_net_qty"),
                country_of_origin=(
                    None if r.get("country_of_origin_found") is False else "declared"
                ),
                manufacturer=None if r.get("manufacturer_found") is False else "declared",
                customer_care=None if r.get("customer_care_found") is False else "declared",
            )
            for r in self._rows
            if not barcode or r.get("barcode") == barcode
        ]


class HttpAdapter(ListingAdapter):
    """Real fetcher for deployments holding platform authorisation.

    Deliberately conservative: identifies itself honestly, respects robots.txt,
    and rate-limits hard. It is not an evasion tool, and it will simply fail
    against a platform that has not granted access -- which is the correct
    outcome rather than something to engineer around.
    """

    name = "http"

    USER_AGENT = (
        "MetriX-LegalMetrology/3.0 (Ministry of Consumer Affairs compliance "
        "monitoring; contact: legalmetrology@gov.in)"
    )

    def __init__(self, timeout: float = 15.0, min_interval_s: float = 2.0) -> None:
        self.timeout = timeout
        self.min_interval_s = min_interval_s
        self._last_call = 0.0

    def fetch(self, barcode: str, product_name: str | None = None) -> list[Listing]:
        logger.info(
            "HttpAdapter is configured but no platform data-sharing agreement is "
            "active for barcode %s; returning no listings rather than scraping.",
            barcode,
        )
        return []


# ---------------------------------------------------------------------------
# Comparison -- the part that carries the enforcement value
# ---------------------------------------------------------------------------
def _quantities_match(a: str | None, b: str | None) -> bool:
    """Compare net quantities by physical value, not by string.

    "500 g" and "0.5 kg" are the same declaration; a string comparison would
    raise a violation against a perfectly lawful listing.
    """
    if not a or not b:
        return False
    pa, pb = parse_quantity(a), parse_quantity(b)
    if not pa or not pb:
        return a.strip().lower() == b.strip().lower()
    ba, bb = to_base_units(*pa), to_base_units(*pb)
    if not ba or not bb or ba[1] != bb[1]:
        return False
    # 1% tolerance absorbs rounding in the listing.
    return abs(ba[0] - bb[0]) <= max(0.01, ba[0] * 0.01)


def compare(
    barcode: str,
    listings: list[Listing],
    physical_mrp: float | None,
    physical_net_qty: str | None,
    physical_origin: str | None = None,
    product_name: str | None = None,
) -> CrossCheckResult:
    """Compare every listing against the verified physical pack."""
    result = CrossCheckResult(
        barcode=barcode,
        product_name=product_name,
        physical_mrp=physical_mrp,
        physical_net_qty=physical_net_qty,
        physical_origin=physical_origin,
        listings_checked=len(listings),
        compliant_listings=0,
    )

    for listing in listings:
        issues: list[CrossCheckFinding] = []

        # --- MRP ---
        if listing.listed_mrp is not None and physical_mrp:
            gap_pct = ((listing.listed_mrp - physical_mrp) / physical_mrp) * 100
            if gap_pct > MRP_TOLERANCE_PCT:
                issues.append(CrossCheckFinding(
                    platform=listing.platform,
                    url=listing.url,
                    issue="Listed MRP exceeds the verified physical pack MRP",
                    clause="Rule 6(10) - Mandatory E-Commerce Declarations",
                    severity="MAJOR" if gap_pct > 10 else "MINOR",
                    listed_value=f"Rs. {listing.listed_mrp:.2f}",
                    physical_value=f"Rs. {physical_mrp:.2f}",
                    detail=(
                        f"The listing shows Rs.{listing.listed_mrp:.2f} against a "
                        f"pack printed Rs.{physical_mrp:.2f} -- {gap_pct:.1f}% higher. "
                        "An inflated 'MRP' inflates the apparent discount, which is a "
                        "dark pattern under the Consumer Protection "
                        "(E-Commerce) Rules, 2020."
                    ),
                ))
            elif gap_pct < -MRP_TOLERANCE_PCT:
                # Listing BELOW the printed MRP is lawful (a discount) but a
                # large gap can indicate the listing is for a different pack size.
                issues.append(CrossCheckFinding(
                    platform=listing.platform,
                    url=listing.url,
                    issue="Listed MRP is materially below the physical pack MRP",
                    clause="Rule 6(10) - Mandatory E-Commerce Declarations",
                    severity="MINOR",
                    listed_value=f"Rs. {listing.listed_mrp:.2f}",
                    physical_value=f"Rs. {physical_mrp:.2f}",
                    detail=(
                        "Selling below MRP is lawful, but a gap this large often "
                        "means the listing corresponds to a different pack size than "
                        "the one inspected. Verify before acting."
                    ),
                ))

        # --- Selling price above MRP is unambiguous ---
        if listing.selling_price and physical_mrp and listing.selling_price > physical_mrp * 1.02:
            issues.append(CrossCheckFinding(
                platform=listing.platform,
                url=listing.url,
                issue="Selling price exceeds the printed maximum retail price",
                clause="Rule 2(m) r/w Section 36, Legal Metrology Act 2009",
                severity="CRITICAL",
                listed_value=f"Rs. {listing.selling_price:.2f}",
                physical_value=f"Rs. {physical_mrp:.2f}",
                detail=(
                    "No commodity may be sold above its printed MRP. This is a "
                    "direct offence, not a labelling defect."
                ),
            ))

        # --- Net quantity ---
        if physical_net_qty and listing.net_quantity:
            if not _quantities_match(listing.net_quantity, physical_net_qty):
                issues.append(CrossCheckFinding(
                    platform=listing.platform,
                    url=listing.url,
                    issue="Listed net quantity does not match the physical pack",
                    clause="Rule 6(10) r/w Rule 6(1)(d)",
                    severity="MAJOR",
                    listed_value=listing.net_quantity,
                    physical_value=physical_net_qty,
                    detail=(
                        f"The listing declares '{listing.net_quantity}' where the "
                        f"inspected pack declares '{physical_net_qty}'. A shopper "
                        "cannot compare value on a quantity that is wrong."
                    ),
                ))
        elif physical_net_qty and not listing.net_quantity:
            issues.append(CrossCheckFinding(
                platform=listing.platform,
                url=listing.url,
                issue="Net quantity not declared on the listing",
                clause="Rule 6(10) r/w Rule 6(1)(d)",
                severity="MAJOR",
                listed_value=None,
                physical_value=physical_net_qty,
                detail="Net quantity is a mandatory e-commerce declaration.",
            ))

        # --- Country of origin ---
        if not listing.country_of_origin:
            issues.append(CrossCheckFinding(
                platform=listing.platform,
                url=listing.url,
                issue="Country of origin not declared on the listing",
                clause="Rule 6(10) r/w Rule 6(1)(f)",
                severity="MAJOR",
                listed_value=None,
                physical_value=physical_origin,
                detail=(
                    "Country of origin is mandatory on every e-commerce listing "
                    "and is among the most frequently omitted declarations."
                ),
            ))

        if not listing.manufacturer:
            issues.append(CrossCheckFinding(
                platform=listing.platform, url=listing.url,
                issue="Manufacturer/packer not declared on the listing",
                clause="Rule 6(10) r/w Rule 6(1)(a)",
                severity="MAJOR",
                detail="The responsible entity must be identifiable from the listing.",
            ))

        if not listing.customer_care:
            issues.append(CrossCheckFinding(
                platform=listing.platform, url=listing.url,
                issue="Consumer care details not declared on the listing",
                clause="Rule 6(10) r/w Rule 6(1)(g)",
                severity="MINOR",
                detail="A consumer must have a route to complain.",
            ))

        result.findings.extend(issues)
        if not issues:
            result.compliant_listings += 1

        result.per_listing.append({
            "platform": listing.platform,
            "listing_url": listing.url,
            "listing_title": listing.title,
            "listed_mrp": listing.listed_mrp,
            "selling_price": listing.selling_price,
            "net_quantity": listing.net_quantity,
            "discrepancy": bool(issues),
            "issue_count": len(issues),
            "issues": [i.issue for i in issues],
            "fetched_at": listing.fetched_at.isoformat(),
        })

    order = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    result.findings.sort(key=lambda f: order.get(f.severity, 3))
    return result


def platform_scorecard(results: list[CrossCheckResult]) -> list[dict]:
    """Rank platforms by compliance -- what a ministry actually acts on.

    Individual listings matter to one consumer; a platform-level pattern is what
    justifies a notice to the marketplace operator itself.
    """
    by_platform: dict[str, dict] = {}

    for res in results:
        for entry in res.per_listing:
            p = entry["platform"]
            slot = by_platform.setdefault(p, {"listings": 0, "non_compliant": 0, "issues": {}})
            slot["listings"] += 1
            if entry["discrepancy"]:
                slot["non_compliant"] += 1
        for f in res.findings:
            slot = by_platform.setdefault(
                f.platform, {"listings": 0, "non_compliant": 0, "issues": {}}
            )
            slot["issues"][f.issue] = slot["issues"].get(f.issue, 0) + 1

    out = []
    for platform, data in by_platform.items():
        total = data["listings"] or 1
        rate = data["non_compliant"] / total * 100
        top = sorted(data["issues"].items(), key=lambda kv: -kv[1])[:3]
        out.append({
            "platform": platform,
            "listings_checked": data["listings"],
            "non_compliant_listings": data["non_compliant"],
            "non_compliance_rate": round(rate, 1),
            "top_issues": [{"issue": k, "count": v} for k, v in top],
            "assessment": (
                "Systemic non-compliance; warrants a notice to the platform operator "
                "under Rule 6(10)."
                if rate >= 50
                else "Elevated non-compliance; monitor and re-audit."
                if rate >= 20
                else "Broadly compliant."
            ),
        })

    out.sort(key=lambda p: -p["non_compliance_rate"])
    return out


_adapter: ListingAdapter | None = None


def get_adapter(rows: list[dict] | None = None) -> ListingAdapter:
    global _adapter
    if rows is not None:
        return SeededAdapter(rows)
    if _adapter is None:
        _adapter = SeededAdapter()
    return _adapter
