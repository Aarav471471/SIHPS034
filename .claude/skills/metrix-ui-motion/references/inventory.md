# Inventory — tokens, primitives, classes

Everything the MetriX web app is built from. Read this before writing a
component; almost everything you need already exists, and the second copy of a
thing is what makes an app look inconsistent.

**Contents**
1. [Design tokens](#1-design-tokens)
2. [CSS component classes](#2-css-component-classes)
3. [React primitives — components/ui.tsx](#3-react-primitives--componentsuitsx)
4. [Icons](#4-icons)
5. [App-level components](#5-app-level-components)
6. [Formatters](#6-formatters)
7. [Data, state and layout conventions](#7-data-state-and-layout-conventions)
8. [Worked example](#8-worked-example)

---

## 1. Design tokens

Defined in `web/src/index.css` as HSL triplets (so Tailwind opacity modifiers
work), mapped to Tailwind names in `web/tailwind.config.js`. Light lives on
`:root`, dark on `.dark` — a component written against tokens needs no `dark:`
variant.

| Tailwind class | Variable | Use for |
|---|---|---|
| `bg-bg` | `--bg` | Page background |
| `bg-bg-subtle` | `--bg-subtle` | Alternating page bands |
| `bg-surface` | `--surface` | Cards, panels, inputs |
| `bg-surface-hover` | `--surface-hover` | Row / button hover |
| `bg-surface-sunk` | `--surface-sunk` | Wells, meter tracks, icon tiles |
| `border-line` | `--border` | Every default border |
| `border-line-strong` | `--border-strong` | Hover / emphasis border |
| `text-ink` | `--text` | Primary text |
| `text-ink-soft` | `--text-soft` | Body copy, secondary |
| `text-ink-muted` | `--text-muted` | Labels, captions |
| `text-ink-faint` | `--text-faint` | Placeholders, disabled |
| `accent` | `--accent` | Brand, primary action |
| `accent-hover` / `accent-soft` / `accent-fg` | | Gradient top / tinted bg / text on accent |
| `ok` / `ok-soft` | | Compliant, success |
| `warn` / `warn-soft` | | Warning, seasonal risk |
| `bad` / `bad-soft` | | Violation, error, critical |
| `info` / `info-soft` | | Neutral notice, processing |
| `ring` | `--ring` | Focus outline (already set globally) |

Also `--radius` (0.75rem, consumed by `.surface`) and layered shadows
`--shadow-xs / -sm / -md / -lg / -xl`. The layering is deliberate — a single
hard `box-shadow` reads as a sticker rather than depth.

**The accent is a deep government blue in light mode and a lighter blue in
dark.** That is not an oversight: the authoritative navy that works on white is
unreadable on a dark surface. Never "fix" it by hardcoding one value.

Use a `-soft` token as the tinted background and the base token as the text and
border on top: `border-warn/25 bg-warn-soft text-warn`.

---

## 2. CSS component classes

`web/src/index.css`, `@layer components`. These are classes, not React
components — put them on whatever element is semantically right (`.btn-primary`
on a `button`, on an `a`, or on a `Link`).

**Surfaces**
- `.surface` — background + 1px border + radius + `--shadow-sm`. The default container.
- `.surface-raised` — same with `--shadow-md`, for things floating above content.
- `.panel` — sunk background, border, smaller radius. A well inside a card.
- `.divider` — 1px rule.
- `.sheen` — adds a hairline top highlight via `::before`. Pair with `.surface`
  on cards that should feel lit. This is the detail that separates a card from a
  rectangle; it is already inside `Card` and `Stat`.
- `.skeleton` — shimmering placeholder block. Size it with Tailwind (`h-3 w-20`).

**Buttons** — `.btn-primary` (gradient accent), `.btn-ghost` (surface + border),
`.btn-subtle` (transparent until hover), `.btn-danger`, `.btn-ok`. Size with
`.btn-sm` or `.btn-lg`; default height is 2.5rem. All handle `:disabled`.
Do not add your own hover transform — primary, danger and ok already lift 1px.

**Forms** — `.input` (works on `input`, `textarea` and `select`; the CSS
specialises each), `.label` (uppercase micro-label, includes its bottom margin).

**Chips** — `.chip` (pill, 11px semibold), `.chip-outline` (adds a border; you
set the colour).

**Utilities** — `.nums` (tabular figures — use on every number that sits in a
column or changes), `.text-balance`, `.text-pretty`, `.bg-grid` (hero areas
only), `.grid-fade`.

**Also in the Tailwind theme** (`web/tailwind.config.js`): `text-2xs`
(0.6875rem, the micro-label size used by `Stat` and chips); `font-sans` is
Inter and `font-mono` is JetBrains Mono; `rounded-lg/md/sm` are derived from
`--radius`, so use them instead of a pixel value; `shadow-xs…xl` map to the
layered shadow tokens; `animate-fade-up` and `animate-pulse-ring` exist for the
rare case where a CSS animation beats a Framer one (a live-capture indicator,
for instance). Note that Tailwind keys with a hyphen must be quoted in that
config file — an unquoted `pulse-ring:` is a JS syntax error that surfaces as a
confusing PostCSS failure pointing at `index.css`.

Leaflet is themed globally at the bottom of `index.css`, including a dark-mode
tile filter. Map markers use `L.divIcon` with inline styles because Leaflet
renders outside React — that is the one sanctioned place for raw hex.

---

## 3. React primitives — components/ui.tsx

```tsx
import { Card, Section, PageHeader, Stat, ScoreRing, StatusChip, SeverityChip,
         ComplianceBadge, Callout, Empty, Loading, ErrorBox, Meter,
         money, moneyShort, when, ago } from '@/components/ui';
```

`ui.tsx` also re-exports `Stagger`, `Item`, `Lift` and `Counter` from
`motion.tsx`, so a page usually needs only this one import.

| Component | Props | Notes |
|---|---|---|
| `ComplianceBadge` | `level?, score?, size?: 'sm'\|'md'` | GOLD / SILVER / BRONZE / STANDARD / FLAGGED |
| `SeverityChip` | `severity?` | CRITICAL / MAJOR / MINOR |
| `StatusChip` | `status?: string, dot?: boolean` | Knows ~20 API status strings; unknown values fall back to the PENDING style and underscores render as spaces. Add new statuses to the `STATUS` map rather than styling one inline. |
| `ScoreRing` | `score?, size?, label?` | 0–100. Colours itself: ≥90 ok, ≥70 warn, else bad. Sweeps on mount; renders `—` for null. |
| `Stat` | `label, value, hint?, tone?, icon?, delta?, className?` | The dashboard workhorse. `tone` ∈ default/good/warn/bad/accent, `icon` is an `Icon` key, `delta` renders a signed arrow. Already an `Item`, so put it inside a `Stagger`. |
| `Card` | `children, interactive?, className?` + div props | `interactive` wraps it in `Lift` and adds a hover border. |
| `Section` | `title, subtitle?, action?, children` | Sub-heading block with an action slot. |
| `PageHeader` | `title, subtitle?, action?, eyebrow?` | One per route, at the top. |
| `Empty` | `title, hint?, action?, icon?` | Say what would fill it and how, not just "no data". |
| `Loading` | `rows?, variant?: 'list'\|'stats'` | Skeletons mirror the real layout so nothing jumps on arrival. |
| `ErrorBox` | `error: unknown, retry?` | Takes a raw caught value and extracts the message. |
| `Callout` | `tone?: 'info'\|'warn'\|'bad'\|'ok', title?, icon?, children` | Inline notice; picks a default icon per tone. |
| `Meter` | `value: number, tone?, className?` | 0–100 bar, animates from 0. When `tone` is omitted it auto-tones by threshold, and that default assumes **higher is worse** (violation rates) — pass `tone` explicitly for a metric where high is good. |

The standard query-page skeleton:

```tsx
if (q.isLoading) return <Loading rows={4} />;
if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
```

---

## 4. Icons

`import { Icon } from '@/components/icons'` then `<Icon.shield size={18} />`.
All 24px viewBox, 1.75 stroke, round caps, `currentColor`, `aria-hidden`.
Default render size is 20.

```
dashboard camera route flag shield scan bell scale chart box check checkCircle
x alert info search chevronRight chevronDown arrowRight arrowUp arrowDown
minus plus map pin clock wifiOff upload file sun moon logout menu sparkle
building users rupee trending command
```

Hand-inlined on purpose — thirty glyphs do not justify an icon package. If you
need a new one, add it to this object at the same optical weight. Never reach
for an emoji, and never paste a one-off SVG into a page.

---

## 5. App-level components

- **`components/Shell.tsx`** — the authenticated layout: desktop sidebar with a
  shared-`layoutId` active pill, mobile bottom tab bar (five items maximum —
  beyond that the thumb targets get too small), offline banner, theme control,
  ⌘K hint. New routes are registered here.
- **`components/CommandPalette.tsx`** — ⌘K / Ctrl-K, grouped Navigate /
  Preferences / Account. Add an entry here whenever you add a route.
- **`components/motion.tsx`** — see `references/motion.md`.
- **`store/theme.ts`** — three-state theme (light / dark / system). `initTheme()`
  runs before React mounts so the first paint is already correct; never toggle
  the `.dark` class from a component.
- **`store/auth.ts`** — exports `api`, the typed `MetrixClient` from
  `packages/shared`. Requests go through it, never a bare `fetch`.
- **`lib/offlineQueue.ts`** — IndexedDB capture queue, resumable per surface.
  Anything that captures evidence goes through it, so a dropped connection in a
  shop basement does not lose an inspection.

---

## 6. Formatters

| Function | Output | Use |
|---|---|---|
| `money(v)` | `₹1,250.50` | Exact figures — price, MRP, penalty on a detail page |
| `moneyShort(v)` | `₹9.75 L`, `₹1.20 Cr` | Dashboard aggregates. Lakh/crore, not K/M |
| `when(iso)` | `07 Sep 2026` | Absolute dates |
| `ago(iso)` | `12m ago`, `3d ago`, then falls back to `when()` | Feeds, activity, queues |

All four return `—` for null. Never hand-format a rupee value with
`.toFixed()` — `en-IN` digit grouping differs from `en-US`, and getting it
wrong is immediately visible to an Indian user.

---

## 7. Data, state and layout conventions

- **Server state belongs to TanStack Query.** `useQuery` with a key array; do
  not copy results into `useState`. Local UI state (open/closed, selected tab)
  is `useState` or Zustand.
- **Rates carry denominators.** Render `28% of 340 checks`, not `28%`.
- **Money and identifiers are tabular.** `.nums` on figures; `font-mono` on
  hashes, barcodes, licence numbers and session references.
- **Common grids** — stat rows `grid gap-3 sm:grid-cols-2 lg:grid-cols-4`;
  detail splits `grid gap-4 lg:grid-cols-[1fr_1.1fr]`; page rhythm `space-y-5`,
  inside a section `space-y-3`.
- **Wide tables scroll themselves** (`overflow-x-auto` on the wrapper). The page
  body never scrolls horizontally.
- **Officer surfaces are mobile-first.** They are used on a phone in a shop.
  Check 375px before you check 1440px.

---

## 8. Worked example

A page that uses the system correctly — no new colours, no hand-rolled card, no
bespoke loading or empty state:

```tsx
import { useQuery } from '@tanstack/react-query';
import { Page } from '@/components/motion';
import { Card, Empty, ErrorBox, Loading, PageHeader, Section, Stagger, Stat,
         StatusChip, ago, moneyShort } from '@/components/ui';
import { api } from '@/store/auth';

export default function Violations() {
  const q = useQuery({ queryKey: ['violations'], queryFn: () => api.violations() });

  if (q.isLoading) return <Loading rows={4} variant="stats" />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;

  const d = q.data!;

  return (
    <Page className="space-y-5">
      <PageHeader
        title="Open violations"
        subtitle={`${d.items.length} of ${d.total_inspections} inspections flagged`}
        action={<button type="button" className="btn-primary">Export</button>}
      />

      <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Critical" value={d.critical} tone="bad" icon="alert"
              hint={`of ${d.total} findings`} />
        <Stat label="Penalty exposure" value={moneyShort(d.penalty_total)}
              icon="rupee" />
      </Stagger>

      <Section title="Most recent">
        {!d.items.length ? (
          <Empty
            title="Nothing open"
            hint="Findings appear here once an inspection has been verified."
          />
        ) : (
          <Stagger as="ul" className="space-y-2">
            {d.items.map((v) => (
              <Card key={v.id} interactive className="flex items-center gap-3 p-4">
                <StatusChip status={v.status} dot />
                <span className="min-w-0 flex-1 truncate font-semibold">{v.product}</span>
                <span className="nums text-xs text-ink-muted">{ago(v.created_at)}</span>
              </Card>
            ))}
          </Stagger>
        )}
      </Section>
    </Page>
  );
}
```
