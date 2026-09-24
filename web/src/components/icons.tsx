/**
 * Icon set.
 *
 * Hand-inlined rather than pulled from a package: the app uses roughly thirty
 * glyphs, and shipping an icon library for that is a hundred kilobytes to save
 * a few hundred lines. All are 24px, 1.75 stroke, round caps — a single optical
 * weight so they sit together.
 */
import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement> & { size?: number };

function S({ size = 20, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...rest}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  dashboard: (p: P) => (
    <S {...p}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></S>
  ),
  camera: (p: P) => (
    <S {...p}><path d="M3 8.5A2.5 2.5 0 0 1 5.5 6h1.7a1 1 0 0 0 .83-.45l.94-1.4A1 1 0 0 1 9.8 3.7h4.4a1 1 0 0 1 .83.45l.94 1.4A1 1 0 0 0 16.8 6h1.7A2.5 2.5 0 0 1 21 8.5v9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z" /><circle cx="12" cy="13" r="3.5" /></S>
  ),
  route: (p: P) => (
    <S {...p}><circle cx="6" cy="19" r="2.5" /><circle cx="18" cy="5" r="2.5" /><path d="M8.5 19h6a3.5 3.5 0 0 0 0-7h-5a3.5 3.5 0 0 1 0-7h6" /></S>
  ),
  flag: (p: P) => (
    <S {...p}><path d="M5 21V4" /><path d="M5 4.5c3-1.5 5.5 1.5 8.5 0S18 3 19 3.5v10c-1-.5-2.5 0-5.5 1.5S8 13.5 5 15" /></S>
  ),
  shield: (p: P) => (
    <S {...p}><path d="M12 22s8-3.6 8-9.4V5.6L12 2.6 4 5.6v7C4 18.4 12 22 12 22z" /><path d="m9 12 2 2 4-4" /></S>
  ),
  scan: (p: P) => (
    <S {...p}><path d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16" /><path d="M7 8v8M10.5 8v8M14 8v8M17 8v8" /></S>
  ),
  bell: (p: P) => (
    <S {...p}><path d="M18 8.5a6 6 0 1 0-12 0c0 6-2.5 7.5-2.5 7.5h17S18 14.5 18 8.5" /><path d="M13.7 20a2 2 0 0 1-3.4 0" /></S>
  ),
  scale: (p: P) => (
    <S {...p}><path d="M12 3v18M7 21h10M5 7h14l-1.5-2.5h-11z" /><path d="M5 7 2.5 13a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0z" /></S>
  ),
  chart: (p: P) => (
    <S {...p}><path d="M3 3v16.5A1.5 1.5 0 0 0 4.5 21H21" /><path d="m7 15 3.5-4 3 2.5L20 7" /></S>
  ),
  box: (p: P) => (
    <S {...p}><path d="M20.5 8.4v7.2a2 2 0 0 1-1 1.73l-6.5 3.6a2 2 0 0 1-2 0l-6.5-3.6a2 2 0 0 1-1-1.73V8.4a2 2 0 0 1 1-1.73l6.5-3.6a2 2 0 0 1 2 0l6.5 3.6a2 2 0 0 1 1 1.73z" /><path d="m3.8 7.4 8.2 4.5 8.2-4.5M12 21v-9.1" /></S>
  ),
  check: (p: P) => (<S {...p}><path d="m4.5 12.5 5 5 10-11" /></S>),
  checkCircle: (p: P) => (<S {...p}><circle cx="12" cy="12" r="9" /><path d="m8.5 12 2.5 2.5 4.5-5" /></S>),
  x: (p: P) => (<S {...p}><path d="m6 6 12 12M18 6 6 18" /></S>),
  alert: (p: P) => (<S {...p}><path d="M12 3.5 2.7 19.5a1 1 0 0 0 .87 1.5h16.86a1 1 0 0 0 .87-1.5z" /><path d="M12 9.5v4.5M12 17.5h.01" /></S>),
  info: (p: P) => (<S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 16v-4.5M12 8h.01" /></S>),
  search: (p: P) => (<S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.4-4.4" /></S>),
  chevronRight: (p: P) => (<S {...p}><path d="m9 5 7 7-7 7" /></S>),
  chevronDown: (p: P) => (<S {...p}><path d="m5 9 7 7 7-7" /></S>),
  arrowRight: (p: P) => (<S {...p}><path d="M4 12h15M13 6l6 6-6 6" /></S>),
  arrowUp: (p: P) => (<S {...p}><path d="M12 19V5M6 11l6-6 6 6" /></S>),
  arrowDown: (p: P) => (<S {...p}><path d="M12 5v14M6 13l6 6 6-6" /></S>),
  minus: (p: P) => (<S {...p}><path d="M5 12h14" /></S>),
  plus: (p: P) => (<S {...p}><path d="M12 5v14M5 12h14" /></S>),
  map: (p: P) => (
    <S {...p}><path d="M9 4 3 6.5v14L9 18l6 2.5 6-2.5v-14L15 6.5z" /><path d="M9 4v14M15 6.5v14" /></S>
  ),
  pin: (p: P) => (
    <S {...p}><path d="M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></S>
  ),
  clock: (p: P) => (<S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5V12l3 2" /></S>),
  wifiOff: (p: P) => (
    <S {...p}><path d="M2 3l20 20M8.6 15.4a5 5 0 0 1 6.3-.6M5 11.9a10 10 0 0 1 4-2.4M1.5 8.4A15 15 0 0 1 6 5.9M22.5 8.4a15 15 0 0 0-6.6-3.3M19 11.9a10 10 0 0 0-2-1.4M12 19h.01" /></S>
  ),
  upload: (p: P) => (
    <S {...p}><path d="M20 16.5v2A2.5 2.5 0 0 1 17.5 21h-11A2.5 2.5 0 0 1 4 18.5v-2" /><path d="M12 15V3M7.5 7.5 12 3l4.5 4.5" /></S>
  ),
  file: (p: P) => (
    <S {...p}><path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z" /><path d="M13.5 3v5.5H19" /></S>
  ),
  sun: (p: P) => (
    <S {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></S>
  ),
  moon: (p: P) => (<S {...p}><path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11z" /></S>),
  logout: (p: P) => (
    <S {...p}><path d="M9 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3" /><path d="M16 17l5-5-5-5M21 12H9" /></S>
  ),
  menu: (p: P) => (<S {...p}><path d="M4 7h16M4 12h16M4 17h16" /></S>),
  sparkle: (p: P) => (
    <S {...p}><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" /><path d="M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" /></S>
  ),
  building: (p: P) => (
    <S {...p}><path d="M4 21V6a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v15M14 10h4a2 2 0 0 1 2 2v9M2 21h20" /><path d="M7.5 8h2M7.5 12h2M7.5 16h2M17 14h.01M17 17.5h.01" /></S>
  ),
  users: (p: P) => (
    <S {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 5.2a3.5 3.5 0 0 1 0 5.6M18.5 20a6.5 6.5 0 0 0-2.2-4.9" /></S>
  ),
  rupee: (p: P) => (
    <S {...p}><path d="M7 4h10M7 8.5h10M15.5 4c0 4-2.8 4.5-5.5 4.5h-3l7.5 11.5" /></S>
  ),
  trending: (p: P) => (<S {...p}><path d="m3 16 5.5-5.5 3.5 3.5L21 5" /><path d="M15 5h6v6" /></S>),
  command: (p: P) => (
    <S {...p}><path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z" /></S>
  ),
};

export type IconName = keyof typeof Icon;
