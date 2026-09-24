"""Rules engine verification.

Each case states the declarations on a hypothetical pack and the finding the
engine must reach.  These are the assertions that matter most in the whole
project: a wrong verdict here becomes a wrongful statutory notice.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.enums import ViolationStatus  # noqa: E402
from rules.base import RuleContext  # noqa: E402
from rules.registry import RULE_CLASSES, evaluate, pipeline_for  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name, detail))
    return ok


def ctx(**kw) -> RuleContext:
    """Build a context, defaulting to a fully compliant biscuit pack."""
    fields = {
        "mrp": "MRP Rs. 10.00 (Incl. of all taxes)",
        "net_quantity": "Net Qty: 250 g",
        "unit_price": "Unit Sale Price: Rs. 0.0400 per g",
        "mfg_date": "03/2026",
        "expiry_date": "03/2027",
        "manufacturer_name": "Mfd by: Parle Products Pvt Ltd",
        "manufacturer_address": "Vile Parle East, Mumbai, Maharashtra - 400057",
        "country_of_origin": "Country of Origin: India",
        "customer_care": "Consumer Care: 1800-123-4567 | care@parle.example",
        "fssai_licence": "10013022001234",
    }
    fields.update(kw.pop("fields", {}))
    for k in list(kw.get("drop", []) or []):
        fields[k] = None
    kw.pop("drop", None)

    defaults = dict(
        fields=fields,
        surfaces=["FRONT", "BACK"],
        surface_area_cm2=216.0,           # 12 x 18 cm
        package_width_cm=12.0,
        package_height_cm=18.0,
        # 216 cm2 panel, quantity by weight -> Table I requires 2.5 mm numerals
        # and Rule 7(3) requires 1.0 mm lettering.
        font_heights_mm={
            "mrp": 4.0, "net_quantity": 3.2, "unit_price": 2.6,
            "manufacturer_name": 1.8, "manufacturer_address": 1.4,
            "country_of_origin": 1.2, "customer_care": 1.2,
        },
        category_slug="biscuits-cookies",
        inspection_date=date(2026, 9, 7),
    )
    defaults.update(kw)
    return RuleContext(**defaults)


def rule_status(ev, rule_id: str) -> str | None:
    for r in ev.results:
        if r.rule_id == rule_id:
            return r.status
    return None


def find(ev, rule_id: str):
    for r in ev.results:
        if r.rule_id == rule_id:
            return r
    return None


def main() -> int:
    # ------------------------------------------------ fully compliant pack --
    ev = evaluate(ctx())
    check("compliant pack passes every rule",
          ev.compliance_status == "COMPLIANT" and not ev.failures,
          f"score={ev.score} rules={len(ev.results)} fails={len(ev.failures)} "
          f"warns={len(ev.warnings)}")
    check("compliant pack scores highly", ev.score >= 90, f"score={ev.score}")

    # ------------------------------------------------------- missing fields --
    for field_name, rule_id, label in [
        ("mrp", "R-MRP-FORMAT", "MRP"),
        ("net_quantity", "R-NET-QTY", "net quantity"),
        ("unit_price", "R-UNIT-PRICE", "unit price"),
        ("mfg_date", "R-MFG-DATE", "manufacture date"),
        ("manufacturer_name", "R-MANUFACTURER", "manufacturer"),
        ("country_of_origin", "R-COUNTRY-ORIGIN", "country of origin"),
        ("customer_care", "R-CUSTOMER-CARE", "consumer care"),
        ("fssai_licence", "R-FSSAI", "FSSAI licence"),
    ]:
        ev = evaluate(ctx(drop=[field_name]))
        r = find(ev, rule_id)
        check(f"missing {label} -> FAIL",
              r is not None and r.status == ViolationStatus.FAIL,
              f"{rule_id}: {(r.discrepancy if r else 'rule did not run')}")

    # -------------------------------------------------- MRP inclusive taxes --
    ev = evaluate(ctx(fields={"mrp": "MRP Rs. 10.00"}))
    r = find(ev, "R-MRP-FORMAT")
    check("MRP without inclusive-of-taxes wording -> WARNING",
          r.status == ViolationStatus.WARNING, r.discrepancy or "")

    ev = evaluate(ctx(fields={"mrp": "MRP Rs. 10.00 + GST extra"}))
    r = find(ev, "R-MRP-FORMAT")
    check("MRP declared exclusive of taxes -> CRITICAL FAIL",
          r.status == ViolationStatus.FAIL and r.severity == "CRITICAL",
          f"penalty=Rs.{r.penalty_amount:,.0f}")

    # ------------------------------------------------------- non-metric unit --
    ev = evaluate(ctx(fields={"net_quantity": "Net Wt 8.8 oz"}))
    r = find(ev, "R-NET-QTY")
    check("non-metric net quantity -> FAIL (Rule 8)",
          r.status == ViolationStatus.FAIL and "oz" in (r.discrepancy or ""),
          r.discrepancy or "")

    # ------------------------------------------- unit price arithmetic check --
    ev = evaluate(ctx(fields={"unit_price": "Unit Sale Price: Rs. 0.99 per g"}))
    r = find(ev, "R-UNIT-PRICE")
    check("wrong unit price arithmetic -> FAIL",
          r.status == ViolationStatus.FAIL, r.discrepancy or "")
    check("wrong unit price flags contested (peer-review trigger)",
          ev.has_contested_unit_price,
          f"expected {r.expected_value}, declared {r.calculated_value}")

    # Rule 6(11) prescribes the denominator: per gram below 1 kg. A per-kg
    # figure on a 250 g pack is arithmetically correct but not the prescribed
    # unit, so it is advisory rather than a penalty.
    ev = evaluate(ctx(fields={"unit_price": "Rs. 40.00 per kg"}))
    r = find(ev, "R-UNIT-PRICE")
    check("unit price per kg on a sub-1kg pack -> advisory, not penalty",
          r.status == ViolationStatus.WARNING and r.penalty_amount in (None, 0),
          "Rule 6(11) prescribes per g below 1 kg; arithmetic itself is right")

    # Small-pack exemption
    ev = evaluate(ctx(fields={"net_quantity": "Net Qty: 8 g", "unit_price": None},
                      font_heights_mm={"mrp": 2.0, "net_quantity": 2.0}))
    r = find(ev, "R-UNIT-PRICE")
    check("sub-10g pack exempt from unit price (Rule 26) -> PASS",
          r.status == ViolationStatus.PASS, "8 g is below the 10 g threshold at which Rule 26 exempts the package")

    # ------------------------------------------------------- expired stock --
    ev = evaluate(ctx(fields={"expiry_date": "15/02/2025", "mfg_date": "01/2025"}))
    r = find(ev, "R-EXPIRED-STOCK")
    check("expired stock -> CRITICAL FAIL",
          r.status == ViolationStatus.FAIL and r.severity == "CRITICAL",
          f"{r.calculated_value}, penalty Rs.{r.penalty_amount:,.0f}")

    # Month-precision expiry is valid to the END of that month.
    ev = evaluate(ctx(fields={"expiry_date": "09/2026"},
                      inspection_date=date(2026, 9, 7)))
    r = find(ev, "R-EXPIRED-STOCK")
    check("month-precision expiry valid to month end -> not expired",
          r.status != ViolationStatus.FAIL,
          "Best Before 09/2026 inspected 07/09/2026 is still within shelf life")

    ev = evaluate(ctx(fields={"expiry_date": "08/2026"},
                      inspection_date=date(2026, 9, 7)))
    r = find(ev, "R-EXPIRED-STOCK")
    check("previous month expiry -> expired",
          r.status == ViolationStatus.FAIL, r.calculated_value or "")

    # Contradictory dates
    ev = evaluate(ctx(fields={"mfg_date": "06/2026", "expiry_date": "01/2026"}))
    r = find(ev, "R-EXPIRY-DATE")
    check("expiry before manufacture -> FAIL", r.status == ViolationStatus.FAIL,
          r.discrepancy or "")

    # Future manufacture date
    ev = evaluate(ctx(fields={"mfg_date": "12/2027"}))
    r = find(ev, "R-MFG-DATE")
    check("future manufacture date -> FAIL", r.status == ViolationStatus.FAIL,
          r.discrepancy or "")

    # --------------------------------------------------------- PIN code -----
    ev = evaluate(ctx(fields={"manufacturer_address": "Vile Parle East, Mumbai"}))
    r = find(ev, "R-PINCODE")
    check("address without PIN code -> FAIL", r.status == ViolationStatus.FAIL,
          r.discrepancy or "")

    # ----------------------------------------------------- font height -------
    ev = evaluate(ctx(font_heights_mm={"mrp": 1.4, "net_quantity": 1.4, "unit_price": 1.4}))
    r = find(ev, "R-FONT-HEIGHT")
    check("undersized declarations -> FAIL (Rule 11)",
          r.status == ViolationStatus.FAIL,
          f"{r.calculated_value} vs required {r.expected_value} "
          f"for a {r.metadata['panel_area_cm2']} cm2 panel")

    # Height schedule scales with panel area.
    ev = evaluate(ctx(surface_area_cm2=80.0, package_width_cm=8.0, package_height_cm=10.0,
                      font_heights_mm={"mrp": 1.4, "net_quantity": 1.4}))
    r = find(ev, "R-FONT-HEIGHT")
    check("same height passes on a small panel",
          r.status == ViolationStatus.PASS,
          "1.4 mm meets the 1.0 mm minimum for an 80 cm2 panel")

    # No physical scale -> refuse to measure rather than guess.
    ev = evaluate(ctx(font_heights_mm={}))
    r = find(ev, "R-FONT-HEIGHT")
    check("no measurable height -> WARNING, not a fabricated finding",
          r.status == ViolationStatus.WARNING and r.penalty_amount is None,
          "reports 'not assessable' rather than inventing a measurement")

    # --------------------------------------------------- multi-surface ------
    # net_quantity IS a principal-panel field, so its absence from the only
    # captured surface is exactly the ambiguous case the guard exists for.
    ev = evaluate(ctx(surfaces=["FRONT"], drop=["net_quantity"]))
    r = find(ev, "R-MULTI-SURFACE")
    check("single surface -> absence reported as unproven, not a violation",
          r.status == ViolationStatus.WARNING and r.penalty_amount is None,
          "protects against a wrongful notice from an incomplete capture")

    # With both panels captured, the same absence IS a substantiated finding.
    ev = evaluate(ctx(surfaces=["FRONT", "BACK"], drop=["net_quantity"]))
    r = find(ev, "R-MULTI-SURFACE")
    check("absence across multiple surfaces -> substantiated FAIL",
          r.status == ViolationStatus.FAIL and r.penalty_amount,
          f"penalty Rs.{r.penalty_amount:,.0f} once capture coverage is adequate")

    # ------------------------------------------------ category pipelines ----
    food = pipeline_for("biscuits-cookies")
    nonfood = pipeline_for("stationery")
    check("food pipeline includes FSSAI + dates", "fssai" in food and "expiry_date" in food,
          f"{len(food)} rules")
    check("stationery pipeline excludes FSSAI + expiry",
          "fssai" not in nonfood and "expiry_date" not in nonfood,
          f"{len(nonfood)} rules -- no food licence demanded of pencils")

    ev = evaluate(ctx(category_slug="stationery",
                      fields={"fssai_licence": None, "expiry_date": None,
                              "mfg_date": None}))
    check("non-food pack not penalised for missing food declarations",
          not any(r.rule_id in ("R-FSSAI", "R-EXPIRY-DATE") for r in ev.failures),
          f"score={ev.score} fails={[r.rule_id for r in ev.failures]}")

    # ------------------------------------------- pre-certification advisory --
    ev = evaluate(ctx(drop=["mrp", "net_quantity"], is_pre_certification=True))
    check("pre-certification produces findings with no penalties",
          len(ev.failures) > 0 and ev.total_penalty == 0.0,
          f"{len(ev.failures)} findings, penalty exposure Rs.{ev.total_penalty:,.0f}")

    # ------------------------------------------------------- penalties -------
    ev = evaluate(ctx(fields={"expiry_date": "15/02/2025", "mfg_date": "01/2025"},
                      drop=["mrp"]))
    check("penalties accumulate across findings", ev.total_penalty >= 100_000,
          f"Rs.{ev.total_penalty:,.0f} across {len(ev.failures)} failures")

    # ---------------------------------------------------------- catalogue ----
    check("all 14 rule modules registered", len(RULE_CLASSES) == 14,
          ", ".join(sorted(RULE_CLASSES)))

    # ------------------------------------------------------------ report ----
    width = max(len(n) for _o, n, _d in results)
    print("\n" + "=" * 104)
    print("  RULES ENGINE VERIFICATION")
    print("=" * 104)
    for ok, name, detail in results:
        print(f"  [{'+' if ok else 'x'}] {name:<{width}}  {detail}")
    failed = sum(1 for ok, _n, _d in results if not ok)
    print("=" * 104)
    print(f"  {len(results) - failed}/{len(results)} passed" + (f", {failed} FAILED" if failed else ""))
    print("=" * 104 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
