/**
 * Command palette (Ctrl/Cmd-K).
 *
 * A senior officer moves between the lead queue, the review queue and a
 * specific session dozens of times a shift. Navigation by keyboard is
 * meaningfully faster than by pointer for that, and it also gives every action
 * in the app a single discoverable index.
 */
import clsx from 'clsx';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Icon, type IconName } from '@/components/icons';
import { Overlay } from '@/components/motion';
import { useTourStore } from '@/components/Tour';
import { useAuth } from '@/store/auth';
import { useTheme } from '@/store/theme';

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: IconName;
  roles?: string[];
  run: () => void;
  group: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const theme = useTheme();
  const showTour = useTourStore((s) => s.show);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setCursor(0);
      // Focus after the entrance animation starts, or the caret jumps.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => { navigate(to); setOpen(false); };
    const all: Command[] = [
      { id: 'dash', label: 'Officer dashboard', icon: 'dashboard', group: 'Navigate', roles: ['officer', 'senior_officer'], run: go('/officer') },
      { id: 'capture', label: 'New inspection', hint: 'Capture a pack', icon: 'camera', group: 'Navigate', roles: ['officer', 'senior_officer'], run: go('/officer/capture') },
      { id: 'route', label: "Today's patrol route", icon: 'route', group: 'Navigate', roles: ['officer', 'senior_officer'], run: go('/officer/route') },
      { id: 'leads', label: 'Citizen leads', icon: 'flag', group: 'Navigate', roles: ['officer', 'senior_officer'], run: go('/officer/leads') },
      { id: 'reviews', label: 'Peer review queue', icon: 'checkCircle', group: 'Navigate', roles: ['senior_officer'], run: go('/officer/reviews') },
      { id: 'scan', label: 'Scan a product', icon: 'scan', group: 'Navigate', roles: ['consumer'], run: go('/scan') },
      { id: 'report', label: 'Report a violation', icon: 'flag', group: 'Navigate', roles: ['consumer'], run: go('/report') },
      { id: 'alerts', label: 'Alerts', icon: 'bell', group: 'Navigate', roles: ['consumer'], run: go('/alerts') },
      { id: 'trust', label: 'My reporting record', icon: 'shield', group: 'Navigate', roles: ['consumer'], run: go('/trust') },
      { id: 'brand', label: 'Brand overview', icon: 'building', group: 'Navigate', roles: ['brand'], run: go('/brand') },
      { id: 'certify', label: 'Audit artwork', hint: 'Pre-market certification', icon: 'checkCircle', group: 'Navigate', roles: ['brand'], run: go('/brand/certify') },
      { id: 'disputes', label: 'Disputes', icon: 'scale', group: 'Navigate', roles: ['brand', 'senior_officer'], run: go('/brand/disputes') },
      { id: 'policy', label: 'Policy intelligence', icon: 'chart', group: 'Navigate', roles: ['senior_officer'], run: go('/policy') },
      { id: 'catalogue', label: 'Compliance catalogue', icon: 'box', group: 'Navigate', run: go('/catalogue') },
      { id: 'method', label: 'How it works', hint: 'Method, clauses and scoring', icon: 'info', group: 'Navigate', run: go('/how-it-works') },
      { id: 'tour', label: 'Replay the introduction', hint: 'The first-run walkthrough for your role', icon: 'sparkle', group: 'Navigate', run: () => { setOpen(false); showTour(); } },

      { id: 'theme', label: `Theme: ${theme.choice}`, hint: 'Cycle light / dark / system', icon: theme.resolved === 'dark' ? 'moon' : 'sun', group: 'Preferences', run: () => { theme.cycle(); } },
      { id: 'logout', label: 'Sign out', icon: 'logout', group: 'Account', run: () => { logout(); navigate('/login'); setOpen(false); } },
    ];

    return all.filter(
      (c) => !c.roles || user?.role === 'admin' || (user && c.roles.includes(user.role)),
    );
  }, [navigate, user, logout, theme, showTour]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) => c.label.toLowerCase().includes(q) || c.hint?.toLowerCase().includes(q),
    );
  }, [commands, query]);

  useEffect(() => { setCursor(0); }, [query]);

  const grouped = useMemo(() => {
    const map = new Map<string, Command[]>();
    for (const c of results) {
      const list = map.get(c.group) ?? [];
      list.push(c);
      map.set(c.group, list);
    }
    return [...map.entries()];
  }, [results]);

  // Flat order drives keyboard selection; grouping is purely visual.
  const flat = grouped.flatMap(([, items]) => items);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setCursor((c) => (c + 1) % Math.max(flat.length, 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setCursor((c) => (c - 1 + flat.length) % Math.max(flat.length, 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      flat[cursor]?.run();
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs text-ink-faint shadow-xs transition-colors hover:border-line-strong hover:text-ink-muted md:inline-flex"
        aria-label="Open command palette"
      >
        <Icon.search size={14} />
        <span>Search…</span>
        <kbd className="ml-2 rounded border border-line bg-surface-sunk px-1.5 py-0.5 font-mono text-[0.625rem] font-medium">
          ⌘K
        </kbd>
      </button>

      <Overlay open={open} onClose={() => setOpen(false)} labelledBy="cmdk-input">
        <div className="surface-raised overflow-hidden">
          <div className="flex items-center gap-3 border-b border-line px-4">
            <Icon.search size={17} className="shrink-0 text-ink-faint" />
            <input
              ref={inputRef}
              id="cmdk-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Search actions and pages…"
              className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-ink-faint"
              autoComplete="off"
              spellCheck={false}
            />
            <kbd className="shrink-0 rounded border border-line bg-surface-sunk px-1.5 py-0.5 font-mono text-[0.625rem] text-ink-faint">
              esc
            </kbd>
          </div>

          <div className="max-h-[52vh] overflow-y-auto p-2">
            {!flat.length ? (
              <p className="px-3 py-8 text-center text-sm text-ink-muted">
                Nothing matches “{query}”
              </p>
            ) : (
              grouped.map(([group, items]) => (
                <div key={group} className="mb-1">
                  <p className="px-3 py-1.5 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
                    {group}
                  </p>
                  {items.map((cmd) => {
                    const index = flat.indexOf(cmd);
                    const active = index === cursor;
                    const Glyph = Icon[cmd.icon];
                    return (
                      <button
                        key={cmd.id}
                        type="button"
                        onMouseEnter={() => setCursor(index)}
                        onClick={cmd.run}
                        className={clsx(
                          'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors',
                          active ? 'bg-accent text-accent-fg' : 'text-ink-soft hover:bg-surface-hover',
                        )}
                      >
                        <Glyph size={16} className="shrink-0 opacity-80" />
                        <span className="flex-1 truncate font-medium">{cmd.label}</span>
                        {cmd.hint && (
                          <span className={clsx(
                            'truncate text-2xs',
                            active ? 'text-accent-fg/70' : 'text-ink-faint',
                          )}>
                            {cmd.hint}
                          </span>
                        )}
                        {active && <Icon.arrowRight size={13} className="shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          <div className="flex items-center gap-4 border-t border-line bg-surface-sunk px-4 py-2 text-2xs text-ink-faint">
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-line px-1 font-mono">↑↓</kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-line px-1 font-mono">↵</kbd> select
            </span>
          </div>
        </div>
      </Overlay>
    </>
  );
}
