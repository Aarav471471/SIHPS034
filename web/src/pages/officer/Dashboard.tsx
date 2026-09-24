import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Page } from '@/components/motion';
import {
  Callout, Card, Counter, Empty, ErrorBox, Item, Loading, PageHeader, ScoreRing,
  Section, Stagger, Stat, StatusChip, ago, moneyShort,
} from '@/components/ui';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import { api } from '@/store/auth';

export default function OfficerDashboard() {
  const dash = useQuery({ queryKey: ['officer', 'dashboard'], queryFn: () => api.officerDashboard() });
  const recent = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: () => api.listSessions({ page_size: 6, mine: true }),
  });
  const { pending, captures } = useOfflineQueue();

  if (dash.isLoading) {
    return (
      <div className="space-y-6">
        <Loading rows={4} variant="stats" />
        <Loading rows={3} />
      </div>
    );
  }
  if (dash.error) return <ErrorBox error={dash.error} retry={() => dash.refetch()} />;

  const d = dash.data!;
  const festival = d.upcoming_festivals?.[0];

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={
          <span className="chip bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
            <Icon.shield size={12} />
            {d.officer.officer_id}
          </span>
        }
        title={d.officer.name ?? 'Officer'}
        subtitle={d.officer.jurisdiction ?? 'No jurisdiction assigned'}
        action={
          <>
            <Link to="/officer/route" className="btn-ghost">
              <Icon.route size={16} />
              Today's route
            </Link>
            <Link to="/officer/capture" className="btn-primary">
              <Icon.camera size={16} />
              New inspection
            </Link>
          </>
        }
      />

      {/* A festival window changes what to inspect this week, so it leads the
          page rather than hiding inside the route planner. */}
      {festival && festival.days_until <= 30 && (
        <Callout
          tone="warn"
          icon="sparkle"
          title={`${festival.festival} in ${festival.days_until} day${festival.days_until === 1 ? '' : 's'} — risk elevated up to ${festival.peak_multiplier}×`}
        >
          <p>Watch: {festival.elevated_categories.slice(0, 5).join(', ').replace(/-/g, ' ')}</p>
          {festival.note && <p className="mt-1 opacity-80">{festival.note}</p>}
        </Callout>
      )}

      <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Inspections" icon="camera"
          value={<Counter value={d.inspections.total} />}
          hint={`${d.inspections.this_week} this week`}
        />
        <Stat
          label="Flagged" icon="alert"
          value={<Counter value={d.inspections.flagged} />}
          hint="Non-compliant findings"
          tone={d.inspections.flagged ? 'bad' : 'default'}
        />
        <Stat
          label="Penalty exposure" icon="rupee"
          value={moneyShort(d.inspections.penalty_exposure)}
          hint="Across your inspections" tone="warn"
        />
        <Stat
          label="Queued offline" icon="upload"
          value={<Counter value={pending} />}
          hint={pending ? 'Waiting for connectivity' : 'Nothing waiting'}
          tone={pending ? 'warn' : 'default'}
        />
      </Stagger>

      {/* Three identical feature cards is the shape a template reaches for.
          What this data actually is: two work queues with counts, and one
          planning action. Rows carry the counts; the plan gets its own panel. */}
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Section title="Your queues" className="min-w-0">
          <Stagger className="space-y-2">
            <Item>
              <Link to="/officer/leads" className="block">
                <Card interactive className="flex items-center gap-4 p-4">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface-sunk text-ink-muted">
                    <Icon.flag size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">Citizen leads</p>
                    <p className="mt-0.5 text-2xs text-ink-muted">
                      Ordered by reporter trust — verified reporters first
                    </p>
                  </div>
                  <span className="display nums shrink-0 text-3xl font-semibold leading-none">
                    <Counter value={d.queues.citizen_leads_pending} />
                  </span>
                  <Icon.chevronRight size={16} className="shrink-0 text-ink-faint" />
                </Card>
              </Link>
            </Item>

            {d.officer.is_senior && (
              <Item>
                <Link to="/officer/reviews" className="block">
                  <Card interactive className="flex items-center gap-4 p-4">
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface-sunk text-ink-muted">
                      <Icon.checkCircle size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">Peer reviews</p>
                      <p className="mt-0.5 text-2xs text-ink-muted">
                        Borderline confidence, contested unit price, or high penalty
                      </p>
                    </div>
                    <span className="display nums shrink-0 text-3xl font-semibold leading-none">
                      <Counter value={d.queues.peer_reviews_pending} />
                    </span>
                    <Icon.chevronRight size={16} className="shrink-0 text-ink-faint" />
                  </Card>
                </Link>
              </Item>
            )}
          </Stagger>
        </Section>

        <Section title="Plan the day" className="min-w-0">
          <Link to="/officer/route" className="block h-full">
            <Card interactive className="flex h-full flex-col justify-between gap-4 bg-accent-soft p-5">
              <div>
                <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-fg shadow-sm">
                  <Icon.route size={18} />
                </span>
                <h3 className="display mt-3.5 text-xl font-semibold">Predictive patrol</h3>
                <p className="mt-1.5 text-pretty text-sm leading-relaxed text-ink-soft">
                  Stops ranked on inspection history, citizen leads, price anomalies
                  and festival windows — then reordered to cut travel time.
                </p>
              </div>
              <span className="flex items-center gap-1.5 text-sm font-semibold text-accent">
                Build today’s route
                <Icon.arrowRight size={15} />
              </span>
            </Card>
          </Link>
        </Section>
      </div>

      {pending > 0 && (
        <Section title="Waiting to upload" subtitle="Captured on this device, not yet sent">
          <Stagger className="space-y-2">
            {captures.filter((c) => c.status !== 'uploaded').slice(0, 4).map((c) => (
              <Item key={c.id}>
                <Card className="flex items-center justify-between gap-3 p-3.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">
                      {c.session.product_name ?? 'Unnamed commodity'}
                    </p>
                    <p className="mt-0.5 truncate text-2xs text-ink-muted">
                      {c.session.store_name ?? 'No store recorded'} · {c.surfaces.length} surface
                      {c.surfaces.length === 1 ? '' : 's'} · {ago(new Date(c.createdAt).toISOString())}
                    </p>
                    {c.lastError && <p className="mt-1 text-2xs text-bad">{c.lastError}</p>}
                  </div>
                  <StatusChip status={c.status.toUpperCase()} dot />
                </Card>
              </Item>
            ))}
          </Stagger>
        </Section>
      )}

      <Section
        title="Recent inspections"
        action={
          <Link to="/catalogue" className="btn-subtle btn-sm">
            Browse catalogue
            <Icon.chevronRight size={14} />
          </Link>
        }
      >
        {recent.isLoading ? (
          <Loading rows={3} />
        ) : !recent.data?.items.length ? (
          <Empty
            icon="camera"
            title="No inspections yet"
            hint="Capture a pack to run it through the compliance pipeline."
            action={<Link to="/officer/capture" className="btn-primary">Start an inspection</Link>}
          />
        ) : (
          <Stagger className="space-y-2">
            {recent.data.items.map((s) => (
              <Item key={s.session_id}>
                <Link to={`/officer/sessions/${s.session_id}`} className="block">
                  <Card interactive className="flex items-center gap-4 p-4">
                    <ScoreRing score={s.overall_score} size={52} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">
                        {s.product_name ?? 'Unidentified commodity'}
                      </p>
                      <p className="mt-0.5 truncate text-sm text-ink-muted">
                        {s.brand_name ?? '—'} · {s.store_name ?? 'No store'} · {ago(s.created_at)}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <StatusChip status={s.status} dot />
                        {s.compliance_status && <StatusChip status={s.compliance_status} />}
                        {s.violation_count > 0 && (
                          <span className="chip bg-bad/10 text-bad ring-1 ring-inset ring-bad/25">
                            {s.violation_count} finding{s.violation_count === 1 ? '' : 's'}
                          </span>
                        )}
                        {s.jurisdiction_status === 'OUT_OF_BOUNDS' && (
                          <span className="chip bg-warn/10 text-warn ring-1 ring-inset ring-warn/25">
                            <Icon.pin size={11} />
                            Outside jurisdiction
                          </span>
                        )}
                      </div>
                    </div>
                    <Icon.chevronRight
                      size={16}
                      className={clsx('shrink-0 text-ink-faint transition-transform')}
                    />
                  </Card>
                </Link>
              </Item>
            ))}
          </Stagger>
        )}
      </Section>
    </Page>
  );
}
