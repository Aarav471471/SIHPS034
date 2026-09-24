"""Rule contract -- spec rules/base.py.

Every compliance check is a subclass of BaseRule.  Three properties are
non-negotiable, because a finding that lacks any of them cannot support a legal
notice:

  * it cites a specific clause of the Act or Rules,
  * it states the evidence in plain language an officer can read aloud, and
  * it points at the pixels that prove it.

Rules are deterministic. They receive already-extracted values and decide
compliance by arithmetic and pattern, never by asking a model. That separation
is what makes the outcome reproducible and defensible on appeal: run the same
inputs a year later in court and the same finding comes out.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from models.enums import ViolationStatus

# ---------------------------------------------------------------------------
# Severity and penalty
# ---------------------------------------------------------------------------
CRITICAL = "CRITICAL"
MAJOR = "MAJOR"
MINOR = "MINOR"


@dataclass
class RuleResult:
    """One rule's verdict on one session."""

    rule_id: str
    rule_name: str
    status: str                        # PASS | WARNING | FAIL
    field_name: str | None = None
    evidence_text: str = ""
    legal_clause: str = ""
    severity: str = MAJOR
    confidence: float = 1.0
    calculated_value: str | None = None
    expected_value: str | None = None
    discrepancy: str | None = None
    suggested_fix: str | None = None
    penalty_amount: float | None = None
    evidence_crop_path: str | None = None
    surface: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ViolationStatus.PASS

    @property
    def is_violation(self) -> bool:
        return self.status in (ViolationStatus.FAIL, ViolationStatus.WARNING)


@dataclass
class RuleContext:
    """Everything a rule is allowed to see.

    Deliberately a plain data object with no database session and no network
    client: a rule that could query anything would stop being reproducible.
    """

    fields: dict[str, str | None]                    # field_name -> normalised value
    raw_fields: dict[str, Any] = field(default_factory=dict)   # ExtractedField rows
    surfaces: list[str] = field(default_factory=list)
    surface_area_cm2: float | None = None
    package_width_cm: float | None = None
    package_height_cm: float | None = None
    font_heights_mm: dict[str, float] = field(default_factory=dict)
    barcode: str | None = None
    barcode_verified: bool = False
    category_slug: str | None = None
    product_category: str | None = None
    inspection_date: date | None = None
    is_pre_certification: bool = False                # brand sandbox: advisory mode
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> str | None:
        v = self.fields.get(name)
        return v.strip() if isinstance(v, str) and v.strip() else None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def crop_path(self, name: str) -> str | None:
        row = self.raw_fields.get(name)
        return getattr(row, "raw_pixel_crop_path", None) if row else None

    def surface_of(self, name: str) -> str | None:
        row = self.raw_fields.get(name)
        return getattr(row, "surface_found", None) if row else None

    def confidence_of(self, name: str) -> float:
        row = self.raw_fields.get(name)
        if row is None:
            return 1.0
        value = getattr(row, "effective_confidence", None)
        return float(value) if value is not None else 1.0


