# Attribution

This skill's structure and several of its ideas are adapted from **taste-skill**
by Leonxlnx — https://github.com/Leonxlnx/taste-skill — used under the MIT
Licence (© 2026 Leonxlnx).

What was taken:

- The **design-read step**: state what kind of screen this is and who uses it
  before styling anything.
- The **three-dial framing** (`DESIGN_VARIANCE` / `MOTION_INTENSITY` /
  `VISUAL_DENSITY`) as a way to make aesthetic intent explicit and arguable.
- The **forbidden animation patterns** — scroll listeners writing to React
  state, `requestAnimationFrame` loops driving re-renders, animating
  layout-triggering properties.
- The **"AI tells"** idea: a checklist of the specific visual and content
  habits that make generated UI recognisable.

What was deliberately changed:

taste-skill scopes itself to *"landing pages, portfolios, and redesigns — not
dashboards, not data tables, not multi-step product UI."* MetriX is precisely
the excluded case: a dense government enforcement console. Its high-variance,
asymmetric-layout defaults would make this product harder to use, so the dials
are recalibrated downward on variance and upward on density, and the rules are
rewritten around evidence integrity, sample sizes, and one-handed field use.

No text or code was copied verbatim. The reference material describes the
MetriX codebase's own tokens, primitives, and conventions.
