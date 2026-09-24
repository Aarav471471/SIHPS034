/**
 * Motion primitives.
 *
 * Animation here is functional, not decorative: it shows where a thing came
 * from, keeps a list from popping in all at once, and gives a number time to be
 * read as it changes. Everything is gated on `prefers-reduced-motion` — a user
 * who has asked for stillness gets the identical interface without movement,
 * not a degraded one.
 *
 * Springs over durations, because a spring settles at a physically plausible
 * rate regardless of how far it has to travel; a fixed duration looks wrong the
 * moment the distance changes.
 */
import {
  AnimatePresence, motion, useReducedMotion, useSpring,
  type HTMLMotionProps, type Transition, type Variants,
} from 'framer-motion';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export { AnimatePresence, motion };

// --------------------------------------------------------------- easing ----
export const SPRING: Transition = { type: 'spring', stiffness: 380, damping: 32, mass: 0.7 };
export const SPRING_SOFT: Transition = { type: 'spring', stiffness: 220, damping: 30 };
export const EASE: Transition = { duration: 0.28, ease: [0.16, 1, 0.3, 1] };
export const EASE_FAST: Transition = { duration: 0.16, ease: [0.16, 1, 0.3, 1] };

// -------------------------------------------------------------- variants ----
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: EASE },
  exit: { opacity: 0, y: -6, transition: EASE_FAST },
};

export const fade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: EASE },
  exit: { opacity: 0, transition: EASE_FAST },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  show: { opacity: 1, scale: 1, transition: SPRING },
  exit: { opacity: 0, scale: 0.98, transition: EASE_FAST },
};

/** Stagger children so a list reads as arriving, not blinking into existence. */
export const stagger = (delay = 0.045): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: delay, delayChildren: 0.02 } },
});

// ------------------------------------------------------------ components ----
/** Page-level entrance. Used once per route. */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  const still = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={still ? false : 'hidden'}
      animate="show"
      variants={fadeUp}
    >
      {children}
    </motion.div>
  );
}

/** Wraps a list so its children stagger in. Pair with <Item>. */
export function Stagger({
  children, className, delay = 0.045, as: Tag = 'div',
}: {
  children: ReactNode; className?: string; delay?: number;
  as?: 'div' | 'ul' | 'ol' | 'section';
}) {
  const still = useReducedMotion();
  const M = motion[Tag] as typeof motion.div;
  return (
    <M
      className={className}
      initial={still ? false : 'hidden'}
      animate="show"
      variants={stagger(delay)}
    >
      {children}
    </M>
  );
}

export function Item({
  children, className, as: Tag = 'div', ...rest
}: {
  children: ReactNode; className?: string;
  as?: 'div' | 'li' | 'article' | 'section';
} & Omit<HTMLMotionProps<'div'>, 'children' | 'className'>) {
  const M = motion[Tag] as typeof motion.div;
  return (
    <M className={className} variants={fadeUp} {...rest}>
      {children}
    </M>
  );
}

/** Card that lifts under the pointer. Subtle by design — 2px, not 8. */
export function Lift({
  children, className, disabled, ...rest
}: {
  children: ReactNode; className?: string; disabled?: boolean;
} & Omit<HTMLMotionProps<'div'>, 'children' | 'className'>) {
  const still = useReducedMotion();
  return (
    <motion.div
      className={className}
      whileHover={still || disabled ? undefined : { y: -2 }}
      whileTap={still || disabled ? undefined : { y: 0, scale: 0.995 }}
      transition={SPRING}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/**
 * A number that animates to its new value.
 *
 * Worth the complexity on a dashboard: when a figure changes on refresh, a
 * jump-cut is easy to miss entirely, while a short count draws the eye to
 * exactly the thing that moved.
 */
export function Counter({
  value, decimals = 0, prefix = '', suffix = '', className,
}: {
  value: number; decimals?: number; prefix?: string; suffix?: string; className?: string;
}) {
  const still = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const mounted = useRef(false);

  const format = (v: number) =>
    `${prefix}${v.toLocaleString('en-IN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}${suffix}`;

  const spring = useSpring(value, { stiffness: 90, damping: 22, mass: 0.9 });

  useEffect(() => spring.on('change', (v) => setDisplay(v)), [spring]);

  useEffect(() => {
    // The first render lands on the real figure immediately. Counting up on
    // page load renders the value briefly wrong (and briefly blank, before the
    // first frame commits) for no benefit -- the animation is meant to draw the
    // eye to a value that CHANGED, which only happens after mount.
    if (!mounted.current) {
      mounted.current = true;
      spring.jump(value);
      setDisplay(value);
      return;
    }
    if (still) {
      spring.jump(value);
      setDisplay(value);
    } else {
      spring.set(value);
    }
  }, [value, spring, still]);

  return <span className={className}>{format(display)}</span>;
}

/** Height-animated disclosure, for inline forms and expandable rows. */
export function Collapse({ open, children }: { open: boolean; children: ReactNode }) {
  const still = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={still ? false : { height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={still ? undefined : { height: 0, opacity: 0 }}
          transition={SPRING_SOFT}
          style={{ overflow: 'hidden' }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Backdrop + dialog, used by the command palette and any modal. */
export function Overlay({
  open, onClose, children, labelledBy,
}: {
  open: boolean; onClose: () => void; children: ReactNode; labelledBy?: string;
}) {
  const still = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    // Freeze the page behind the dialog so a scroll gesture does not move it.
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  // Rendered through a portal on <body>, not in place. An ancestor carrying
  // `backdrop-filter` (the sticky app header does) becomes the containing block
  // for its fixed-position descendants, which would trap this overlay inside the
  // header's own 52px box -- the dialog overflows and, worse, the click-catching
  // backdrop only covers the header, so clicking the page does not dismiss it.
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]"
          initial={still ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={EASE_FAST}
        >
          <div
            className="absolute inset-0 bg-ink/50 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={labelledBy}
            className="relative w-full max-w-xl"
            initial={still ? false : { opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={still ? undefined : { opacity: 0, scale: 0.98, y: -4 }}
            transition={SPRING}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