class BaseRule(ABC):
    """A single compliance check."""

    rule_id: str = "R-BASE"
    rule_name: str = "Base Rule"
    legal_clause: str = ""
    field_name: str | None = None
    severity: str = MAJOR
    penalty_amount: float = 25_000.0
    # Set when a rule cannot run without a value it did not receive; the
    # engine then reports "not assessable" rather than a false pass.
    requires: tuple[str, ...] = ()

    @abstractmethod
    def evaluate(self, ctx: RuleContext) -> RuleResult: ...

    # -------------------------------------------------------------- helpers --
    def _result(
        self, status: str, evidence: str, **kwargs
    ) -> RuleResult:
        kwargs.setdefault("severity", self.severity)
        kwargs.setdefault("penalty_amount", self.penalty_amount if status == "FAIL" else None)
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            status=status,
            field_name=kwargs.pop("field_name", self.field_name),
            evidence_text=evidence,
            legal_clause=self.legal_clause,
            **kwargs,
        )

    def passed(self, evidence: str, **kwargs) -> RuleResult:
        return self._result(ViolationStatus.PASS, evidence, **kwargs)

    def failed(self, evidence: str, **kwargs) -> RuleResult:
        return self._result(ViolationStatus.FAIL, evidence, **kwargs)

    def warned(self, evidence: str, **kwargs) -> RuleResult:
        return self._result(ViolationStatus.WARNING, evidence, **kwargs)

    def run(self, ctx: RuleContext) -> RuleResult:
        """Evaluate with guard rails around the rule's own logic.

        A rule that raises must not take down the inspection: the finding is
        downgraded to a warning that says the check could not be completed,
        which is honest and lets the remaining rules still produce a notice.
        """
        missing = [r for r in self.requires if not ctx.has(r)]
        if missing and not isinstance(self, _AlwaysRunnable):
            return self.warned(
                f"{self.rule_name} could not be assessed: "
                f"{', '.join(missing)} was not extracted from any surface.",
                severity=MINOR,
                penalty_amount=None,
            )
        try:
            result = self.evaluate(ctx)
        except Exception as exc:  # pragma: no cover - defensive
            return self.warned(
                f"{self.rule_name} could not be evaluated ({exc.__class__.__name__}): {exc}",
                severity=MINOR,
                penalty_amount=None,
            )

        # Attach evidence pointers if the rule did not set them itself.
        if result.evidence_crop_path is None and result.field_name:
            result.evidence_crop_path = ctx.crop_path(result.field_name)
        if result.surface is None and result.field_name:
            result.surface = ctx.surface_of(result.field_name)
        if result.confidence == 1.0 and result.field_name:
            result.confidence = ctx.confidence_of(result.field_name)
        # Pre-certification is advisory: a brand checking artwork before
        # printing must not be issued statutory penalties.
        if ctx.is_pre_certification and result.status == ViolationStatus.FAIL:
            result.penalty_amount = None
        return result


class _AlwaysRunnable:
    """Marker for rules whose whole job is detecting absence.

    A missing-declaration rule must still run when the declaration is missing --
    that is the violation. Without this marker the `requires` guard would
    suppress exactly the finding the rule exists to make.
    """


# ===========================================================================
# Parsing helpers shared across rules
# ===========================================================================
# Indian digit grouping: commas are ALWAYS thousands separators, never decimal
# points (1,250.50 is one thousand two hundred fifty rupees fifty paise). A
# pattern that allowed ",50" as a decimal fraction would read Rs.1,250.50 as
# Rs.1.25 -- a thousandfold understatement of an MRP, which would corrupt both
# the notice and the price-gouging radar that consumes these values.
_AMOUNT = r"([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
CURRENCY_RE = re.compile(
    rf"(?:rs\.?|inr|₹)\s*{_AMOUNT}|{_AMOUNT}\s*(?:rs\.?|inr|₹)",
    re.IGNORECASE,
)

QUANTITY_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*"
    r"(kg|kgs|kilogram|kilograms|g|gm|gms|gram|grams|mg|"
    r"l|ltr|litre|liter|litres|liters|ml|millilitre|milliliter|"
    r"n|no|nos|pc|pcs|piece|pieces|u|units?)\b",
    re.IGNORECASE,
)

# Canonical metric units under Rule 8. Non-metric declarations are a violation.
UNIT_CANONICAL: dict[str, str] = {
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "mg": "mg",
    "l": "L", "ltr": "L", "litre": "L", "liter": "L", "litres": "L", "liters": "L",
    "ml": "ml", "millilitre": "ml", "milliliter": "ml",
    "n": "N", "no": "N", "nos": "N", "pc": "N", "pcs": "N",
    "piece": "N", "pieces": "N", "u": "N", "unit": "N", "units": "N",
}

