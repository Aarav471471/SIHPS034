---
name: metrix-ui-motion
description: >-
  Build and refine UI for the MetriX Legal Metrology platform — screens,
  components, layouts, dashboards, forms, and animations. Use this whenever the
  task touches the web app or the Expo mobile app — adding a page or screen,
  restyling something, "make this look better / more professional / less
  AI-generated / less vibe-coded", adding motion, transitions, hover states,
  loading states, empty states, dark mode, or any Framer Motion work. Also use
  it when reviewing UI code for consistency. It carries the project's design
  tokens, component inventory, and motion rules, so reach for it before writing
  any JSX or Tailwind classes rather than inventing a parallel style vocabulary.
---

# MetriX UI & Motion

MetriX is a **government enforcement console**, not a landing page. A Legal
Metrology officer uses it standing in a shop with one hand; a ministry analyst
uses it to decide policy. That audience sets every decision below.

Adapted from the MIT-licensed [taste-skill](https://github.com/Leonxlnx/taste-skill)
library by Leonxlnx — specifically its design-read discipline, dial system, and
anti-slop bans. Recalibrated deliberately: taste-skill scopes itself to *"landing
pages, portfolios, and redesigns — not dashboards, not data tables, not
multi-step product UI"*, which is exactly what MetriX is. Applying its
asymmetric-layout and high-variance defaults here would produce a beautiful,
unusable enforcement tool.

---

## 1. Read the screen before styling it

State this in one line before writing code:

> **"Reading this as: \<screen kind> for \<who uses it, where>, optimising for \<what they need in the first 3 seconds>."**

Examples that should change your output:

- *"Officer capture screen, used one-handed in a shop with poor light — optimising for a thumb-reachable shutter and a legible readiness signal."*
- *"Ministry clause-rate chart, used in a review meeting — optimising for ranking accuracy and a readable denominator."*
- *"Brand dispute portal, opened once from an emailed link by someone who may be about to be fined — optimising for the evidence being unmissable and the appeal path obvious."*

If the read genuinely diverges, ask **one** question. If you can infer it, don't ask.

### The three dials, calibrated for this product

taste-skill's baseline is `VARIANCE 8 / MOTION 6 / DENSITY 4` — tuned for
marketing sites. MetriX runs much lower on variance and higher on density,
because scanability beats surprise in a tool people use all day.

| Surface | VARIANCE | MOTION | DENSITY | Why |
|---|---|---|---|---|
| Officer dashboard / queues | 3 | 4 | 6 | Repeated daily; symmetry makes it scannable |
| Capture / camera | 2 | 5 | 3 | One-handed, high-stakes, minimal chrome |
| Policy dashboards | 3 | 3 | 7 | Dense data; motion must not distract from figures |
| Consumer scan | 4 | 6 | 4 | Public-facing; a little warmth earns trust |
| Dispute portal | 2 | 2 | 5 | Someone may be fined on this page. Sober. |
| Login / marketing panel | 6 | 6 | 3 | The one place expressiveness is appropriate |

**Never exceed MOTION 6 on a screen that shows evidence or a penalty figure.**
Animation that draws the eye away from a cited violation is actively harmful.

---

## 2. Use what exists. Do not build a parallel vocabulary.

The single biggest failure mode is inventing new styles alongside the system —
a `bg-slate-800` here, a hand-rolled card there. Within two screens the app
looks assembled by three different people.

**Before writing any component, read `references/inventory.md`.** It lists every
primitive, token, and CSS class with its signature. If something close exists,
use it. If nothing fits, extend the system in `web/src/components/ui.tsx` so the
next screen inherits it — don't solve it locally.

Quick orientation:

| Need | Reach for |
|---|---|
| Any panel or container | `<Card>` or the `.surface` class |
| Page title block | `<PageHeader title subtitle action eyebrow>` |
| Sub-section with heading | `<Section title subtitle action>` |
| A number that matters | `<Stat label value hint tone icon>` |
| Compliance score 0–100 | `<ScoreRing score size>` |
| Status / severity / badge | `<StatusChip>`, `<SeverityChip>`, `<ComplianceBadge>` |
| Inline notice | `<Callout tone="warn\|bad\|ok\|info">` |
| Loading | `<Loading rows variant="list\|stats">` |
| Nothing to show | `<Empty title hint action icon>` |
| Request failed | `<ErrorBox error retry>` |
| Rate / progress bar | `<Meter value tone>` |
| Money, dates | `money()`, `moneyShort()`, `when()`, `ago()` |

Buttons and inputs are CSS classes, not components: `.btn-primary`,
`.btn-ghost`, `.btn-subtle`, `.btn-danger`, `.btn-ok` (with `.btn-sm` / `.btn-lg`),
`.input`, `.label`, `.chip`.

---

## 3. Colour comes from tokens, always

Every colour is a CSS variable exposed as a Tailwind class. Light and dark are
one definition apart, so a component written against tokens works in both
without a `dark:` variant.

```
Surfaces   bg-bg  bg-surface  bg-surface-hover  bg-surface-sunk
Borders    border-line  border-line-strong
Text       text-ink  text-ink-soft  text-ink-muted  text-ink-faint
Brand      bg-accent  text-accent  bg-accent-soft  text-accent-fg
Semantic   ok  warn  bad  info      (each has a -soft companion)
```

Opacity modifiers work: `bg-bad/10`, `ring-accent/20`, `text-warn/80`.

**Hardcoding a shade (`bg-slate-800`, `text-gray-500`, `#0f172a`) breaks dark
mode silently** — it looks fine in whichever theme you were viewing and wrong in
the other. If you need a colour the tokens don't cover, add it to both `:root`
and `.dark` in `web/src/index.css`.

Two exceptions where a raw colour is correct: overlay scrims on media
(`bg-black/60` over a camera feed) and a chart series palette, which is data
encoding rather than chrome.

---

## 4. Motion

Full patterns and the Framer Motion API surface are in
`references/motion.md`. Read it before writing any animation. The rules that
matter most:

**Springs, not durations.** A spring settles at a plausible rate whatever the
distance; a fixed duration looks wrong the moment the distance changes. Use the
exported `SPRING`, `SPRING_SOFT`, `EASE`, `EASE_FAST` rather than inventing
timings — five slightly different easings across an app reads as sloppiness even
when nobody can name why.

**Reduced motion is not optional.** Everything must respect
`useReducedMotion()`. The goal is that a user who asked for stillness gets the
*identical* interface without movement — not a degraded one. Every exported
primitive already handles this; if you hand-roll a `motion.div`, you own it.

**Animate `transform` and `opacity` only.** Animating `width`, `height`, `top`,
or `left` forces layout on every frame. The one sanctioned exception is
`height: auto` inside `<Collapse>`, which is why that primitive exists.

**Motion should explain, not decorate.** Ask what the animation tells the user.
A staggered list shows items arriving. A shared `layoutId` shows one thing
moving rather than two things swapping. A counter draws the eye to a figure that
*changed*. If the answer is "it looks nice", cut it — on a screen showing a
₹1,00,000 penalty, decoration reads as unseriousness.

**Never animate a value on first paint.** A count-up on mount shows the user a
number that is briefly wrong, and can flash empty before the first frame
commits. `<Counter>` lands on the true value at mount and animates only on
change. Apply the same logic to anything data-bearing.

Banned outright: `window.addEventListener('scroll')` and `requestAnimationFrame`
loops that touch React state — both re-render every frame. Use `useScroll`,
`useMotionValue`/`useTransform`, or IntersectionObserver.

---

## 5. Domain rules specific to enforcement

These come from the problem, not from taste, and outrank aesthetic preference.

- **Evidence is never decorated.** A cited pixel crop gets a plain border and a
  caption saying where it came from. No filters, no rounded-off cropping, no
  hover zoom that changes what the officer sees.
- **Show the denominator.** "28% violation rate" alone is misleading. Render it
  as `28% of 340 checks`. Every rate in this app has a sample size; omitting it
  is how a dashboard lies.
- **Absence has three states, not two.** *Not declared*, *not found on the
  captured surfaces*, and *not assessable* mean different things legally. Use
  the copy the API returns rather than collapsing them to "—".
- **Money and identifiers are monospace and tabular.** `.nums` for figures,
  `font-mono` for hashes, barcodes, licence numbers, session refs. Digits that
  don't align are hard to compare and easy to misread.
- **Confidence is always visible where a finding is.** If the pipeline was
  unsure, the UI says so next to the claim, not in a tooltip.
- **Destructive and legal actions need a written reason.** Peer-review decisions
  and appeal outcomes gate their buttons on a remarks field. That is a product
  requirement, not a nicety.

---

## 6. Anti-patterns

Borrowed from taste-skill's "AI tells" and narrowed to what actually shows up
in this codebase.

**Visual**
- Pure `#000` or `#fff` as a surface. Use `bg-bg` / `bg-surface`.
- Neon glows, heavy gradients, glassmorphism on everything. One soft light
  source on the login panel is the whole budget.
- A single hard `box-shadow`. The token shadows are layered for a reason.
- Emoji as UI iconography. Use `Icon.*` from `components/icons.tsx`.

**Layout**
- Three equal feature cards. On a dashboard, prefer a stat row plus a dense
  list, which is what the data actually is.
- Fixed pixel heights on anything containing text. It will overflow in another
  language or at another font size.
- Horizontal page scroll. Wide tables scroll inside their own
  `overflow-x-auto` container; the page never does.

**Content**
- Placeholder names like "John Doe" or brands like "Acme". This project has a
  seeded corpus of real-shaped Indian retail data — use it.
- Suspiciously round figures. Real data is `47.2%` and `₹9.75 L`.
- Filler verbs: "seamless", "elevate", "unleash", "next-gen".

**Code**
- Hand-rolled SVG icons when `Icon.*` has one.
- A new colour constant. See §3.
- `useState` for something the server owns — TanStack Query already caches it.

---

## 7. Before you call it done

- Look at it in **both themes**. Toggle with the header control or ⌘K → Theme.
- Look at it at **375px wide**. The officer surfaces are phone-first.
- Tab through it. Focus rings are defined; if you can't see where you are,
  something is overriding them.
- Turn on reduced motion (OS setting) and confirm nothing breaks or disappears.
- Run `npm run typecheck` in `web/`.

Then say plainly what you changed and what you deliberately left alone.

---

## Reference files

- `references/inventory.md` — every primitive, token, and CSS class with
  signatures and worked usage. Read before building a component.
- `references/motion.md` — motion primitives, Framer Motion patterns, worked
  examples, and the performance rules. Read before writing an animation.
