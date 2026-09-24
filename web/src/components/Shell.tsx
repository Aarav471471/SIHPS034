/**
 * Application chrome.
 *
 * Desktop gets a persistent sidebar rather than a top nav: this is a working
 * tool used all day across five sections, and a sidebar keeps every destination
 * one click away with the current one always visible. Phones get a bottom bar,
 * because the officer and consumer surfaces are used one-handed in a shop and
 * the top of a phone is out of thumb reach.
 */
import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { CommandPalette } from '@/components/CommandPalette';
import { Tour, useFirstRunTour, useTourStore } from '@/components/Tour';
import { Icon, type IconName } from '@/components/icons';
import { AnimatePresence, EASE, motion } from '@/components/motion';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import { homeFor, useAuth } from '@/store/auth';
import { useTheme } from '@/store/theme';

interface NavItem {
  to: string;
  label: string;
  roles: string[];
  icon: IconName;
  end?: boolean;
  badge?: 'queue';
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Enforcement',
    items: [
      { to: '/officer', label: 'Dashboard', roles: ['officer', 'senior_officer'], icon: 'dashboard', end: true },
      { to: '/officer/capture', label: 'Inspect', roles: ['officer', 'senior_officer'], icon: 'camera', badge: 'queue' },
      { to: '/officer/route', label: 'Patrol route', roles: ['officer', 'senior_officer'], icon: 'route' },
      { to: '/officer/leads', label: 'Citizen leads', roles: ['officer', 'senior_officer'], icon: 'flag' },
      { to: '/officer/reviews', label: 'Peer reviews', roles: ['senior_officer'], icon: 'checkCircle' },
    ],
  },
  {
    group: 'Consumer',
    items: [
      { to: '/scan', label: 'Scan', roles: ['consumer'], icon: 'scan' },
      { to: '/report', label: 'Report', roles: ['consumer'], icon: 'flag' },
      { to: '/alerts', label: 'Alerts', roles: ['consumer'], icon: 'bell' },
      { to: '/trust', label: 'My record', roles: ['consumer'], icon: 'shield' },
    ],
  },
  {
    group: 'Brand',
    items: [
      { to: '/brand', label: 'Overview', roles: ['brand'], icon: 'building', end: true },
      { to: '/brand/certify', label: 'Pre-certify', roles: ['brand'], icon: 'checkCircle' },
      { to: '/brand/disputes', label: 'Disputes', roles: ['brand', 'senior_officer'], icon: 'scale' },
    ],
  },
  {
    group: 'Intelligence',
    items: [
      { to: '/policy', label: 'Policy', roles: ['senior_officer'], icon: 'chart' },
      { to: '/catalogue', label: 'Catalogue', roles: ['officer', 'senior_officer', 'consumer', 'brand'], icon: 'box' },
      { to: '/how-it-works', label: 'How it works', roles: ['officer', 'senior_officer', 'consumer', 'brand'], icon: 'info' },
    ],
  },
];

// Mobile bottom bar carries at most five; more become unreachable targets.
const MOBILE_LIMIT = 5;

function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}

function ThemeToggle() {
  const { choice, resolved, cycle } = useTheme();
  const Glyph = choice === 'system' ? Icon.sparkle : resolved === 'dark' ? Icon.moon : Icon.sun;
  return (
    <button
      type="button"
      onClick={cycle}
      className="grid size-9 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
      title={`Theme: ${choice}`}
      aria-label={`Theme: ${choice}. Click to change.`}
    >
      <Glyph size={17} />
    </button>
  );
}

