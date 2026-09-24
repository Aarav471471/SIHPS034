"""Predictive enforcement routing -- spec intelligence/risk_routing_engine.py, 3.C.

Replaces random patrol with a ranked, ordered day plan.

Two problems are solved, and conflating them is the usual mistake:

  1. WHICH stores are worth visiting -- the spec's weighted risk score
         R_store = w1*History + w2*CitizenLeads + w3*PriceAnomalies + w4*Seasonal

  2. In WHAT ORDER to visit them -- a travelling-salesman problem. Ranking by
     risk and visiting in that order can send an officer back and forth across
     a city all day. The route is therefore optimised for travel distance
     *subject to* covering the highest-risk stores, using nearest-neighbour
     construction followed by 2-opt improvement.

The second half is what converts a good list into a usable day.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from core.geofence import haversine_km
from intelligence.festival_calendar import seasonal_multiplier

logger = logging.getLogger("metrix.routing")

# Average urban patrol speed including parking and walking, km/h. Deliberately
# pessimistic: a plan an officer cannot finish is worse than a shorter one.
PATROL_SPEED_KMH = 18.0
# Minutes on site for one inspection.
MINUTES_PER_INSPECTION = 25
# Half-life for how quickly a past violation stops predicting the present.
HISTORY_HALFLIFE_DAYS = 120.0


@dataclass
class StoreRisk:
    store_name: str
    latitude: float
    longitude: float
    address: str | None = None

    historical_violations: int = 0
    weighted_history: float = 0.0
    citizen_leads: int = 0
    verified_leads: int = 0
    price_anomalies: int = 0
    max_overcharge_pct: float = 0.0
    days_since_inspection: int | None = None
    top_categories: list[str] = field(default_factory=list)
    seasonal_multiplier: float = 1.0

    risk_score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self, rank: int | None = None) -> dict:
        out = {
            "store_name": self.store_name,
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "address": self.address,
            "risk_score": round(self.risk_score, 1),
            "risk_reasons": self.risk_reasons,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "historical_violations": self.historical_violations,
            "citizen_leads": self.citizen_leads,
            "price_anomalies": self.price_anomalies,
            "days_since_inspection": self.days_since_inspection,
            "seasonal_multiplier": self.seasonal_multiplier,
            "watch_categories": self.top_categories,
        }
        if rank is not None:
            out["rank"] = rank
        return out


@dataclass
class PatrolRoute:
    stops: list[StoreRisk]
    total_distance_km: float
    estimated_minutes: int
    start_lat: float
    start_lng: float
    optimisation: str
    naive_distance_km: float = 0.0
    seasonal_context: list[dict] = field(default_factory=list)
    coverage_warnings: list[str] = field(default_factory=list)

    @property
    def distance_saved_km(self) -> float:
        return max(0.0, self.naive_distance_km - self.total_distance_km)

    def to_dict(self) -> dict:
        return {
            "patrol_route": [s.to_dict(rank=i + 1) for i, s in enumerate(self.stops)],
            "summary": {
                "stops": len(self.stops),
                "total_distance_km": round(self.total_distance_km, 2),
                "estimated_duration_minutes": self.estimated_minutes,
                "estimated_duration_readable": (
                    f"{self.estimated_minutes // 60}h {self.estimated_minutes % 60}m"
                ),
                "travel_optimisation": self.optimisation,
                "risk_covered_first_3": round(
                    sum(s.risk_score for s in self.stops[:3]), 1
                ),
                "distance_if_visited_by_rank_km": round(self.naive_distance_km, 2),
                "distance_saved_km": round(self.distance_saved_km, 2),
                "aggregate_risk": round(sum(s.risk_score for s in self.stops), 1),
            },
            "seasonal_context": self.seasonal_context,
            "coverage_warnings": self.coverage_warnings,
        }


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------
def _decay(days_ago: float, halflife: float = HISTORY_HALFLIFE_DAYS) -> float:
    """Exponential recency weight.

    A violation found last week predicts today's behaviour far better than one
    from two years ago. Counting them equally sends officers back to shops that
    have long since cleaned up, while missing new offenders.
    """
    return 0.5 ** (max(0.0, days_ago) / halflife)


def score_store(
    store: StoreRisk,
    on: date | None = None,
    weights: dict[str, float] | None = None,
) -> StoreRisk:
    """Compute R_store per spec 3.C, with each component normalised to 0-100."""
    w = weights or {
        "history": settings.RISK_W_HISTORICAL,
        "citizen": settings.RISK_W_CITIZEN_LEADS,
        "anomaly": settings.RISK_W_PRICE_ANOMALY,
        "seasonal": settings.RISK_W_SEASONAL,
    }
    reasons: list[str] = []

    # --- 1. Historical violations, recency-weighted ---
    history = min(100.0, store.weighted_history * 18.0)
    if store.historical_violations:
        reasons.append(
            f"{store.historical_violations} past violation"
            f"{'s' if store.historical_violations != 1 else ''} recorded at this retailer"
        )

    # --- 2. Citizen leads. A verified lead is worth far more than a raw one. ---
    citizen = min(100.0, (store.citizen_leads * 12.0) + (store.verified_leads * 25.0))
    if store.citizen_leads:
        detail = f"{store.citizen_leads} citizen report{'s' if store.citizen_leads != 1 else ''}"
        if store.verified_leads:
            detail += f" ({store.verified_leads} already confirmed by an officer)"
        reasons.append(detail)

    # --- 3. Price-gouging anomalies ---
    anomaly = min(100.0, store.price_anomalies * 20.0 + store.max_overcharge_pct * 1.2)
    if store.price_anomalies:
        reasons.append(
            f"{store.price_anomalies} price anomal"
            f"{'ies' if store.price_anomalies != 1 else 'y'} detected"
            + (f", peaking at {store.max_overcharge_pct:.0f}% above MRP"
               if store.max_overcharge_pct else "")
        )

    # --- 4. Seasonal exposure ---
    # Driven by what this store actually sells: a stationery shop gets no Diwali
    # uplift, a sweet shop gets a large one.
    day = on or date.today()
    best_mult, festival_reason = 1.0, None
    for slug in store.top_categories or []:
        ctx = seasonal_multiplier(slug, day)
        if ctx.multiplier > best_mult:
            best_mult = ctx.multiplier
            festival_reason = ctx.reasons[0] if ctx.reasons else None
    store.seasonal_multiplier = round(best_mult, 3)
    seasonal = min(100.0, (best_mult - 1.0) * 66.0)
    if festival_reason:
        reasons.append(festival_reason)

    base = (
        w["history"] * history
        + w["citizen"] * citizen
        + w["anomaly"] * anomaly
        + w["seasonal"] * seasonal
    )

    # --- Coverage nudge ---
    # A shop nobody has visited in a year is a blind spot, not a safe shop.
    # Small, so it never outweighs real evidence -- it only breaks ties.
    if store.days_since_inspection is None:
        base += 8.0
        reasons.append("Never inspected -- no compliance history exists for this retailer")
    elif store.days_since_inspection > 180:
        base += min(10.0, store.days_since_inspection / 60.0)
        reasons.append(f"Not inspected for {store.days_since_inspection} days")

    store.risk_score = round(min(100.0, base), 2)
    store.components = {
        "historical": round(history, 2),
        "citizen_leads": round(citizen, 2),
        "price_anomalies": round(anomaly, 2),
        "seasonal": round(seasonal, 2),
    }
    store.risk_reasons = reasons or ["No specific risk indicators; routine coverage visit"]
    return store


def weighted_history(violation_dates: list[datetime], as_of: datetime | None = None) -> float:
    """Recency-weighted count of past violations."""
    from models.base import as_utc

    now = as_of or datetime.now(timezone.utc)
    total = 0.0
    for when in violation_dates:
        aware = as_utc(when)
        if aware is None:
            continue
        total += _decay((now - aware).total_seconds() / 86400.0)
    return round(total, 4)


# ---------------------------------------------------------------------------
# Route optimisation
# ---------------------------------------------------------------------------
def _path_length(points: list[tuple[float, float]]) -> float:
    return sum(
        haversine_km(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def _nearest_neighbour(
    start: tuple[float, float], stores: list[StoreRisk]
) -> list[StoreRisk]:
    remaining = list(stores)
    ordered: list[StoreRisk] = []
    cursor = start
    while remaining:
        nxt = min(
            remaining,
            key=lambda s: haversine_km(cursor[0], cursor[1], s.latitude, s.longitude),
        )
        remaining.remove(nxt)
        ordered.append(nxt)
        cursor = (nxt.latitude, nxt.longitude)
    return ordered


# Kilometres of extra travel worth accepting to move one full risk point
# earlier in the day. Tuned so a ~40-point risk gap can pull a store ahead of a
# ~2 km detour, which matches how an officer actually trades these off.
RISK_URGENCY_WEIGHT = 0.06


def _route_cost(
    start: tuple[float, float], seq: list[StoreRisk], risk_weight: float
) -> float:
    """Blended objective: travel distance plus a penalty for visiting late.

    Pure distance minimisation is the wrong objective for enforcement. A patrol
    is routinely cut short -- a long inspection, a dispute, a call elsewhere --
    and whatever was scheduled last is what gets dropped. Optimising travel
    alone will happily strand the single highest-risk shop at the end of the
    day, which is precisely the store the officer most needed to reach.

    Each stop therefore carries a penalty proportional to its risk multiplied by
    its position, so high-risk stores are pulled earlier unless the detour is
    genuinely expensive. The route stays efficient; it just front-loads the
    stops that matter.
    """
    distance = _path_length([start] + [(s.latitude, s.longitude) for s in seq])
    urgency = sum(s.risk_score * i for i, s in enumerate(seq))
    return distance + risk_weight * urgency


def _two_opt(
    start: tuple[float, float],
    ordered: list[StoreRisk],
    max_passes: int = 40,
    risk_weight: float = RISK_URGENCY_WEIGHT,
) -> list[StoreRisk]:
    """Improve a route by reversing segments that cross over themselves.

    Nearest-neighbour is greedy and characteristically strands one far stop,
    forcing a long backtrack at the end. 2-opt removes those crossings.

    Segment reversal alone cannot always front-load an urgent stop, so an
    or-opt move (relocating a single stop to a better position) is applied as
    well. With a handful of stops this converges almost instantly.
    """
    if len(ordered) < 3:
        return ordered

    best = ordered[:]
    best_cost = _route_cost(start, best, risk_weight)

    for _ in range(max_passes):
        improved = False

        # 2-opt: reverse a segment, removing route crossings.
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best)):
                candidate = best[: i + 1] + best[i + 1 : j + 1][::-1] + best[j + 1 :]
                cost = _route_cost(start, candidate, risk_weight)
                if cost < best_cost - 1e-9:
                    best, best_cost = candidate, cost
                    improved = True

        # or-opt: move one stop elsewhere. This is what lets an urgent but
        # awkwardly placed store climb the order.
        for i in range(len(best)):
            for j in range(len(best)):
                if i == j:
                    continue
                moved = best[:]
                stop = moved.pop(i)
                moved.insert(j, stop)
                cost = _route_cost(start, moved, risk_weight)
                if cost < best_cost - 1e-9:
                    best, best_cost = moved, cost
                    improved = True

        if not improved:
            break
    return best


def build_route(
    stores: list[StoreRisk],
    start_lat: float,
    start_lng: float,
    max_stops: int | None = None,
    radius_km: float | None = None,
    on: date | None = None,
) -> PatrolRoute:
    """Select the highest-risk stores in range and order them for travel."""
    limit = max_stops or settings.ROUTE_MAX_STOPS
    reach = radius_km or settings.ROUTE_DEFAULT_RADIUS_KM

    in_range = [
        s for s in stores
        if haversine_km(start_lat, start_lng, s.latitude, s.longitude) <= reach
    ]

    # Risk selects WHICH stores; geography then decides the order.
    selected = sorted(in_range, key=lambda s: -s.risk_score)[:limit]
    if not selected:
        return PatrolRoute(
            stops=[], total_distance_km=0.0, estimated_minutes=0,
            start_lat=start_lat, start_lng=start_lng,
            optimisation="no stores within range",
        )

    start = (start_lat, start_lng)
    naive = _path_length([start] + [(s.latitude, s.longitude) for s in selected])

    ordered = _two_opt(start, _nearest_neighbour(start, selected))
    distance = _path_length([start] + [(s.latitude, s.longitude) for s in ordered])

    travel_minutes = (distance / PATROL_SPEED_KMH) * 60
    total_minutes = int(round(travel_minutes + len(ordered) * MINUTES_PER_INSPECTION))

    seasonal_ctx: list[dict] = []
    seen: set[str] = set()
    for s in ordered:
        for slug in s.top_categories or []:
            ctx = seasonal_multiplier(slug, on or date.today())
            for entry in ctx.active:
                key = f"{entry['festival']}|{slug}"
                if key not in seen and entry["multiplier"] > 1.0:
                    seen.add(key)
                    seasonal_ctx.append({**entry, "category": slug})
    seasonal_ctx.sort(key=lambda e: -e["multiplier"])

    # Tell the officer when the travel/risk trade-off has a real cost. The
    # optimiser will decline a long detour to front-load one high-risk store --
    # usually correct, but if the day is cut short that store is the one missed.
    # Surfacing it lets a human override a decision made on distance alone.
    warnings: list[str] = []
    if ordered:
        highest = max(ordered, key=lambda s: s.risk_score)
        position = ordered.index(highest) + 1
        if position > max(2, len(ordered) // 2) and highest.risk_score >= 60:
            detour = haversine_km(start_lat, start_lng, highest.latitude, highest.longitude)
            warnings.append(
                f"{highest.store_name} carries the highest risk on this route "
                f"({highest.risk_score:.0f}) but is scheduled stop {position} of "
                f"{len(ordered)}, because it lies {detour:.1f} km from your start "
                "point and visiting it earlier would add substantial travel. "
                "If the day may be cut short, consider going there first."
            )

    over_shift = total_minutes > 8 * 60
    if over_shift:
        warnings.append(
            f"This plan needs about {total_minutes // 60}h {total_minutes % 60}m, "
            "which exceeds a normal shift. Consider reducing the number of stops."
        )

    return PatrolRoute(
        stops=ordered,
        total_distance_km=distance,
        estimated_minutes=total_minutes,
        start_lat=start_lat,
        start_lng=start_lng,
        optimisation="nearest-neighbour + 2-opt/or-opt, risk-weighted",
        naive_distance_km=naive,
        seasonal_context=seasonal_ctx[:8],
        coverage_warnings=warnings,
    )
