import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Page } from '@/components/motion';
import {
  Empty, ErrorBox, Loading, PageHeader, Section, Stat, moneyShort, when,
} from '@/components/ui';
import { api } from '@/store/auth';

export default function BrandOverview() {
  const dash = useQuery({ queryKey: ['brand', 'dashboard'], queryFn: () => api.brandDashboard() });
  const certs = useQuery({ queryKey: ['brand', 'certs'], queryFn: () => api.myCertifications() });

  if (dash.isLoading) return <Loading rows={4} />;
  if (dash.error) return <ErrorBox error={dash.error} retry={() => dash.refetch()} />;

  const d = dash.data!;

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Brand portal</span>}
        title={d.brand_name ?? 'Brand'}
        subtitle="Your compliance position across every field inspection on record, and the artwork audits that would have prevented them."
        action={
          <Link to="/brand/certify" className="btn-primary">
            <Icon.checkCircle size={16} />
            Audit new artwork
          </Link>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Field inspections" value={d.field_inspections.total}
          hint={`${d.field_inspections.flagged} flagged`}
        />
        <Stat
          label="Average score"
          value={d.field_inspections.avg_compliance_score ?? '—'}
          tone={
            (d.field_inspections.avg_compliance_score ?? 0) >= 85 ? 'good'
              : (d.field_inspections.avg_compliance_score ?? 0) >= 70 ? 'warn' : 'bad'
          }
        />
        <Stat
          label="Penalty exposure" value={moneyShort(d.field_inspections.penalty_exposure)}
          tone={d.field_inspections.penalty_exposure > 0 ? 'warn' : 'default'}
        />
        <Stat
          label="Certificates" value={d.pre_certifications.approved}
          hint={`${d.pre_certifications.total} audits run`} tone="good"
        />
      </div>

      {/* The guidance is the useful part: recurring findings almost always
          trace to one artwork template, and saying so is more actionable than
          another chart. */}
      {d.most_common_findings.length > 0 && (
        <Section title="Recurring findings" subtitle={d.guidance}>
          <div className="surface divide-y divide-line">
            {d.most_common_findings.map((f) => (
              <div key={f.finding} className="flex items-center justify-between gap-3 p-3">
                <span className="text-sm font-medium">{f.finding}</span>
                <span className="chip bg-bad-soft text-bad">{f.count}×</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Link to="/brand/certify" className="surface p-4 transition hover:border-accent">
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Pre-certification
          </div>
          <div className="mt-1 text-3xl font-bold">{d.pre_certifications.total}</div>
          <p className="mt-1 text-xs text-ink-muted">
            {d.pre_certifications.badges_issued} trust marks issued
          </p>
        </Link>
        <Link to="/brand/disputes" className="surface p-4 transition hover:border-accent">
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Open appeals
          </div>
          <div className="mt-1 text-3xl font-bold">{d.disputes.under_review}</div>
          <p className="mt-1 text-xs text-ink-muted">
            {d.disputes.accepted} accepted of {d.disputes.total} filed
          </p>
        </Link>
        <div className="surface p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Rejected audits
          </div>
          <div className="mt-1 text-3xl font-bold text-warn">
            {d.pre_certifications.rejected}
          </div>
          <p className="mt-1 text-xs text-ink-muted">Caught before printing</p>
        </div>
      </div>

      <Section
        title="Certification history"
        action={<Link to="/brand/certify" className="text-sm font-semibold text-accent">New audit</Link>}
      >
        {certs.isLoading ? (
          <Loading rows={2} />
        ) : !certs.data?.length ? (
          <Empty
            title="No artwork audited yet"
            hint="Upload a die-line before your next print run. Every defect caught here is an enforcement case that never happens."
            action={<Link to="/brand/certify" className="btn-primary">Audit artwork</Link>}
          />
        ) : (
          <div className="space-y-2">
            {certs.data.map((c) => (
              <div key={c.cert_ref} className="surface flex items-center gap-4 p-4">
                <div className={clsx(
                  'grid size-12 shrink-0 place-items-center rounded-lg text-lg font-bold',
                  c.is_approved ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn',
                )}>
                  {c.compliance_score ?? '—'}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{c.product_name}</p>
                  <p className="text-xs text-ink-muted">
                    {c.cert_ref} · {when(c.created_at)}
                    {c.target_pack_width_cm &&
                      ` · ${c.target_pack_width_cm}×${c.target_pack_height_cm} cm`}
                  </p>
                  {c.findings && c.findings.length > 0 && (
                    <p className="mt-1 text-xs text-warn">
                      {c.findings.length} finding{c.findings.length === 1 ? '' : 's'}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className={clsx(
                    'chip',
                    c.is_approved ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn',
                  )}>
                    {c.is_approved ? 'Certified' : 'Not certified'}
                  </span>
                  {c.audit_report_url && (
                    <a
                      href={api.resolveUrl(c.audit_report_url)}
                      target="_blank" rel="noreferrer"
                      className="text-xs font-semibold text-accent"
                    >
                      Report PDF
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </Page>
  );
}
