"""Macro policy intelligence -- spec section 3 / policy dashboard APIs.

Turns the inspection ledger into evidence a ministry can legislate from:
which clauses are failing most, which categories are improving or degrading, and
whether a rule change actually worked.

Two things separate this from a chart of counts:

  * **Trend requires a fair comparison.** Comparing this month's compliance rate
    to last month's is meaningless if the two months inspected different
    categories. Trends are therefore computed per category and only reported
    when both periods carry enough samples to support a claim.

  * **A rate needs a denominator.** "Rule 6(2) was violated 340 times" says
    nothing without knowing how often it was *checked*. Every clause statistic
    here is a violation rate over applicable inspections.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Below this, a period-over-period movement is noise rather than a trend.
MIN_SAMPLES_FOR_TREND = 8
# Percentage-point change that counts as a real movement.
TREND_THRESHOLD_PP = 3.0


@dataclass
class ClauseStat:
    clause: str
    rule_id: str
    rule_name: str
    violations: int
    applicable_inspections: int
    violation_rate: float
    severity_mix: dict[str, int] = field(default_factory=dict)
    penalty_exposure: float = 0.0
    trend_pp: float | None = None

    def to_dict(self) -> dict:
        return {
            "clause": self.clause,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "violations": self.violations,
            "applicable_inspections": self.applicable_inspections,
            "violation_rate": round(self.violation_rate, 2),
            "severity_mix": self.severity_mix,
            "penalty_exposure": round(self.penalty_exposure, 2),
            "trend_pp": round(self.trend_pp, 2) if self.trend_pp is not None else None,
            "direction": (
                None if self.trend_pp is None
                else "worsening" if self.trend_pp > TREND_THRESHOLD_PP
                else "improving" if self.trend_pp < -TREND_THRESHOLD_PP
                else "stable"
            ),
        }


@dataclass
class CategoryTrend:
    slug: str
    name: str
    current_score: float
    previous_score: float | None
    change: float | None
    current_samples: int
    previous_samples: int
    direction: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "current_avg_score": round(self.current_score, 1),
            "previous_avg_score": (
                round(self.previous_score, 1) if self.previous_score is not None else None
            ),
            "change": round(self.change, 1) if self.change is not None else None,
            "direction": self.direction,
            "current_samples": self.current_samples,
            "previous_samples": self.previous_samples,
            "note": self.note,
        }


def compute_clause_stats(
    violations: list[dict],
    applicable_counts: dict[str, int],
    previous_rates: dict[str, float] | None = None,
) -> list[ClauseStat]:
    """Rank clauses by violation RATE, not raw count.

    Raw counts simply rank clauses by how often they are checked, which makes
    the most universal rule look like the biggest problem. Rate answers the
    question a policymaker is actually asking: where is compliance weakest?
    """
    grouped: dict[str, list[dict]] = {}
    for v in violations:
        grouped.setdefault(v["rule_id"], []).append(v)

    stats: list[ClauseStat] = []
    for rule_id, items in grouped.items():
        applicable = applicable_counts.get(rule_id, 0)
        if applicable <= 0:
            continue

        severity_mix: dict[str, int] = {}
        for v in items:
            sev = v.get("severity") or "MAJOR"
            severity_mix[sev] = severity_mix.get(sev, 0) + 1

        rate = (len(items) / applicable) * 100
        trend = None
        if previous_rates and rule_id in previous_rates:
            trend = rate - previous_rates[rule_id]

        stats.append(ClauseStat(
            clause=items[0].get("legal_clause") or rule_id,
            rule_id=rule_id,
            rule_name=items[0].get("rule_name") or rule_id,
            violations=len(items),
            applicable_inspections=applicable,
            violation_rate=rate,
            severity_mix=severity_mix,
            penalty_exposure=sum(v.get("penalty_amount") or 0.0 for v in items),
            trend_pp=trend,
        ))

    stats.sort(key=lambda s: -s.violation_rate)
    return stats


def compute_category_trends(
    current: dict[str, list[float]],
    previous: dict[str, list[float]],
    names: dict[str, str] | None = None,
) -> list[CategoryTrend]:
    """Per-category compliance movement between two comparable windows."""
    labels = names or {}
    trends: list[CategoryTrend] = []

    for slug, scores in current.items():
        if not scores:
            continue
        cur = statistics.mean(scores)
        prev_scores = previous.get(slug, [])

        # A movement is only reported when both windows carry enough
        # inspections to support the claim. Announcing that a category
        # "degraded 20 points" on the strength of two inspections would be
        # statistically indefensible and could misdirect policy.
        if len(scores) < MIN_SAMPLES_FOR_TREND or len(prev_scores) < MIN_SAMPLES_FOR_TREND:
            trends.append(CategoryTrend(
                slug=slug,
                name=labels.get(slug, slug),
                current_score=cur,
                previous_score=statistics.mean(prev_scores) if prev_scores else None,
                change=None,
                current_samples=len(scores),
                previous_samples=len(prev_scores),
                direction="insufficient_data",
                note=(
                    f"{len(scores)} current and {len(prev_scores)} prior inspections; "
                    f"at least {MIN_SAMPLES_FOR_TREND} in each period are needed "
                    "before a trend can be claimed."
                ),
            ))
            continue

        prev = statistics.mean(prev_scores)
        change = cur - prev
        direction = (
            "degrading" if change < -TREND_THRESHOLD_PP
            else "improving" if change > TREND_THRESHOLD_PP
            else "stable"
        )
        trends.append(CategoryTrend(
            slug=slug,
            name=labels.get(slug, slug),
            current_score=cur,
            previous_score=prev,
            change=change,
            current_samples=len(scores),
            previous_samples=len(prev_scores),
            direction=direction,
            note=(
                f"Compliance {'fell' if change < 0 else 'rose'} "
                f"{abs(change):.1f} points across {len(scores)} inspections."
                if direction != "stable"
                else "No material change between periods."
            ),
        ))

    trends.sort(key=lambda t: (t.change if t.change is not None else 0))
    return trends


def geographic_summary(sessions: list[dict], grid_deg: float = 0.05) -> list[dict]:
    """Aggregate compliance onto a coarse grid for choropleth mapping.

    Grid cells rather than exact points: publishing the precise coordinates of
    every failed inspection would identify individual small retailers in a
    public dashboard, which is neither necessary nor fair before adjudication.
    """
    cells: dict[tuple[int, int], list[dict]] = {}
    for s in sessions:
        lat, lng = s.get("latitude"), s.get("longitude")
        if lat is None or lng is None:
            continue
        key = (int(lat / grid_deg), int(lng / grid_deg))
        cells.setdefault(key, []).append(s)

    out = []
    for (gy, gx), items in cells.items():
        scores = [i["overall_score"] for i in items if i.get("overall_score") is not None]
        non_compliant = len([i for i in items if i.get("compliance_status") == "NON_COMPLIANT"])
        out.append({
            "centre": {
                "latitude": round((gy + 0.5) * grid_deg, 4),
                "longitude": round((gx + 0.5) * grid_deg, 4),
            },
            "cell_size_deg": grid_deg,
            "inspections": len(items),
            "avg_score": round(statistics.mean(scores), 1) if scores else None,
            "non_compliant": non_compliant,
            "non_compliance_rate": round(non_compliant / len(items) * 100, 1),
        })

    out.sort(key=lambda c: -c["non_compliance_rate"])
    return out


def amendment_impact(
    before: list[float], after: list[float], amendment_name: str
) -> dict:
    """Did a rule change actually improve compliance?

    The spec's "policy feedback loop". Effect size is reported alongside the
    raw difference because a 2-point move on 500 inspections means something
    quite different from a 2-point move on 12.
    """
    if len(before) < MIN_SAMPLES_FOR_TREND or len(after) < MIN_SAMPLES_FOR_TREND:
        return {
            "amendment": amendment_name,
            "conclusive": False,
            "verdict": "insufficient_data",
            "note": (
                f"{len(before)} inspections before and {len(after)} after; "
                f"at least {MIN_SAMPLES_FOR_TREND} in each period are required."
            ),
        }

    mean_before = statistics.mean(before)
    mean_after = statistics.mean(after)
    change = mean_after - mean_before

    # Cohen's d -- how large the shift is relative to natural variation.
    sd_before = statistics.pstdev(before) or 1e-9
    sd_after = statistics.pstdev(after) or 1e-9
    pooled = (((len(before) - 1) * sd_before ** 2 + (len(after) - 1) * sd_after ** 2)
              / max(1, len(before) + len(after) - 2)) ** 0.5
    effect = change / pooled if pooled else 0.0

    magnitude = (
        "negligible" if abs(effect) < 0.2
        else "small" if abs(effect) < 0.5
        else "moderate" if abs(effect) < 0.8
        else "large"
    )

    return {
        "amendment": amendment_name,
        "conclusive": abs(effect) >= 0.2,
        "verdict": (
            "improved" if change > 0 and abs(effect) >= 0.2
            else "worsened" if change < 0 and abs(effect) >= 0.2
            else "no_measurable_effect"
        ),
        "mean_before": round(mean_before, 2),
        "mean_after": round(mean_after, 2),
        "change": round(change, 2),
        "effect_size": round(effect, 3),
        "effect_magnitude": magnitude,
        "samples_before": len(before),
        "samples_after": len(after),
        "note": (
            f"Mean compliance moved {change:+.1f} points "
            f"({magnitude} effect, d={effect:.2f}) across "
            f"{len(before)} + {len(after)} inspections."
        ),
    }


def period_bounds(days: int) -> tuple[datetime, datetime, datetime]:
    """(previous_start, current_start, now) for two equal comparison windows."""
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)
    return previous_start, current_start, now
