"""Canonical string constants for every CHECK-constrained column in the spec.

Stored as VARCHAR (matching the spec DDL) rather than native DB enums so new
values can ship without a migration -- important for a rules engine that grows.
"""
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    OFFICER = "officer"
    SENIOR_OFFICER = "senior_officer"
    ADMIN = "admin"
    CONSUMER = "consumer"
    BRAND = "brand"


class SourceType(StrEnum):
    OFFICER = "OFFICER"
    CITIZEN_REPORT = "CITIZEN_REPORT"
    BRAND_PRE_CERT = "BRAND_PRE_CERT"


class SessionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FLAGGED = "FLAGGED"
    PEER_REVIEW = "PEER_REVIEW"
    APPEALED = "APPEALED"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class ComplianceStatus(StrEnum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    WARNING = "WARNING"


class JurisdictionStatus(StrEnum):
    WITHIN_BOUNDS = "WITHIN_BOUNDS"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    UNKNOWN = "UNKNOWN"


class SurfaceType(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"
    SIDE = "SIDE"
    BOTTOM = "BOTTOM"
    CAP = "CAP"
    DIE_LINE = "DIE_LINE"


class ViolationStatus(StrEnum):
    FAIL = "FAIL"
    WARNING = "WARNING"
    PASS = "PASS"


class ReportCategory(StrEnum):
    OVERCHARGING = "OVERCHARGING"
    MISSING_MRP = "MISSING_MRP"
    MISSING_EXPIRY = "MISSING_EXPIRY"
    EXPIRED_STOCK = "EXPIRED_STOCK"
    MISSING_NET_QTY = "MISSING_NET_QTY"
    OTHER = "OTHER"


class ReportStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    INVESTIGATING = "INVESTIGATING"
    REJECTED = "REJECTED"


class PeerReviewTrigger(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONTESTED_UNIT_PRICE = "CONTESTED_UNIT_PRICE"
    HIGH_PENALTY = "HIGH_PENALTY"
    MANUAL = "MANUAL"


class PeerReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class AppellateStatus(StrEnum):
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class BadgeLevel(StrEnum):
    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    STANDARD = "STANDARD"
    FLAGGED = "FLAGGED"


class AlertType(StrEnum):
    EXPIRED_BATCH_WARNING = "EXPIRED_BATCH_WARNING"
    PRODUCT_RECALL = "PRODUCT_RECALL"
    PRICE_SURGE = "PRICE_SURGE"
    COMPLIANCE_UPDATE = "COMPLIANCE_UPDATE"


class EcomPlatform(StrEnum):
    AMAZON = "Amazon"
    FLIPKART = "Flipkart"
    BLINKIT = "Blinkit"
    ZEPTO = "Zepto"
    SWIGGY_INSTAMART = "Swiggy Instamart"


def badge_for_score(score: float | None) -> str:
    """Map a compliance score to the consumer-facing trust badge."""
    if score is None:
        return BadgeLevel.STANDARD
    if score >= 95:
        return BadgeLevel.GOLD
    if score >= 85:
        return BadgeLevel.SILVER
    if score >= 70:
        return BadgeLevel.BRONZE
    if score >= 50:
        return BadgeLevel.STANDARD
    return BadgeLevel.FLAGGED
