"""Price-Gouging & MRP-Tampering Radar -- spec intelligence/price_gouging_radar.py.

Every consumer and officer scan appends `(barcode, printed_mrp, gps, timestamp)`.
The radar turns that stream into enforcement leads.

The spec's rule is "flag when printed_mrp > modal_mrp x 1.05". Implemented
naively that produces mostly noise, because the inputs are hostile:

  * OCR misreads a digit, so a handful of scans are wildly wrong;
  * a genuine nationwide price revision shifts the true MRP mid-window;
  * two different pack sizes can share a barcode prefix in bad catalogue data;
  * a single scan of a store proves nothing.

So the modal price is computed with **robust statistics** (MAD-based outlier
rejection before the mode), a flag requires **corroboration** across
independent scans, a **legitimate revision** is distinguished from tampering by
looking at whether the whole market moved or just one retailer, and confirmed
hotspots are **clustered geographically** so an officer is sent to an area
rather than a pin.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import settings
from core.geofence import haversine_km

logger = logging.getLogger("metrix.radar")

# A scan whose price is more than this many MADs from the median is treated as
# a misread rather than evidence, and excluded before the mode is taken.
MAD_OUTLIER_THRESHOLD = 3.5
# Below this many usable scans there is no defensible "standard" price.
MIN_SAMPLES_FOR_MODE = 3
# Prices are bucketed to the rupee before taking the mode: printed MRPs are
# round numbers, and exact-float matching would find no mode at all.
PRICE_BUCKET = 1.0
# A retailer needs this many overcharging scans before it becomes a lead.
MIN_SCANS_PER_STORE = 2
# Stores within this radius are treated as one hotspot for patrol purposes.
HOTSPOT_RADIUS_KM = 1.5


@dataclass
class PriceStats:
    """Robust summary of what a commodity actually sells for."""

    barcode: str
    modal_mrp: float | None
    median_mrp: float | None
    mad: float
    sample_count: int
    usable_count: int
    outliers_rejected: int
    price_spread: float
    confidence: float           # 0-1: how much to trust this as the standard
    is_stable: bool
    note: str = ""


@dataclass
class GougingFinding:
    barcode: str
    product_name: str | None
    brand_name: str | None
    store_name: str
    latitude: float | None
    longitude: float | None
    modal_mrp: float
    observed_mrp: float
    overcharge_amount: float
    overcharge_pct: float
    scan_count: int
    distinct_reporters: int
    first_seen: datetime
    last_seen: datetime
    confidence: float
    severity: str               # WATCH | LEAD | PRIORITY
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "barcode": self.barcode,
            "product_name": self.product_name,
            "brand_name": self.brand_name,
            "store_name": self.store_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "modal_mrp": round(self.modal_mrp, 2),
            "observed_mrp": round(self.observed_mrp, 2),
            "overcharge_amount": round(self.overcharge_amount, 2),
            "overcharge_pct": round(self.overcharge_pct, 1),
            "scan_count": self.scan_count,
            "distinct_reporters": self.distinct_reporters,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "confidence": round(self.confidence, 3),
            "severity": self.severity,
            "reasons": self.reasons,
        }


@dataclass
class Hotspot:
    centre_lat: float
    centre_lng: float
    store_names: list[str]
    findings: list[GougingFinding]
    total_overcharge: float
    severity: str
    radius_km: float = HOTSPOT_RADIUS_KM

    def to_dict(self) -> dict:
        return {
            "centre": {"latitude": round(self.centre_lat, 6),
                       "longitude": round(self.centre_lng, 6)},
            "radius_km": self.radius_km,
            "stores": self.store_names,
            "finding_count": len(self.findings),
            "distinct_products": len({f.barcode for f in self.findings}),
            "total_overcharge_per_unit": round(self.total_overcharge, 2),
            "severity": self.severity,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Robust statistics
# ---------------------------------------------------------------------------
def _mad(values: list[float], median: float) -> float:
    """Median absolute deviation -- a spread measure outliers cannot inflate.

    Standard deviation is unusable here: one OCR misread of 45 as 4500 would
    inflate it enough to hide every real overcharge in the window.
    """
    if not values:
        return 0.0
    return statistics.median([abs(v - median) for v in values])


def compute_price_stats(prices: list[float], barcode: str = "") -> PriceStats:
    """Derive the defensible 'standard' MRP for a commodity."""
    total = len(prices)
    clean = [p for p in prices if p and p > 0]

    if len(clean) < MIN_SAMPLES_FOR_MODE:
        return PriceStats(
            barcode=barcode, modal_mrp=None, median_mrp=None, mad=0.0,
            sample_count=total, usable_count=len(clean), outliers_rejected=0,
            price_spread=0.0, confidence=0.0, is_stable=False,
            note=(
                f"Only {len(clean)} scan(s) in the window; at least "
                f"{MIN_SAMPLES_FOR_MODE} are needed to establish a standard price."
            ),
        )

    median = statistics.median(clean)
    mad = _mad(clean, median)

    # Reject misreads. The 0.6745 factor makes MAD comparable to a standard
    # deviation for normally distributed data.
    if mad > 0:
        kept = [
            p for p in clean
            if abs(p - median) / (mad / 0.6745) <= MAD_OUTLIER_THRESHOLD
        ]
    else:
        # Zero MAD means most scans agree exactly; anything far off is a misread.
        kept = [p for p in clean if abs(p - median) <= max(1.0, median * 0.25)]

    if len(kept) < MIN_SAMPLES_FOR_MODE:
        kept = clean

    rejected = len(clean) - len(kept)

    # Mode over rupee buckets. Printed MRPs are round numbers, so the mode is
    # far more meaningful than the mean, which a few gouging scans would drag up.
    buckets = Counter(round(p / PRICE_BUCKET) * PRICE_BUCKET for p in kept)
    modal_bucket, modal_freq = buckets.most_common(1)[0]

    # Refine to the mean of scans inside the winning bucket, so 45.00 does not
    # become 45 when the true price is 44.50.
    in_bucket = [p for p in kept if abs(p - modal_bucket) < PRICE_BUCKET]
    modal = statistics.mean(in_bucket) if in_bucket else float(modal_bucket)

    spread = (max(kept) - min(kept)) if kept else 0.0
    agreement = modal_freq / len(kept)

    # Confidence rises with sample size and with how strongly scans agree.
    volume_factor = min(1.0, len(kept) / 12.0)
    confidence = round(0.35 * volume_factor + 0.65 * agreement, 3)
    stable = agreement >= 0.5 and len(kept) >= 5

    return PriceStats(
        barcode=barcode,
        modal_mrp=round(modal, 2),
        median_mrp=round(statistics.median(kept), 2),
        mad=round(mad, 3),
        sample_count=total,
        usable_count=len(kept),
        outliers_rejected=rejected,
        price_spread=round(spread, 2),
        confidence=confidence,
        is_stable=stable,
        note=(
            f"{modal_freq} of {len(kept)} usable scans agree on Rs.{modal:.2f}"
            + (f"; {rejected} outlier(s) rejected as probable misreads" if rejected else "")
        ),
    )


def detect_market_wide_revision(
    scans_by_time: list[tuple[datetime, float, str]],
    modal_mrp: float,
) -> tuple[bool, str | None]:
    """Distinguish a lawful price revision from retailer tampering.

    When a manufacturer raises an MRP, the increase appears at *many* retailers
    at roughly the same time. When a shopkeeper over-stickers, it appears at one.
    Without this test every nationwide price revision would generate a flood of
    false enforcement leads and destroy the officer's trust in the system.
    """
    if len(scans_by_time) < 8:
        return False, None

    ordered = sorted(scans_by_time, key=lambda s: s[0])
    midpoint = len(ordered) // 2
    early, late = ordered[:midpoint], ordered[midpoint:]

    early_prices = [p for _t, p, _s in early]
    late_prices = [p for _t, p, _s in late]
    if not early_prices or not late_prices:
        return False, None

    early_med = statistics.median(early_prices)
    late_med = statistics.median(late_prices)
    if early_med <= 0:
        return False, None

    shift = (late_med - early_med) / early_med
    if shift < 0.03:
        return False, None

    # How broad is the shift? Count retailers whose later scans sit above the
    # earlier median.
    late_stores = {s for _t, p, s in late if p > early_med * 1.02}
    all_late_stores = {s for _t, _p, s in late}
    if not all_late_stores:
        return False, None

    breadth = len(late_stores) / len(all_late_stores)

    if breadth >= 0.6 and len(all_late_stores) >= 3:
        return True, (
            f"Prices rose {shift * 100:.1f}% across {len(late_stores)} of "
            f"{len(all_late_stores)} retailers in the second half of the window. "
            "This is consistent with a manufacturer price revision rather than "
            "retailer tampering, and is not raised as an enforcement lead."
        )
    return False, None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def analyse_barcode(
    barcode: str,
    scans: list[dict],
    product_name: str | None = None,
    brand_name: str | None = None,
    threshold: float | None = None,
) -> tuple[PriceStats, list[GougingFinding], str | None]:
    """Find retailers charging above the established MRP for one commodity.

    `scans` items need: scanned_mrp, store_name, latitude, longitude,
    scanned_at, scanned_by_user_id.
    """
    multiplier = threshold or settings.RADAR_TAMPER_MULTIPLIER

    # Normalise timestamps on entry: SQLite hands back naive datetimes and
    # PostgreSQL aware ones, and mixing them raises on the first comparison.
    from models.base import as_utc

    scans = [{**s, "scanned_at": as_utc(s.get("scanned_at"))} for s in scans]

    prices = [float(s["scanned_mrp"]) for s in scans if s.get("scanned_mrp")]
    stats = compute_price_stats(prices, barcode)

    if stats.modal_mrp is None:
        return stats, [], None

    # Rule out a lawful market-wide revision before accusing anyone.
    timeline = [
        (s["scanned_at"], float(s["scanned_mrp"]), s.get("store_name") or "unknown")
        for s in scans
        if s.get("scanned_mrp") and s.get("scanned_at")
    ]
    revised, revision_note = detect_market_wide_revision(timeline, stats.modal_mrp)
    if revised:
        return stats, [], revision_note

    ceiling = stats.modal_mrp * multiplier

    by_store: dict[str, list[dict]] = defaultdict(list)
    for s in scans:
        price = s.get("scanned_mrp")
        if price and float(price) > ceiling:
            by_store[s.get("store_name") or "Unnamed retailer"].append(s)

    findings: list[GougingFinding] = []
    for store, offending in by_store.items():
        reporters = {s.get("scanned_by_user_id") for s in offending if s.get("scanned_by_user_id")}
        observed = statistics.median([float(s["scanned_mrp"]) for s in offending])
        times = sorted(s["scanned_at"] for s in offending if s.get("scanned_at"))
        lats = [s["latitude"] for s in offending if s.get("latitude") is not None]
        lngs = [s["longitude"] for s in offending if s.get("longitude") is not None]

        over_amount = observed - stats.modal_mrp
        over_pct = (over_amount / stats.modal_mrp) * 100

        reasons = [
            f"Standard MRP is Rs.{stats.modal_mrp:.2f} "
            f"({stats.usable_count} corroborating scans); this retailer is "
            f"charging Rs.{observed:.2f}, {over_pct:.1f}% above it."
        ]

        # Corroboration determines how seriously to take it. A single scan from
        # a single person is a watch item, not an accusation.
        if len(offending) >= MIN_SCANS_PER_STORE and len(reporters) >= 2:
            severity = "PRIORITY"
            reasons.append(
                f"Corroborated by {len(reporters)} independent reporters across "
                f"{len(offending)} scans."
            )
        elif len(offending) >= MIN_SCANS_PER_STORE:
            severity = "LEAD"
            reasons.append(f"Observed {len(offending)} times at this retailer.")
        else:
            severity = "WATCH"
            reasons.append(
                "Single observation only; requires corroboration before a "
                "field visit is warranted."
            )

        if over_pct >= 25:
            reasons.append("Overcharge exceeds 25% -- consistent with MRP over-stickering.")
            if severity == "LEAD":
                severity = "PRIORITY"

        # Finding confidence combines how sure we are of the baseline with how
        # well corroborated the observation is.
        corroboration = min(1.0, (len(offending) + len(reporters)) / 6.0)
        confidence = round(stats.confidence * 0.6 + corroboration * 0.4, 3)

        findings.append(GougingFinding(
            barcode=barcode,
            product_name=product_name,
            brand_name=brand_name,
            store_name=store,
            latitude=statistics.mean(lats) if lats else None,
            longitude=statistics.mean(lngs) if lngs else None,
            modal_mrp=stats.modal_mrp,
            observed_mrp=observed,
            overcharge_amount=over_amount,
            overcharge_pct=over_pct,
            scan_count=len(offending),
            distinct_reporters=len(reporters),
            first_seen=times[0] if times else datetime.now(timezone.utc),
            last_seen=times[-1] if times else datetime.now(timezone.utc),
            confidence=confidence,
            severity=severity,
            reasons=reasons,
        ))

    findings.sort(key=lambda f: (-f.confidence, -f.overcharge_pct))
    return stats, findings, None


def cluster_hotspots(
    findings: list[GougingFinding], radius_km: float = HOTSPOT_RADIUS_KM
) -> list[Hotspot]:
    """Group nearby findings so patrols target areas, not individual pins.

    Single-link agglomeration on great-circle distance. A market with six
    offending shops is one visit, not six, and presenting it as six wastes the
    officer's day.
    """
    located = [f for f in findings if f.latitude is not None and f.longitude is not None]
    if not located:
        return []

    clusters: list[list[GougingFinding]] = []
    for finding in located:
        placed = False
        for cluster in clusters:
            if any(
                haversine_km(finding.latitude, finding.longitude, o.latitude, o.longitude)
                <= radius_km
                for o in cluster
            ):
                cluster.append(finding)
                placed = True
                break
        if not placed:
            clusters.append([finding])

    order = {"PRIORITY": 0, "LEAD": 1, "WATCH": 2}
    hotspots = []
    for cluster in clusters:
        lat = statistics.mean(f.latitude for f in cluster)
        lng = statistics.mean(f.longitude for f in cluster)
        severity = min((f.severity for f in cluster), key=lambda s: order.get(s, 3))
        # A cluster of several independent findings is worse than any one of them.
        if len(cluster) >= 3 and severity == "LEAD":
            severity = "PRIORITY"

        hotspots.append(Hotspot(
            centre_lat=lat,
            centre_lng=lng,
            store_names=sorted({f.store_name for f in cluster}),
            findings=sorted(cluster, key=lambda f: -f.overcharge_pct),
            total_overcharge=sum(f.overcharge_amount for f in cluster),
            severity=severity,
            radius_km=radius_km,
        ))

    hotspots.sort(key=lambda h: (order.get(h.severity, 3), -len(h.findings)))
    return hotspots


# ---------------------------------------------------------------------------
# Consumer-facing check -- the "Scan Before You Buy" warning
# ---------------------------------------------------------------------------
@dataclass
class ScanVerdict:
    is_gouged: bool
    severity: str | None
    modal_mrp: float | None
    observed_mrp: float | None
    overcharge_amount: float | None
    overcharge_pct: float | None
    warning: str | None
    baseline_confidence: float
    sample_count: int


def check_scan(
    scanned_mrp: float | None,
    official_mrp: float | None,
    stats: PriceStats,
    threshold: float | None = None,
) -> ScanVerdict:
    """Judge one shopper's scan at the shelf, in real time.

    The manufacturer's declared MRP takes precedence over the crowd-derived
    mode when it is known -- it is the legally operative figure. The mode is the
    fallback for products not yet in the catalogue.
    """
    multiplier = threshold or settings.RADAR_TAMPER_MULTIPLIER
    baseline = official_mrp if official_mrp else stats.modal_mrp

    if scanned_mrp is None or baseline is None:
        return ScanVerdict(
            is_gouged=False, severity=None, modal_mrp=baseline,
            observed_mrp=scanned_mrp, overcharge_amount=None, overcharge_pct=None,
            warning=None, baseline_confidence=stats.confidence,
            sample_count=stats.usable_count,
        )

    if scanned_mrp <= baseline * multiplier:
        return ScanVerdict(
            is_gouged=False, severity=None, modal_mrp=round(baseline, 2),
            observed_mrp=round(scanned_mrp, 2), overcharge_amount=0.0,
            overcharge_pct=0.0, warning=None,
            baseline_confidence=stats.confidence, sample_count=stats.usable_count,
        )

    over = scanned_mrp - baseline
    pct = (over / baseline) * 100
    severity = "PRIORITY" if pct >= 25 else "LEAD" if pct >= 10 else "WATCH"

    source = (
        "the manufacturer's declared MRP" if official_mrp
        else f"{stats.usable_count} verified scans of this product"
    )

    return ScanVerdict(
        is_gouged=True,
        severity=severity,
        modal_mrp=round(baseline, 2),
        observed_mrp=round(scanned_mrp, 2),
        overcharge_amount=round(over, 2),
        overcharge_pct=round(pct, 1),
        warning=(
            f"You are being charged Rs.{scanned_mrp:.2f}. According to {source}, "
            f"the price should be Rs.{baseline:.2f} -- an overcharge of "
            f"Rs.{over:.2f} ({pct:.0f}%). Selling above the printed MRP is an "
            "offence under the Legal Metrology Act, 2009."
        ),
        baseline_confidence=stats.confidence,
        sample_count=stats.usable_count,
    )


def window_start(days: int | None = None) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days or settings.RADAR_WINDOW_DAYS)
