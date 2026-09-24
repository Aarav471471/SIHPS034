# Motion — primitives, patterns, and the rules behind them

Framer Motion is already installed and wrapped. Import from
`@/components/motion`, not from `framer-motion` directly — the wrapper
re-exports `motion` and `AnimatePresence` and adds the reduced-motion handling
that hand-rolled components keep forgetting.

**Contents**
1. [Timing constants](#1-timing-constants)
2. [Variants](#2-variants)
3. [Components](#3-components)
4. [Patterns](#4-patterns)
5. [Performance and banned patterns](#5-performance-and-banned-patterns)
6. [Reduced motion](#6-reduced-motion)
7. [Choosing whether to animate at all](#7-choosing-whether-to-animate-at-all)

---

## 1. Timing constants

```ts
SPRING       // stiffness 380, damping 32, mass 0.7 — UI response, hovers, dialogs
SPRING_SOFT  // stiffness 220, damping 30           — layout, height, larger travel
EASE         // 280ms, cubic-bezier(0.16, 1, 0.3, 1) — entrances
EASE_FAST    // 160ms, same curve                    — exits, hover tints
```

Two reasons to use these rather than typing a transition inline. A spring
settles at a physically plausible rate whatever the distance, so it stays right
when the layout changes; a fixed duration looks wrong the moment the travel
distance does. And five slightly different easings across an app is one of the
things that reads as "unfinished" even when nobody can point at why.

Exits are faster than entrances (160 vs 280ms). Something leaving should get
out of the way; something arriving deserves to be seen.

---

## 2. Variants

```ts
fadeUp   // opacity 0 → 1, y 10 → 0, exits upward by 6px
fade     // opacity only
scaleIn  // opacity + scale 0.97 → 1, springs
stagger(delay = 0.045)  // parent orchestration variant
```

The child variants use the names `hidden` / `show` / `exit`. If you write your
own variant object, use those names so it composes with `Stagger` and `Item`.

---

## 3. Components

### `<Page>`
Route-level entrance. One per route, wrapping the whole page body.
```tsx
<Page className="space-y-5">…</Page>
```

### `<Stagger>` + `<Item>`
A list that reads as arriving rather than blinking into existence.
```tsx
<Stagger as="ul" className="space-y-2" delay={0.045}>
  {rows.map((r) => <Item as="li" key={r.id}>…</Item>)}
</Stagger>
```
`as` accepts `div | ul | ol | section` on `Stagger` and `div | li | article |
section` on `Item`. **`Stat` is already an `Item`** — drop it straight into a
`Stagger` without wrapping.

Keep the total stagger under about 300ms. At 45ms a stagger of eight items
finishes in 360ms, which is already the ceiling; for a twenty-row queue lower
the delay to ~0.02 rather than making the user wait for row twenty.

### `<Lift>`
Pointer hover lift, 2px. Used by `Card interactive`.
```tsx
<Lift disabled={!clickable}><div className="surface">…</div></Lift>
```
2px, not 8. A card that leaps at the cursor is a marketing tell.

### `<Counter>`
A figure that animates when it changes.
```tsx
<Counter value={score} decimals={1} prefix="₹" className="nums" />
```
It lands on the true value at mount and animates only on change. This matters:
counting up on page load shows a number that is briefly wrong (and briefly
blank, before the first spring frame commits) for no benefit — the animation
exists to draw the eye to a value that *changed*, which can only happen after
mount. Apply the same reasoning to anything else data-bearing you animate.

Formats with `en-IN` grouping. Use `.nums` alongside it so the width does not
jitter as digits change.

### `<Collapse>`
Height disclosure for inline forms and expandable rows.
```tsx
<Collapse open={open}>{detail}</Collapse>
```
This is the sanctioned exception to "never animate height" — it exists so the
exception lives in exactly one place. Do not animate height anywhere else.

### `<Overlay>`
Backdrop plus dialog. Handles Escape, click-outside, and body scroll locking.
```tsx
<Overlay open={open} onClose={close} labelledBy="dlg-title">
  <div className="surface-raised p-5">
    <h2 id="dlg-title">…</h2>
  </div>
</Overlay>
```
Pass `labelledBy` pointing at the heading id — the dialog is already
`role="dialog" aria-modal="true"` and needs the name to be usable with a screen
reader.

---

## 4. Patterns

### Shared element (the active nav pill)
One element moving reads as continuity; two elements cross-fading reads as a
glitch.
```tsx
{active && (
  <motion.span
    layoutId="nav-active"
    className="absolute inset-0 rounded-lg bg-accent-soft"
    transition={SPRING}
  />
)}
```
A `layoutId` must be unique per animating group. Two groups sharing a string
will fling an element across the screen.

### Entering and leaving lists
```tsx
<AnimatePresence initial={false}>
  {items.map((i) => (
    <motion.li key={i.id} variants={fadeUp}
               initial="hidden" animate="show" exit="exit" layout>
      …
    </motion.li>
  ))}
</AnimatePresence>
```
`initial={false}` suppresses the entrance on first render, so an already-loaded
list does not replay. Stable `key`s are required — an index key makes React
reuse the wrong node and the animation lies about what moved.

### Progress that reflects real work
Prefer a `Meter` bound to actual pipeline stage counts over an indeterminate
spinner. On a capture screen the officer needs to know whether to wait; a
spinner tells them nothing.

### Scroll-linked effects
```tsx
const { scrollYProgress } = useScroll();
const opacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);
return <motion.div style={{ opacity }} />;
```
`useScroll` and `useTransform` keep the value off the React render path. See §5
for what not to do instead.

---

## 5. Performance and banned patterns

**Animate `transform` and `opacity` only.** They are composited; `width`,
`height`, `top`, `left`, `margin` and `padding` force layout on every frame,
which on a mid-range Android phone in a shop is the difference between smooth
and unusable. `Collapse` is the one sanctioned exception, which is why it is a
primitive rather than something you write inline.

**Never do these** — borrowed from taste-skill's forbidden list, and they show
up in generated React constantly:

```tsx
// Re-renders the whole subtree on every scroll event.
window.addEventListener('scroll', () => setY(window.scrollY));

// Same problem, 60 times a second, forever.
useEffect(() => {
  const loop = () => { setFrame((f) => f + 1); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}, []);
```

Use `useScroll` / `useMotionValue` / `useTransform` (values live outside React
state) or `IntersectionObserver` for "animate when visible".

Other things to avoid: animating more than ~20 elements at once; `filter:
blur()` on anything animating; `layout` on a long list where only one row
changed (scope it to the row); nesting `AnimatePresence` more than one level
deep.

---

## 6. Reduced motion

Two layers, both already in place:

1. `index.css` collapses all CSS animation and transition durations under
   `@media (prefers-reduced-motion: reduce)`.
2. Every primitive here calls `useReducedMotion()` and passes `initial={false}`
   so the element renders at its final state rather than never appearing.

If you hand-roll a `motion.div`, you own the second layer:
```tsx
const still = useReducedMotion();
<motion.div initial={still ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} />
```

The bar is that a user who asked for stillness gets the *identical* interface
without movement — not a degraded one, and never an element that fails to
appear because its entrance was skipped. Test it: turn on the OS reduce-motion
setting and walk the screen.

---

## 7. Choosing whether to animate at all

Before adding motion, answer what it tells the user. Legitimate answers:

- *This list is arriving* — stagger
- *This is the same thing, moved* — shared `layoutId`
- *This number changed* — `Counter`
- *This came from that* — scale/position origin on a dialog or popover
- *Work is happening and here is how much is left* — `Meter`

"It looks nice" is not one. MetriX shows evidence, findings and penalty
figures; motion that pulls the eye away from a cited violation is worse than no
motion, and decoration on a screen that may lead to a fine reads as
unseriousness.

Screens that should stay near-still: the dispute portal, evidence viewers, and
anything displaying a penalty amount or a legal citation. Screens with room for
expression: login, the consumer scan result, and empty states.
