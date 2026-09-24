"""Citizen reporter trust score -- spec core/reputation.py, section 3.B.

The scoring rule itself is deliberately simple and published in the spec:

    start at 50
    +10  when an officer confirms the reported violation
    -20  when a report is found to be spam or false
    >80  earns the "Verified Vigilant Citizen" badge and queue priority

The asymmetry is the point. A false report costs twice what a confirmed one
earns, so flooding the officer queue with noise is self-defeating, while a
genuinely observant citizen climbs steadily.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from models.enums import ReportStatus

TRUST_MIN = 0.0
TRUST_MAX = 100.0


@dataclass
class TrustUpdate:
    previous_score: float
    new_score: float
    delta: float
    badge: str
    badge_changed: bool
    reason: str


def clamp(score: float) -> float:
    return max(TRUST_MIN, min(TRUST_MAX, round(score, 2)))


def badge_for(score: float) -> str:
    if score > settings.TRUST_SCORE_VERIFIED_THRESHOLD:
        return "VERIFIED_VIGILANT_CITIZEN"
    if score >= 60:
        return "ACTIVE_CITIZEN"
    if score >= 35:
        return "CITIZEN"
    return "LOW_TRUST"


def apply_verdict(current_score: float, verdict: str) -> TrustUpdate:
    """Apply an officer's verdict on a citizen report to the reporter's score."""
    if verdict == ReportStatus.VERIFIED:
        delta = settings.TRUST_SCORE_CONFIRMED_DELTA
        reason = "Report confirmed by a Legal Metrology officer during field inspection"
    elif verdict == ReportStatus.REJECTED:
        delta = settings.TRUST_SCORE_SPAM_DELTA
        reason = "Report could not be substantiated and was marked false"
    else:
        delta = 0.0
        reason = f"Report status changed to {verdict}; trust score unaffected"

    new_score = clamp(current_score + delta)
    old_badge, new_badge = badge_for(current_score), badge_for(new_score)

    return TrustUpdate(
        previous_score=round(current_score, 2),
        new_score=new_score,
        delta=round(new_score - current_score, 2),
        badge=new_badge,
        badge_changed=old_badge != new_badge,
        reason=reason,
    )


def priority_score(
    trust_score: float,
    category_weight: float = 1.0,
    has_photo: bool = True,
    has_gps: bool = True,
) -> float:
    """Ordering key for the officer's daily lead queue.

    Trust dominates (spec: high-trust reports "jump to the top"), but a lead
    with no photograph and no GPS fix is materially harder to action, so it is
    discounted rather than trusted purely on the reporter's history.
    """
    score = trust_score * category_weight
    if not has_photo:
        score *= 0.6
    if not has_gps:
        score *= 0.75
    return round(min(TRUST_MAX * category_weight, score), 2)


# Some report categories carry more enforcement weight than others.
CATEGORY_WEIGHTS: dict[str, float] = {
    "EXPIRED_STOCK": 1.5,      # a live public-health risk
    "OVERCHARGING": 1.3,       # direct, measurable consumer loss
    "MISSING_MRP": 1.2,
    "MISSING_EXPIRY": 1.15,
    "MISSING_NET_QTY": 1.0,
    "OTHER": 0.9,
}


def category_weight(category: str | None) -> float:
    return CATEGORY_WEIGHTS.get(category or "OTHER", 0.9)


def is_rate_limited(reports_in_last_hour: int) -> tuple[bool, str | None]:
    """Anti-spam shield -- volume cap independent of trust score."""
    cap = settings.CITIZEN_REPORT_RATE_LIMIT_PER_HOUR
    if reports_in_last_hour >= cap:
        return True, (
            f"Report limit reached ({cap} per hour). "
            "This limit exists to keep the officer queue actionable."
        )
    return False, None
