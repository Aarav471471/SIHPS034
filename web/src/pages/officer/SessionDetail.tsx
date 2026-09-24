import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Item, Page, Stagger } from '@/components/motion';
import {
  Callout, Card, ErrorBox, Loading, RuleRow, ScoreScale, Section, Stat,
  StatusChip, Verdict, money, when,
} from '@/components/ui';
import { STAGES, STAGE_LABELS, usePipelineSocket } from '@/hooks/usePipelineSocket';
import { api, useAuth } from '@/store/auth';

const SEVERITY_TONE = { CRITICAL: 'bad', MAJOR: 'warn', MINOR: 'warn' } as const;

export default function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [remarks, setRemarks] = useState('');

  const session = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.getSession(sessionId!),
    enabled: Boolean(sessionId),
    // Poll while the pipeline runs. The WebSocket carries progress; this is
    // what actually swaps in the finished result.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'PENDING' || s === 'PROCESSING' ? 2000 : false;
    },
  });

  const running = session.data?.status === 'PENDING' || session.data?.status === 'PROCESSING';
  const { progress, latest, stageStatus, connected } = usePipelineSocket(sessionId, running);

  const seal = useQuery({
    queryKey: ['seal', sessionId],
    queryFn: () => api.verifyEvidenceSeal(sessionId!),
    enabled: Boolean(sessionId) && !running,
  });

  const escalate = useMutation({
    mutationFn: (reason: string) => api.escalate(sessionId!, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['session', sessionId] }),
  });

  const decide = useMutation({
    mutationFn: (v: { decision: 'APPROVED' | 'REJECTED' | 'MODIFIED'; remarks: string }) =>
      api.decidePeerReview(sessionId!, v.decision, v.remarks),
    onSuccess: () => {
      setRemarks('');
      qc.invalidateQueries({ queryKey: ['session', sessionId] });
    },
  });

  if (session.isLoading) return <Loading rows={4} />;
  if (session.error) return <ErrorBox error={session.error} retry={() => session.refetch()} />;

  const s = session.data!;
  const fails = s.violations.filter((v) => v.status === 'FAIL');
  const warns = s.violations.filter((v) => v.status === 'WARNING');
  const verified = s.fields.filter((f) => f.ocr_agreement === true).length;

  // A pack the pipeline could not read is not a compliant pack. Everything that
  // reports a verdict on this page keys off this one flag, so the page cannot
  // end up congratulating a blank extraction in one place and warning about it
  // in another.
  const unassessable = !running && s.fields.length === 0;

  return (
    <Page className="space-y-8">
      {/* ------------------------------------------------- the verdict --- */}
      <Verdict
        score={s.overall_score}
        state={running ? 'pending' : unassessable ? 'unassessable' : 'scored'}
        title={s.product_name ?? 'Unidentified commodity'}
        subtitle={
          <>
            {s.brand_name ?? 'Brand not declared'} · {s.store_name ?? 'No store recorded'}
            {s.location_address ? ` · ${s.location_address}` : ''}
          </>
        }
        meta={
          <>
            <StatusChip status={s.status} dot />
            {s.compliance_status && <StatusChip status={s.compliance_status} />}
            {s.jurisdiction_status === 'OUT_OF_BOUNDS' && (
              <span className="chip bg-warn-soft text-warn ring-1 ring-inset ring-warn/25">
                <Icon.pin size={11} />
                Outside jurisdiction
              </span>
            )}
            {s.is_locked && (
              <span className="chip bg-surface-sunk text-ink-muted ring-1 ring-inset ring-line-strong">
                <Icon.shield size={11} />
                Evidence locked
              </span>
            )}
            <code className="ml-1 font-mono text-2xs text-ink-faint">{s.session_id}</code>
          </>
        }
        aside={
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            {[
              ['Inspected', when(s.created_at)],
              ['Officer', s.officer_name ?? '—'],
              [
                'Confidence',
                s.confidence_score != null ? s.confidence_score.toFixed(2) : '—',
              ],
              ['Penalty exposure', money(s.estimated_penalty)],
            ].map(([k, v]) => (
              <div key={String(k)}>
                <dt className="eyebrow">{k}</dt>
                <dd
                  className={clsx(
                    'nums mt-1 text-sm font-semibold',
                    k === 'Penalty exposure' && s.estimated_penalty ? 'text-warn' : '',
                  )}
                >
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        }
        note={
          running
            ? 'The pipeline is still running. Nothing on this page is final until the validate stage completes.'
            : unassessable
            ? 'No declarations were read from this capture, so no clause could be tested. The score is withheld rather than defaulted.'
            : `${s.fields.length} declaration${s.fields.length === 1 ? '' : 's'} extracted, ${verified} independently confirmed by a second OCR pass over the same pixels. Every finding below cites the clause it rests on.`
        }
      />

      {/* ------------------------------------------- live pipeline ------- */}
      {running && (
        <Card className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">In progress</p>
              <h2 className="display mt-1 text-xl font-semibold">
                Running the inspection pipeline
              </h2>
            </div>
            <span
              className={clsx(
                'chip ring-1 ring-inset',
                connected
                  ? 'bg-ok-soft text-ok ring-ok/25'
                  : 'bg-surface-sunk text-ink-muted ring-line-strong',
              )}
            >
              <span className={clsx('size-1.5 rounded-full', connected ? 'animate-pulse bg-ok' : 'bg-ink-faint')} />
              {connected ? 'Live' : 'Reconnecting…'}
            </span>
          </div>

          <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-surface-sunk">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>

          <ol className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-6">
            {STAGES.map((stage, i) => {
              const st = stageStatus[stage] ?? 'pending';
              return (
                <li key={stage} className="text-center">
                  <div
                    className={clsx(
                      'mx-auto grid size-9 place-items-center rounded-full text-xs font-bold ring-1',
                      st === 'done' && 'bg-ok text-white ring-ok',
                      st === 'active' && 'animate-pulse bg-accent text-accent-fg ring-accent',
                      st === 'failed' && 'bg-bad text-white ring-bad',
                      st === 'pending' && 'bg-surface-sunk text-ink-faint ring-line',
                    )}
                  >
                    {st === 'done' ? <Icon.check size={14} /> : i + 1}
                  </div>
                  <div
                    className={clsx(
                      'mt-1.5 text-2xs font-semibold',
                      st === 'pending' ? 'text-ink-faint' : 'text-ink-soft',
                    )}
                  >
                    {STAGE_LABELS[stage]}
                  </div>
                </li>
              );
            })}
          </ol>

          {latest && (
            <p className="panel mt-5 px-3.5 py-2.5 text-sm text-ink-soft">{latest.message}</p>
          )}
        </Card>
      )}

      {s.processing_error && (
        <ErrorBox error={new Error(s.processing_error)} retry={() => session.refetch()} />
      )}

      {/* ------------------------------------------------- findings ------ */}
      <Section
        title="Findings"
        subtitle="Each finding cites the clause it rests on and the pixels that evidence it."
        action={
          s.violations.length > 0 && (
            <div className="flex gap-1.5">
              {fails.length > 0 && (
                <span className="chip bg-bad-soft text-bad ring-1 ring-inset ring-bad/25">
                  {fails.length} failed
                </span>
              )}
              {warns.length > 0 && (
                <span className="chip bg-warn-soft text-warn ring-1 ring-inset ring-warn/25">
                  {warns.length} advisory
                </span>
              )}
            </div>
          )
        }
      >
        {!s.violations.length ? (
          /* Zero findings is only a clean result when there was something to
             check, and when the checking has finished. Mid-pipeline the
             violations array is legitimately empty because the validate stage
             has not run yet -- announcing compliance there is the same false
             reassurance as announcing it on a blank extraction. Both fail
             closed. Reporting either as compliant is how an enforcement tool
             clears a pack it never actually assessed. */
          running ? (
            <Callout tone="info" icon="clock" title="Still checking">
              The validate stage has not run yet. Findings appear here as soon as
              the rules engine has been applied to the extracted declarations.
            </Callout>
          ) : unassessable ? (
            <Callout tone="warn" title="Not assessable — nothing was extracted">
              No declarations could be read from the captured surfaces, so no
              clause could be tested. This is not a finding of compliance.
              Re-capture with the printed panel filling the frame, in even light,
              with the text in focus.
            </Callout>
          ) : (
            <Callout tone="ok" title="No contravention detected">
              All {s.fields.length} extracted declaration
              {s.fields.length === 1 ? '' : 's'} passed every applicable clause.
            </Callout>
          )
        ) : (
          <Stagger className="space-y-2.5">
            {s.violations.map((v, i) => (
              <RuleRow
                key={`${v.rule_id}-${i}`}
                tone={v.status === 'FAIL' ? SEVERITY_TONE[v.severity ?? 'MAJOR'] : 'warn'}
                title={v.rule_name ?? v.rule_id}
                clause={v.legal_clause}
                code={v.rule_id}
                observed={v.calculated_value}
                expected={v.expected_value}
                action={
                  <>
                    <span
                      className={clsx(
                        'chip ring-1 ring-inset',
                        v.severity === 'CRITICAL' && 'bg-bad-soft text-bad ring-bad/25',
                        v.severity === 'MAJOR' && 'bg-warn-soft text-warn ring-warn/25',
                        v.severity === 'MINOR' && 'bg-surface-sunk text-ink-muted ring-line-strong',
                      )}
                    >
                      {v.severity ?? 'MAJOR'}
                    </span>
                    {v.penalty_amount != null && (
                      <span className="nums chip bg-surface-sunk text-ink-soft ring-1 ring-inset ring-line">
                        {money(v.penalty_amount)}
                      </span>
                    )}
                  </>
                }
                evidence={
                  <div className="mt-3 space-y-3">
                    {v.suggested_fix && (
                      <p className="rounded-lg bg-info-soft px-3 py-2 text-xs leading-relaxed text-info">
                        <span className="font-semibold">Remedy · </span>
                        {v.suggested_fix}
                      </p>
                    )}
                    {v.crop_url && (
                      <figure className="inline-block">
                        {/* Evidence is shown plainly: no filter, no crop
                            adjustment, no hover zoom. What the officer sees has
                            to be exactly what the rule was applied to. */}
                        <img
                          src={api.resolveUrl(v.crop_url)}
                          alt={`Evidence crop for ${v.rule_name ?? v.rule_id}`}
                          className="max-h-32 rounded-lg border border-line-strong"
                          loading="lazy"
                        />
                        <figcaption className="mt-1.5 text-2xs text-ink-faint">
                          Crop from the original photograph, unaltered
                        </figcaption>
                      </figure>
                    )}
                  </div>
                }
              >
                {v.evidence_text}
              </RuleRow>
            ))}
          </Stagger>
        )}
      </Section>

      {/* ------------------------------------------- extracted fields ---- */}
      <Section
        title="Extracted declarations"
        subtitle="The vision reading, and the independent OCR re-read of the same pixels that either confirms it or does not."
      >
        {!s.fields.length ? (
          <Callout tone="warn" title="Nothing extracted">
            The pipeline located no printed declarations on the captured surfaces.
          </Callout>
        ) : (
          <>
            <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Declarations read" value={s.fields.length} icon="file" />
              <Stat
                label="OCR confirmed" value={verified} icon="checkCircle"
                tone={verified === s.fields.length ? 'good' : 'warn'}
                hint={`of ${s.fields.length} read`}
              />
              <Stat
                label="Surfaces captured" value={s.images.length} icon="camera"
                hint={s.images.map((i) => i.surface_type).join(', ').toLowerCase()}
              />
              <Stat
                label="Pack size" icon="box"
                value={
                  s.package_width_cm && s.package_height_cm
                    ? `${s.package_width_cm}×${s.package_height_cm} cm`
                    : '—'
                }
                hint={s.package_width_cm ? 'Sets the Rule 11 minimum height' : 'Height check cannot run'}
                tone={s.package_width_cm ? 'default' : 'warn'}
              />
            </Stagger>

            <Card className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line bg-surface-sunk text-left">
                  <tr>
                    {['Declaration', 'Value', 'Surface', 'Vision', 'OCR check', 'Height'].map((h) => (
                      <th key={h} className="whitespace-nowrap px-4 py-3">
                        <span className="eyebrow">{h}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {s.fields.map((f) => (
                    <tr key={f.field_name} className="transition-colors hover:bg-surface-hover">
                      <td className="whitespace-nowrap px-4 py-3 font-medium capitalize">
                        {f.field_name.replace(/_/g, ' ')}
                      </td>
                      <td className="px-4 py-3">
                        {f.detected_value ?? (
                          <span className="text-ink-faint">not found</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-2xs uppercase tracking-wide text-ink-muted">
                        {f.surface_found ?? '—'}
                      </td>
                      <td className="nums px-4 py-3">
                        {f.confidence_vision_llm != null ? f.confidence_vision_llm.toFixed(2) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {f.ocr_agreement === true && (
                          <span className="chip bg-ok-soft text-ok">agrees</span>
                        )}
                        {f.ocr_agreement === false && (
                          <span className="chip bg-bad-soft text-bad">disagrees</span>
                        )}
                        {f.ocr_agreement == null && (
                          <span className="text-2xs text-ink-faint">unverified</span>
                        )}
                      </td>
                      <td className="nums px-4 py-3 text-ink-muted">
                        {f.font_height_mm ? `${f.font_height_mm} mm` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <p className="text-xs leading-relaxed text-ink-muted">
              An unverified reading is capped below the auto-accept threshold,
              which is what routes a session to human review rather than issuing a
              notice on a single model's word.
            </p>
          </>
        )}
      </Section>

      {/* ------------------------------------------------ evidence ------- */}
      <Section
        title="Evidence"
        subtitle="Every surface is hashed at the moment of capture. The seal below re-derives those hashes from what is stored now."
      >
        <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {s.images.map((img) => (
            <Item key={img.id}>
              <figure className="surface overflow-hidden">
                {img.url && (
                  <img
                    src={api.resolveUrl(img.url)}
                    alt={`${img.surface_type} surface as captured`}
                    className="aspect-square w-full border-b border-line object-cover"
                    loading="lazy"
                  />
                )}
                <figcaption className="space-y-1.5 p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="eyebrow">{img.surface_type}</span>
                    {img.is_curved_surface && (
                      <span className="chip bg-info-soft text-info">curved</span>
                    )}
                  </div>
                  <p className="text-2xs text-ink-muted">
                    {img.unwarp_method ?? 'no'} rectification
                    {img.px_per_mm ? ` · ${img.px_per_mm} px/mm` : ''}
                  </p>
                  <p className="break-all font-mono text-[0.625rem] leading-relaxed text-ink-faint">
                    {img.sha256_hash.slice(0, 32)}…
                  </p>
                </figcaption>
              </figure>
            </Item>
          ))}
        </Stagger>

        {seal.data && (
          <Callout
            tone={seal.data.intact ? 'ok' : 'bad'}
            icon={seal.data.intact ? 'shield' : 'alert'}
            title={seal.data.verdict}
          >
            <p className="break-all font-mono text-2xs">Seal {seal.data.seal ?? '—'}</p>
          </Callout>
        )}
      </Section>

      {/* -------------------------------------------------- actions ------ */}
      {!running && (
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <Section title="Decision">
            <Card className="space-y-3.5 p-5">
              {s.status === 'PEER_REVIEW' && user?.role !== 'officer' ? (
                <>
                  <p className="text-sm leading-relaxed text-ink-soft">
                    This case was escalated for senior review. Examine the evidence
                    crops above before deciding — your remarks are recorded against
                    the decision and are disclosable if the notice is contested.
                  </p>
                  <div>
                    <label className="label" htmlFor="remarks">Remarks</label>
                    <textarea
                      id="remarks" className="input" rows={3} value={remarks}
                      onChange={(e) => setRemarks(e.target.value)}
                      placeholder="Why you are approving, dismissing or modifying these findings"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button" className="btn-ok"
                      disabled={remarks.trim().length < 3 || decide.isPending}
                      onClick={() => decide.mutate({ decision: 'APPROVED', remarks })}
                    >
                      <Icon.checkCircle size={16} />
                      Approve notice
                    </button>
                    <button
                      type="button" className="btn-danger"
                      disabled={remarks.trim().length < 3 || decide.isPending}
                      onClick={() => decide.mutate({ decision: 'REJECTED', remarks })}
                    >
                      Dismiss with remarks
                    </button>
                    <button
                      type="button" className="btn-ghost"
                      disabled={remarks.trim().length < 3 || decide.isPending}
                      onClick={() => decide.mutate({ decision: 'MODIFIED', remarks })}
                    >
                      Modify findings
                    </button>
                  </div>
                  {remarks.trim().length < 3 && (
                    <p className="text-2xs text-ink-faint">
                      A written reason is required before any decision can be recorded.
                    </p>
                  )}
                  {decide.error && <ErrorBox error={decide.error} />}
                </>
              ) : (
                <>
                  <p className="text-sm leading-relaxed text-ink-soft">
                    Refer this case to a senior officer if the findings are
                    contested, the evidence is borderline, or the penalty exposure
                    warrants a second signature.
                  </p>
                  <button
                    type="button" className="btn-ghost"
                    disabled={escalate.isPending || s.status === 'PEER_REVIEW'}
                    onClick={() => escalate.mutate('Referred by the inspecting officer')}
                  >
                    <Icon.users size={16} />
                    {s.status === 'PEER_REVIEW'
                      ? 'Already awaiting senior review'
                      : 'Escalate to senior review'}
                  </button>
                  {escalate.error && <ErrorBox error={escalate.error} />}
                </>
              )}
            </Card>
          </Section>

          <Section title="Scoring">
            <ScoreScale />
          </Section>
        </div>
      )}
    </Page>
  );
}
