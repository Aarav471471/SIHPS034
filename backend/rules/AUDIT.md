# Rules engine — legal audit

Audited 2026-09-08 against the Legal Metrology (Packaged Commodities) Rules 2011
and its amendments. Seven defects were found and fixed. This file records what
changed, on what authority, and what is still open.

## Sources used

The gazette PDF on `consumeraffairs.gov.in` could not be retrieved during the
audit (TLS certificate failure from the audit environment). The corrections below
rest on secondary sources that reproduce the text and agree with each other:

- Full text of the Rules — Indian Kanoon [doc/100694501](https://indiankanoon.org/doc/100694501/)
- Rule 7 in isolation — Indian Kanoon [doc/151004919](https://indiankanoon.org/doc/151004919/)
- Amendment history — [iPleaders](https://blog.ipleaders.in/legal-metrology-packaged-commodities-rules-2011/),
  [King Stubb & Kasiva on the 2021/2022 amendments](https://ksandk.com/legal-metrology/packaged-commodities-rules-2022/)

**The gazette remains the authority.** Anything below that carries a penalty
should be confirmed against it before this system issues a real notice.

## Defects found and fixed

### 1. Character-height rule cited the wrong rule
`rule_font_height.py` cited *Rule 11 r/w Second Schedule*. The height provisions
are **Rule 7** — "Principal Display Panel — its area, size and letter etc.":
Rule 7(2) for numerals, Rule 7(3) for letters. Rule 11 concerns excluding wrapper
weight and prohibiting words like "about" and "approximately".

### 2. The Second Schedule table was wrong in every row
Coded thresholds were 100 / 300 / 600 cm². Actual Table I is 50 / 100 / 500 /
2500 cm², with different heights:

| Panel area (cm²) | Was | Now (Table I) | Blown/moulded |
|---|---|---|---|
| < 50 | 1.0 | 1.0 | 1.5 |
| 50–100 | 1.0 | 1.5 | 3.0 |
| 100–500 | 2.0 | 2.5 | 4.0 |
| 500–2500 | 4.0 | 4.0 | 6.0 |
| > 2500 | 6.0 | 6.0 | 6.0 |

The old table erred in both directions — over-strict on a 400 cm² panel,
under-strict on a 250 cm² one.

### 3. Table II was missing entirely
The Schedule has two tables. Table I governs quantities declared by weight or
volume; **Table II** governs length, area and number. The old single table was
closest to Table II and was being applied to everything. `schedule_for()` now
selects on the parsed unit of the net-quantity declaration, defaulting to
Table I — the stricter of the two at every overlapping area, so an unrecognised
unit is not quietly given the easier standard.

### 4. Rule 7(3) was not implemented
A floor for **letters** that does not scale with panel area: 1 mm, or 2 mm when
blown, formed, moulded, embossed or perforated. Added as `LetterHeightRule`
(`R-LETTER-HEIGHT`), registered as `letter_height` in the universal pipeline. The
pipeline already measures a height for every extracted field, so it has real
input.

### 5. Unit sale price cited a superseded sub-rule
Cited *Rule 6(2)*. Unit sale price was substituted into **Rule 6(11)** by the
Legal Metrology (Packaged Commodities) Amendment Rules 2021, in force
1 October 2022. Rule 6(2) is a different sub-rule.

### 6. Unit-price arithmetic ignored the prescribed denominator
Rule 6(11) fixes the unit of comparison rather than leaving it to the packer:
per gram below 1 kg and per kilogram above; per millilitre below 1 litre and per
litre above; per centimetre below 1 metre and per metre above; per number where
sold by number — rounded to two decimal places.

The old code computed in whichever base unit it derived and accepted either
member of the pair as equally valid. It now computes against the prescribed unit.
A pack whose figure is arithmetically correct but expressed in the other unit
gets a **WARNING with no penalty**, not a FAIL — it is a real non-conformity but
a trivial one, and the distinction matters when the output is a statutory notice.

Also implemented: the **second proviso**, under which no separate unit sale price
is required where it equals the retail sale price.

### 7. Principal-display-panel rule cited Rule 9
`rule_multi_surface.py` cited *Rule 9* for panel placement. Rule 7 defines the
principal display panel and what must appear on it; Rule 9 governs how
declarations are printed — legibility, contrast, script. Now cited as
*Rule 7 r/w Rule 9*.

## A correction that was not made

The small-package exemption (below 10 g / 10 ml) was initially removed as
unsupported, then **restored** — it is real, but it comes from **Rule 26**, which
exempts such packages from the Rules, with the unit-sale-price exemption aligned
to it. The earlier code carried the right thresholds under the wrong citation.
Tobacco is carved out by proviso and is excluded from the exemption in code.

The existing test caught this, which is the argument for the test suite asserting
outcomes rather than implementation.

## Still open

- **Gazette confirmation.** Everything above rests on secondary sources.
- **Rule 26 is broader than unit price.** It exempts qualifying packages from the
  Rules generally, not just from the unit-price requirement. The other rules still
  run against sub-10 g packs. Whether that is right depends on a reading of the
  proviso that should be settled against the gazette before it is changed —
  narrowing the whole pipeline on a secondary source would be the wrong risk to take.
- **Unreviewed amendments.** 2017, 2020, the Third Amendment 2022, an amendment
  effective 1 June 2023 (combination and group packages), and a Second Amendment
  2025. Any of these may touch Rule 6 or the Schedule.
- **Penalty amounts are modelled, not statutory.** The per-rule figures in each
  rule class are plausible but are not drawn from the penalty schedule of the
  Legal Metrology Act 2009, which varies by offence and by whether the
  contravention is a repeat. They should not be presented as statutory.