NON_METRIC_UNITS = (
    "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds",
    "gallon", "gallons", "pint", "pints", "quart", "quarts",
    "inch", "inches", "foot", "feet", "yard", "yards",
    "tola", "seer", "maund",
)

# Base-unit conversion for unit-price arithmetic
TO_BASE: dict[str, tuple[float, str]] = {
    "kg": (1000.0, "g"), "g": (1.0, "g"), "mg": (0.001, "g"),
    "L": (1000.0, "ml"), "ml": (1.0, "ml"),
    "N": (1.0, "N"),
}


def parse_currency(text: str | None) -> float | None:
    """Pull a rupee amount out of a declaration."""
    if not text:
        return None
    m = CURRENCY_RE.search(str(text))
    if m:
        raw = m.group(1) or m.group(2)
        try:
            return float(raw.replace(",", ""))    # strip grouping, keep the decimal point
        except (TypeError, ValueError):
            return None
    # No currency marker -- fall back to a bare number, still comma-grouped.
    m = re.search(_AMOUNT, str(text))
    try:
        return float(m.group(1).replace(",", "")) if m else None
    except (TypeError, ValueError):
        return None


def parse_quantity(text: str | None) -> tuple[float, str] | None:
    """Parse a net quantity into (value, canonical unit)."""
    if not text:
        return None
    m = QUANTITY_RE.search(str(text))
    if not m:
        return None
    try:
        value = float(m.group(1))
    except (TypeError, ValueError):
        return None
    unit = UNIT_CANONICAL.get(m.group(2).lower())
    return (value, unit) if unit else None


def to_base_units(value: float, unit: str) -> tuple[float, str] | None:
    """Convert to grams / millilitres / count for arithmetic comparison."""
    conv = TO_BASE.get(unit)
    if not conv:
        return None
    factor, base = conv
    return value * factor, base


DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})\b"), "dmy2"),
    (re.compile(r"\b(\d{1,2})[/\-.](\d{4})\b"), "my"),
    (re.compile(r"\b(\d{4})[/\-.](\d{1,2})\b"), "ym"),
    (
        re.compile(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*(\d{4})\b",
            re.IGNORECASE,
        ),
        "mon_y",
    ),
]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date(text: str | None) -> tuple[date, str] | None:
    """Parse a packaging date into (date, precision).

    Precision is 'day' or 'month'. Rule 6(1)(c) permits month-and-year only for
    manufacture, so losing that distinction would make the dates rule wrong.
    Day-first ordering is assumed, per Indian labelling convention.
    """
    if not text:
        return None
    s = str(text).strip()

    for pattern, kind in DATE_PATTERNS:
        m = pattern.search(s)
        if not m:
            continue
        try:
            if kind == "dmy":
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if mo > 12 and d <= 12:      # tolerate an mm/dd/yyyy pack
                    d, mo = mo, d
                return date(y, mo, min(d, 28) if d > 31 else d), "day"
            if kind == "dmy2":
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if mo > 12 and d <= 12:
                    d, mo = mo, d
                return date(2000 + y, mo, d), "day"
            if kind == "my":
                mo, y = int(m.group(1)), int(m.group(2))
                return date(y, mo, 1), "month"
            if kind == "ym":
                y, mo = int(m.group(1)), int(m.group(2))
                return date(y, mo, 1), "month"
            if kind == "mon_y":
                mo = MONTHS[m.group(1)[:3].lower()]
                return date(int(m.group(2)), mo, 1), "month"
        except (ValueError, KeyError):
            continue
    return None


def month_end(d: date) -> date:
    """Last day of a month-precision date.

    A pack marked "Best Before 03/2027" is compliant through 31 March, so
    treating it as 1 March would declare stock expired a month early -- and
    issue a penalty for goods that are perfectly lawful to sell.
    """
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


PINCODE_RE = re.compile(r"\b([1-9][0-9]{5})\b")
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?(?:1800[\s-]?\d{3}[\s-]?\d{4}|\b[6-9]\d{9}\b)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")


def today() -> date:
    return datetime.now().date()
