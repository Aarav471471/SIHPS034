import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { EASE, Item, Stagger, motion } from '@/components/motion';
import { homeFor, useAuth } from '@/store/auth';

// Seeded demo accounts on a local database — shown so a reviewer can enter every
// portal without hunting through documentation.
const DEMO = [
  { role: 'Field Officer', username: 'officer.sharma', note: 'Delhi Central Zone', icon: 'camera' as const },
  { role: 'Senior Officer', username: 'senior.iyer', note: 'Peer review + policy', icon: 'checkCircle' as const },
  { role: 'Consumer', username: 'citizen.priya', note: 'Verified Vigilant Citizen', icon: 'scan' as const },
  { role: 'Brand', username: 'brand.parle', note: 'Pre-certification + disputes', icon: 'building' as const },
  { role: 'Administrator', username: 'admin', note: 'Full platform access', icon: 'shield' as const },
];

const PILLARS = [
  { t: 'Officer', d: 'Predictive patrol routing, offline capture, tamper-evident evidence', icon: 'route' as const },
  { t: 'Consumer', d: 'Scan before you buy, overcharge detection, citizen reporting', icon: 'scan' as const },
  { t: 'Brand', d: 'Pre-market artwork audit before the print run', icon: 'building' as const },
  { t: 'Policy', d: 'Clause-level trends and inter-agency referrals', icon: 'chart' as const },
];

export default function Login() {
  const { login, busy, error, user, status } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  if (status === 'authenticated' && user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? homeFor(user.role)} replace />;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const profile = await login(username.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? homeFor(profile.role), { replace: true });
    } catch {
      /* surfaced from the store */
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      {/* ----------------------------------------------------- brand ---- */}
      <div className="relative hidden overflow-hidden bg-[hsl(222_54%_11%)] p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-14">
        <div className="bg-grid absolute inset-0 opacity-[0.07]" />
        {/* A single soft light source keeps the panel from reading as flat navy. */}
        <div
          className="pointer-events-none absolute -right-40 -top-40 size-[32rem] rounded-full opacity-50 blur-3xl"
          style={{ background: 'radial-gradient(circle, hsl(216 70% 40%), transparent 65%)' }}
        />

        <motion.div
          className="relative"
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={EASE}
        >
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-xl bg-white/10 text-2xl font-black ring-1 ring-inset ring-white/20">
              M
            </span>
            <div>
              <div className="text-lg font-bold tracking-tight">MetriX</div>
              <div className="text-xs text-white/60">Legal Metrology Compliance Engine</div>
            </div>
          </div>

          <p className="eyebrow mt-16 text-white/45">Packaged Commodities Rules 2011</p>
          <h1 className="display mt-3 max-w-xl text-balance text-display font-semibold leading-[1.05] xl:text-display-lg">
            AI-assisted enforcement a court can rely on.
          </h1>
          <p className="mt-6 max-w-md text-pretty text-sm leading-relaxed text-white/70">
            Vision AI proposes what it reads on a pack. Deterministic OCR re-reads the
            same pixels. A rules engine checks the arithmetic against the Packaged
            Commodities Rules. A human approves the notice.
          </p>

          <Stagger className="mt-14 grid max-w-lg grid-cols-2 gap-x-8 gap-y-6" delay={0.06}>
            {PILLARS.map((p) => {
              const Glyph = Icon[p.icon];
              return (
                <Item key={p.t} className="flex gap-3">
                  <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-white/10 ring-1 ring-inset ring-white/15">
                    <Glyph size={15} />
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{p.t}</div>
                    <div className="mt-0.5 text-pretty text-xs leading-relaxed text-white/60">
                      {p.d}
                    </div>
                  </div>
                </Item>
              );
            })}
          </Stagger>
        </motion.div>

        <p className="relative text-xs text-white/45">
          Smart India Hackathon 2025 · PS 26034 · Ministry of Consumer Affairs,
          Food &amp; Public Distribution
        </p>
      </div>

      {/* ----------------------------------------------------- form ----- */}
      <div className="flex items-center justify-center bg-bg p-6">
        <motion.div
          className="w-full max-w-sm"
          initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
          transition={{ ...EASE, delay: 0.06 }}
        >
          <div className="mb-7 lg:hidden">
            <span className="grid size-11 place-items-center rounded-xl bg-accent text-2xl font-black text-accent-fg shadow-md">
              M
            </span>
            <h1 className="display mt-4 text-2xl font-semibold">MetriX</h1>
            <p className="text-sm text-ink-muted">Legal Metrology Compliance</p>
          </div>

          <form onSubmit={submit} className="surface-raised space-y-4 p-6 sm:p-7">
            <div>
              <h2 className="display text-2xl font-semibold">Sign in</h2>
              <p className="mt-0.5 text-sm text-ink-muted">
                Use your username or email address.
              </p>
            </div>

            <div>
              <label className="label" htmlFor="username">Username or email</label>
              <input
                id="username" className="input" value={username} autoComplete="username"
                onChange={(e) => setUsername(e.target.value)} required
                placeholder="officer.sharma"
              />
            </div>

            <div>
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password" type="password" className="input" value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)} required
              />
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 rounded-lg bg-bad-soft px-3 py-2 text-sm font-medium text-bad"
              >
                <Icon.alert size={15} className="shrink-0" />
                {error}
              </motion.p>
            )}

            <button type="submit" className="btn-primary btn-lg w-full" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
              {!busy && <Icon.arrowRight size={16} />}
            </button>
          </form>

          <div className="surface mt-4 overflow-hidden">
            <p className="eyebrow border-b border-line px-4 py-3">Demo accounts</p>
            <div className="divide-y divide-line">
              {DEMO.map((d) => {
                const Glyph = Icon[d.icon];
                return (
                  <button
                    key={d.username}
                    type="button"
                    onClick={() => { setUsername(d.username); setPassword('Metrix@2026'); }}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-hover"
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-sunk text-ink-muted">
                      <Glyph size={15} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold">{d.role}</span>
                      <span className="block truncate text-2xs text-ink-muted">{d.note}</span>
                    </span>
                    <code className="shrink-0 rounded-md bg-surface-sunk px-2 py-1 font-mono text-2xs text-ink-muted">
                      {d.username}
                    </code>
                  </button>
                );
              })}
            </div>
            <p className="border-t border-line bg-surface-sunk px-4 py-2 text-2xs text-ink-muted">
              Password for all demo accounts:{' '}
              <code className="font-mono font-semibold text-ink-soft">Metrix@2026</code>
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