export function Shell() {
  const { user, logout } = useAuth();
  const online = useOnline();
  const { pending, syncing, sync } = useOfflineQueue();
  const navigate = useNavigate();
  const location = useLocation();
  const [drawer, setDrawer] = useState(false);
  const showTour = useTourStore((s) => s.show);

  // Shown once per role on first sight of the app, and replayable from the
  // header or the command palette afterwards.
  useFirstRunTour();

  const groups = NAV
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => user && (user.role === 'admin' || i.roles.includes(user.role))),
    }))
    .filter((g) => g.items.length);

  const flat = groups.flatMap((g) => g.items);

  // Route changes close the drawer, but that alone is not enough: tapping the
  // entry for the page you are already on, or the logo, leaves the pathname
  // untouched and the drawer open on top of the content. Every activation
  // inside the drawer closes it, and Escape does too.
  useEffect(() => { setDrawer(false); }, [location.pathname]);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawer(false); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [drawer]);

  // Built per surface rather than shared as one element: the desktop rail stays
  // mounted at every breakpoint (it is only `hidden`), so reusing one tree would
  // put two elements with the same layoutId on the page whenever the drawer
  // opens, and Framer Motion would fling the active pill between them.
  const renderSidebar = (scope: 'rail' | 'drawer') => (
    <>
      <div className="flex items-center gap-2.5 px-4 py-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent font-black text-accent-fg shadow-sm">
          M
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-bold leading-tight tracking-tight">MetriX</span>
          <span className="block truncate text-2xs leading-tight text-ink-faint">
            Legal Metrology
          </span>
        </span>
      </div>

      <nav
        className="flex-1 space-y-5 overflow-y-auto px-3 pb-4"
        onClick={scope === 'drawer' ? () => setDrawer(false) : undefined}
      >
        {groups.map((g) => (
          <div key={g.group}>
            <p className="px-3 pb-1.5 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
              {g.group}
            </p>
            <ul className="space-y-0.5">
              {g.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      clsx(
                        'group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'text-accent'
                          : 'text-ink-muted hover:bg-surface-hover hover:text-ink',
                      )
                    }
                  >
                    {({ isActive }) => {
                      const Glyph = Icon[item.icon];
                      return (
                        <>
                          {/* A shared layoutId slides the active pill between
                              items instead of cross-fading two rectangles. */}
                          {isActive && (
                            <motion.span
                              layoutId={`nav-active-${scope}`}
                              className="absolute inset-0 -z-10 rounded-lg bg-accent/10 ring-1 ring-inset ring-accent/20"
                              transition={{ type: 'spring', stiffness: 420, damping: 36 }}
                            />
                          )}
                          <Glyph size={17} className="shrink-0" />
                          <span className="flex-1 truncate">{item.label}</span>
                          {item.badge === 'queue' && pending > 0 && (
                            <span className="chip bg-warn/15 text-warn nums">{pending}</span>
                          )}
                        </>
                      );
                    }}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {user && (
        <div className="border-t border-line p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">
              {(user.full_name ?? user.username).slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-semibold">
                {user.full_name ?? user.username}
              </span>
              <span className="block truncate text-2xs capitalize text-ink-faint">
                {user.role.replace('_', ' ')}
                {user.jurisdiction_name && ` · ${user.jurisdiction_name}`}
              </span>
            </span>
            <button
              type="button"
              onClick={() => { logout(); navigate('/login'); }}
              className="grid size-8 shrink-0 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-hover hover:text-bad"
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon.logout size={15} />
            </button>
          </div>
        </div>
      )}
    </>
  );

  return (
    <div className="min-h-dvh lg:flex">
      {/* ------------------------------------------------ desktop rail -- */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        {renderSidebar('rail')}
      </aside>

      {/* ------------------------------------------------ mobile drawer - */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={EASE}
              onClick={() => setDrawer(false)}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-surface lg:hidden"
              initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
              transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            >
              {renderSidebar('drawer')}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Connectivity is stated plainly rather than left for an officer to
            infer from a failed upload. Queued work rides along with it. */}
        <AnimatePresence>
          {(!online || pending > 0) && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={EASE}
              className={clsx(
                'sticky top-0 z-30 overflow-hidden text-xs font-semibold',
                online ? 'bg-warn text-white' : 'bg-ink text-bg',
              )}
            >
              <div className="flex items-center justify-between gap-3 px-4 py-2">
                <span className="flex items-center gap-2">
                  {!online && <Icon.wifiOff size={14} />}
                  {online
                    ? `${pending} capture${pending === 1 ? '' : 's'} waiting to upload`
                    : `Offline — captures are saved on this device${pending ? ` (${pending} queued)` : ''}`}
                </span>
                {online && pending > 0 && (
                  <button
                    type="button" onClick={() => sync()} disabled={syncing}
                    className="underline underline-offset-2 disabled:opacity-60"
                  >
                    {syncing ? 'Syncing…' : 'Sync now'}
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <header className="sticky top-0 z-20 border-b border-line bg-surface/80 backdrop-blur-xl">
          <div className="flex items-center gap-3 px-4 py-2.5 lg:px-6">
            <button
              type="button"
              onClick={() => setDrawer(true)}
              className="grid size-9 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-hover lg:hidden"
              aria-label="Open navigation"
            >
              <Icon.menu size={19} />
            </button>

            <Link to={homeFor(user?.role)} className="flex items-center gap-2 lg:hidden">
              <span className="grid size-8 place-items-center rounded-lg bg-accent text-sm font-black text-accent-fg">
                M
              </span>
            </Link>

            <div className="ml-auto flex items-center gap-1.5">
              <CommandPalette />
              <button
                type="button"
                onClick={showTour}
                className="grid size-9 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
                title="Replay the introduction"
                aria-label="Replay the introduction"
              >
                <Icon.info size={17} />
              </button>
              <ThemeToggle />
            </div>
          </div>
        </header>

        {/* Route transition. Keyed on pathname so each page animates in. */}
        <main className="flex-1 px-4 py-5 pb-24 lg:px-6 lg:py-6 lg:pb-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>

      <Tour />

      {/* ------------------------------------------------ mobile tabs -- */}
      {flat.length > 0 && (
        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/90 backdrop-blur-xl lg:hidden">
          <ul className="flex items-stretch justify-around pb-[env(safe-area-inset-bottom)]">
            {flat.slice(0, MOBILE_LIMIT).map((item) => {
              const active = item.end
                ? location.pathname === item.to
                : location.pathname.startsWith(item.to);
              const Glyph = Icon[item.icon];
              return (
                <li key={item.to} className="flex-1">
                  <Link
                    to={item.to}
                    className={clsx(
                      'relative flex flex-col items-center gap-1 py-2 text-[0.625rem] font-semibold transition-colors',
                      active ? 'text-accent' : 'text-ink-faint',
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="tab-active"
                        className="absolute inset-x-4 top-0 h-0.5 rounded-full bg-accent"
                        transition={{ type: 'spring', stiffness: 420, damping: 36 }}
                      />
                    )}
                    <span className="relative">
                      <Glyph size={19} />
                      {item.badge === 'queue' && pending > 0 && (
                        <span className="absolute -right-1.5 -top-1 grid size-3.5 place-items-center rounded-full bg-warn text-[0.5rem] font-bold text-white">
                          {pending > 9 ? '9+' : pending}
                        </span>
                      )}
                    </span>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
