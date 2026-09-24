"""Indian festival calendar and seasonal risk weighting.

The spec's risk formula carries a seasonal multiplier -- "sweet & ghee shops get
2.5x risk during Diwali week".  That is not decoration: overcharging and
short-weighting are strongly seasonal in Indian retail, concentrated in the
weeks before major festivals when demand for specific commodities spikes and
temporary sellers enter the market.

Dates here are approximate for the lunisolar festivals, which is honest: Diwali
moves by weeks year to year and pinning it to a false precision would be worse
than a stated window. Enforcement planning needs the *window*, not the tithi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Festival:
    name: str
    # (month, day) of the principal day. Lunisolar dates are the observed date
    # for the year in DATES below; this is the fallback approximation.
    approx_month: int
    approx_day: int
    # Enforcement interest begins this many days before and ends after.
    lead_days: int = 14
    trail_days: int = 3
    # Commodity categories whose risk rises, and by how much.
    category_multipliers: dict[str, float] = field(default_factory=dict)
    note: str = ""


# Observed principal dates. Solar festivals are fixed; lunisolar ones are listed
# per year because they shift substantially.
DATES: dict[int, dict[str, tuple[int, int]]] = {
    2025: {
        "Diwali": (10, 20), "Dussehra": (10, 2), "Raksha Bandhan": (8, 9),
        "Janmashtami": (8, 16), "Ganesh Chaturthi": (8, 27), "Holi": (3, 14),
        "Eid al-Fitr": (3, 31), "Eid al-Adha": (6, 7), "Navratri": (9, 22),
        "Onam": (9, 5), "Pongal": (1, 14), "Christmas": (12, 25),
        "Karva Chauth": (10, 10), "Makar Sankranti": (1, 14),
    },
    2026: {
        "Diwali": (11, 8), "Dussehra": (10, 20), "Raksha Bandhan": (8, 28),
        "Janmashtami": (9, 4), "Ganesh Chaturthi": (9, 14), "Holi": (3, 4),
        "Eid al-Fitr": (3, 20), "Eid al-Adha": (5, 27), "Navratri": (10, 11),
        "Onam": (8, 26), "Pongal": (1, 14), "Christmas": (12, 25),
        "Karva Chauth": (10, 29), "Makar Sankranti": (1, 14),
    },
    2027: {
        "Diwali": (10, 29), "Dussehra": (10, 9), "Raksha Bandhan": (8, 17),
        "Janmashtami": (8, 25), "Ganesh Chaturthi": (9, 4), "Holi": (3, 22),
        "Eid al-Fitr": (3, 9), "Eid al-Adha": (5, 17), "Navratri": (9, 30),
        "Onam": (9, 15), "Pongal": (1, 15), "Christmas": (12, 25),
        "Karva Chauth": (10, 18), "Makar Sankranti": (1, 14),
    },
}


FESTIVALS: list[Festival] = [
    Festival(
        "Diwali", 11, 8, lead_days=21, trail_days=5,
        category_multipliers={
            "sweets-mithai": 2.5, "ghee-butter": 2.5, "dry-fruits-nuts": 2.3,
            "chocolates-confectionery": 1.9, "edible-oils": 1.8,
            "snacks-namkeen": 1.6, "atta-flour": 1.4, "salt-sugar": 1.3,
            "electronics-small": 1.9, "cosmetics": 1.6,
        },
        note="Peak gifting season; sweets, ghee and dry fruits see the sharpest "
             "price and short-weight abuse, and temporary sellers proliferate.",
    ),
    Festival(
        "Dussehra", 10, 20, lead_days=10,
        category_multipliers={
            "sweets-mithai": 1.8, "snacks-namkeen": 1.5, "ghee-butter": 1.6,
            "atta-flour": 1.3,
        },
    ),
    Festival(
        "Navratri", 10, 11, lead_days=12, trail_days=9,
        category_multipliers={
            "atta-flour": 2.0, "dry-fruits-nuts": 1.8, "dairy-products": 1.6,
            "ghee-butter": 1.7, "spices-masala": 1.4,
        },
        note="Fasting demand shifts to specialist flours (kuttu, singhara), a "
             "recurring locus of short-weight and mislabelling complaints.",
    ),
    Festival(
        "Holi", 3, 4, lead_days=10,
        category_multipliers={
            "sweets-mithai": 2.0, "dairy-products": 1.7, "ghee-butter": 1.8,
            "beverages-juices": 1.5, "snacks-namkeen": 1.5,
        },
    ),
    Festival(
        "Eid al-Fitr", 3, 20, lead_days=14, trail_days=3,
        category_multipliers={
            "dry-fruits-nuts": 2.0, "sweets-mithai": 1.9, "dairy-products": 1.6,
            "rice-grains": 1.5, "ghee-butter": 1.6,
        },
    ),
    Festival(
        "Eid al-Adha", 5, 27, lead_days=10,
        category_multipliers={"spices-masala": 1.6, "rice-grains": 1.5, "ghee-butter": 1.4},
    ),
    Festival(
        "Raksha Bandhan", 8, 28, lead_days=8,
        category_multipliers={"sweets-mithai": 1.9, "chocolates-confectionery": 1.7},
    ),
    Festival(
        "Ganesh Chaturthi", 9, 14, lead_days=10,
        category_multipliers={
            "sweets-mithai": 2.0, "ghee-butter": 1.7, "atta-flour": 1.4,
            "dry-fruits-nuts": 1.5,
        },
    ),
    Festival(
        "Janmashtami", 9, 4, lead_days=7,
        category_multipliers={"dairy-products": 1.8, "ghee-butter": 1.7, "sweets-mithai": 1.6},
    ),
    Festival(
        "Onam", 8, 26, lead_days=12,
        category_multipliers={
            "edible-oils": 1.7, "rice-grains": 1.6, "spices-masala": 1.5,
            "sweets-mithai": 1.5,
        },
    ),
    Festival(
        "Pongal", 1, 14, lead_days=8,
        category_multipliers={
            "rice-grains": 1.8, "ghee-butter": 1.6, "salt-sugar": 1.5,
            "dairy-products": 1.4,
        },
    ),
    Festival(
        "Makar Sankranti", 1, 14, lead_days=8,
        category_multipliers={"salt-sugar": 1.7, "dry-fruits-nuts": 1.5, "sweets-mithai": 1.6},
    ),
    Festival(
        "Karva Chauth", 10, 29, lead_days=6,
        category_multipliers={"sweets-mithai": 1.6, "dry-fruits-nuts": 1.5, "cosmetics": 1.7},
    ),
    Festival(
        "Christmas", 12, 25, lead_days=14, trail_days=7,
        category_multipliers={
            "chocolates-confectionery": 2.0, "breakfast-cereals": 1.4,
            "beverages-juices": 1.5, "dry-fruits-nuts": 1.6,
        },
    ),
]


def _observed(fest: Festival, year: int) -> date:
    """Observed date for a year, falling back to the approximation."""
    table = DATES.get(year, {})
    if fest.name in table:
        m, d = table[fest.name]
        return date(year, m, d)
    return date(year, fest.approx_month, fest.approx_day)


@dataclass
class SeasonalContext:
    active: list[dict]
    multiplier: float
    reasons: list[str]

    @property
    def is_festival_period(self) -> bool:
        return bool(self.active)


def seasonal_multiplier(
    category_slug: str | None, on: date | None = None
) -> SeasonalContext:
    """Risk multiplier for a commodity category on a given date.

    When festival windows overlap, the LARGEST multiplier applies rather than
    the product of them. Compounding would let two mid-sized festivals imply a
    risk higher than Diwali itself, which is not what the data supports and
    would misdirect patrols.
    """
    day = on or date.today()
    slug = (category_slug or "").lower()

    active: list[dict] = []
    best = 1.0
    reasons: list[str] = []

    # Check adjacent years so a window spanning New Year is not missed.
    for year in (day.year - 1, day.year, day.year + 1):
        for fest in FESTIVALS:
            principal = _observed(fest, year)
            start = principal - timedelta(days=fest.lead_days)
            end = principal + timedelta(days=fest.trail_days)
            if not (start <= day <= end):
                continue

            mult = fest.category_multipliers.get(slug, 1.0)
            days_out = (principal - day).days
            entry = {
                "festival": fest.name,
                "date": principal.isoformat(),
                "days_until": days_out,
                "window": f"{start.isoformat()} to {end.isoformat()}",
                "multiplier": mult,
                "note": fest.note,
            }
            active.append(entry)
            if mult > best:
                best = mult
                reasons = [
                    f"{fest.name} on {principal:%d %b} "
                    + (
                        f"({days_out} days away)" if days_out > 0
                        else "(today)" if days_out == 0
                        else f"({-days_out} days ago)"
                    )
                    + f" raises risk for this category by {mult:.1f}x"
                ]

    active.sort(key=lambda e: abs(e["days_until"]))
    return SeasonalContext(active=active, multiplier=round(best, 3), reasons=reasons)


def upcoming(within_days: int = 45, on: date | None = None) -> list[dict]:
    """Festivals approaching within a horizon, for enforcement planning."""
    day = on or date.today()
    out = []
    for year in (day.year, day.year + 1):
        for fest in FESTIVALS:
            principal = _observed(fest, year)
            days = (principal - day).days
            if 0 <= days <= within_days:
                out.append({
                    "festival": fest.name,
                    "date": principal.isoformat(),
                    "days_until": days,
                    "watch_from": (principal - timedelta(days=fest.lead_days)).isoformat(),
                    "elevated_categories": sorted(
                        fest.category_multipliers,
                        key=lambda k: fest.category_multipliers[k],
                        reverse=True,
                    )[:6],
                    "peak_multiplier": max(fest.category_multipliers.values(), default=1.0),
                    "note": fest.note,
                })
    out.sort(key=lambda e: e["days_until"])
    return out


def category_multipliers_today(on: date | None = None) -> dict[str, float]:
    """Every elevated category right now -- drives the routing engine."""
    day = on or date.today()
    result: dict[str, float] = {}
    for fest in FESTIVALS:
        for year in (day.year - 1, day.year, day.year + 1):
            principal = _observed(fest, year)
            if not (
                principal - timedelta(days=fest.lead_days)
                <= day
                <= principal + timedelta(days=fest.trail_days)
            ):
                continue
            for slug, mult in fest.category_multipliers.items():
                result[slug] = max(result.get(slug, 1.0), mult)
    return result
