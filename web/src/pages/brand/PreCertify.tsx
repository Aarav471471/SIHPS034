import { useMutation } from '@tanstack/react-query';
import clsx from 'clsx';
import { useEffect, useState } from 'react';

import { Page } from '@/components/motion';
import {
  ErrorBox, PageHeader, ScoreScale, SeverityChip, Verdict,
} from '@/components/ui';
import { api } from '@/store/auth';

export default function PreCertify() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [form, setForm] = useState({
    product_name: '', pack_width_cm: '', pack_height_cm: '',
  });

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const audit = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('die_line', file!, file!.name);
      fd.append('product_name', form.product_name);
      fd.append('pack_width_cm', form.pack_width_cm);
      fd.append('pack_height_cm', form.pack_height_cm);
      return api.preCertify(fd);
    },
  });

  const result = audit.data;

  return (
    <Page className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Advisory mode</span>}
        title="Pre-market certification"
        subtitle="Upload label artwork before it goes to print. The same rules engine that enforces in the field runs here without penalty — checking costs nothing, and a bad print run costs a recall."
      />

      <form
        className="surface space-y-4 p-5"
        onSubmit={(e) => { e.preventDefault(); audit.mutate(); }}
      >
        <div>
          <label className="label">Artwork or die-line</label>
          {preview ? (
            <div className="relative">
              <img src={preview} alt="Artwork" className="w-full rounded-lg border border-line" />
              <button
                type="button" onClick={() => setFile(null)}
                className="absolute right-2 top-2 rounded-lg bg-black/60 px-2 py-1 text-xs text-white"
              >
                Replace
              </button>
            </div>
          ) : (
            <label className="btn-ghost w-full cursor-pointer justify-center py-8">
              {file ? file.name : 'Choose a PNG, JPEG or PDF'}
              <input
                type="file" accept="image/png,image/jpeg,image/webp,application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
        </div>

        <div>
          <label className="label" htmlFor="pname">Product name</label>
          <input
            id="pname" className="input" required value={form.product_name}
            onChange={(e) => setForm({ ...form, product_name: e.target.value })}
            placeholder="Parle-G Gold 500g"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="pw">Printed pack width (cm)</label>
            <input
              id="pw" className="input" type="number" step="0.1" required
              value={form.pack_width_cm}
              onChange={(e) => setForm({ ...form, pack_width_cm: e.target.value })}
              placeholder="12.0"
            />
          </div>
          <div>
            <label className="label" htmlFor="ph">Printed pack height (cm)</label>
            <input
              id="ph" className="input" type="number" step="0.1" required
              value={form.pack_height_cm}
              onChange={(e) => setForm({ ...form, pack_height_cm: e.target.value })}
              placeholder="18.0"
            />
          </div>
        </div>
        <p className="text-xs text-ink-muted">
          The physical dimensions set the exact scale, which is what makes the
          font-height check under Rule 11 reliable — more reliable here than in
          the field, where scale must be inferred from a photograph.
        </p>

        {audit.error && <ErrorBox error={audit.error} />}

        <button
          type="submit" className="btn-primary w-full py-3"
          disabled={audit.isPending || !file || !form.product_name || !form.pack_width_cm}
        >
          {audit.isPending ? 'Auditing artwork…' : 'Run the compliance audit'}
        </button>
      </form>

      {result && (
        <div className="space-y-4">
          <Verdict
            score={result.compliance_score}
            title={result.is_compliant
              ? 'Cleared for print'
              : `${result.blocking_issues} issue${result.blocking_issues === 1 ? '' : 's'} to fix before print`}
            subtitle={result.message}
            meta={<code className="font-mono text-2xs text-ink-faint">{result.pre_cert_id}</code>}
            note="Advisory only. Nothing here is a notice and no penalty attaches — this is the same engine the field uses, run before the plates are cut."
          />

          {result.digital_badge_token && (
            <div className="surface border-ok/30 p-4">
              <p className="text-sm font-bold text-ok">Digital Trust Mark issued</p>
              <p className="mt-1 text-xs text-ink-muted">
                Print this token as a QR code on the pack. Any shopper can verify
                it without an account.
              </p>
              <code className="mt-2 block break-all rounded bg-surface-sunk px-3 py-2 text-xs">
                {result.digital_badge_token}
              </code>
            </div>
          )}

          {result.warnings.map((w) => (
            <p key={w} className="rounded-lg bg-surface-sunk px-3 py-2 text-xs text-ink-muted">
              {w}
            </p>
          ))}

          {result.findings.length > 0 && (
            <section className="space-y-3">
              <h3 className="display text-xl font-semibold">Findings</h3>
              {result.findings.map((f, i) => (
                <article
                  key={`${f.rule}-${i}`}
                  className={clsx('surface border-l-4 p-4',
                    f.status === 'FAIL' ? 'border-l-bad' : 'border-l-warn',
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-bold">{f.rule_name}</h4>
                    <SeverityChip severity={f.severity} />
                    <span className={clsx(
                      'chip',
                      f.status === 'FAIL' ? 'bg-bad-soft text-bad' : 'bg-warn-soft text-warn',
                    )}>
                      {f.status === 'FAIL' ? 'Blocks certification' : 'Advisory'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs font-medium text-accent">{f.clause}</p>
                  <p className="mt-2 text-sm text-ink-soft">{f.message}</p>

                  {(f.measured || f.required) && (
                    <dl className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-surface-sunk p-3 text-sm">
                      <div>
                        <dt className="text-xs text-ink-muted">In your artwork</dt>
                        <dd className="font-semibold text-bad">{f.measured ?? '—'}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-muted">Required</dt>
                        <dd className="font-semibold text-ok">{f.required ?? '—'}</dd>
                      </div>
                    </dl>
                  )}

                  {f.fix && (
                    <p className="mt-2 rounded-lg bg-info-soft px-3 py-2 text-sm text-info">
                      <span className="font-semibold">Fix: </span>{f.fix}
                    </p>
                  )}
                </article>
              ))}
            </section>
          )}

          {Object.keys(result.measured_font_heights_mm).length > 0 && (
            <section>
              <h3 className="display text-xl font-semibold">Measured declaration heights</h3>
              <div className="surface mt-2 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-line bg-surface-sunk text-left text-xs uppercase text-ink-muted">
                    <tr>
                      <th className="px-4 py-2">Declaration</th>
                      <th className="px-4 py-2">Value read</th>
                      <th className="px-4 py-2">Height</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {Object.entries(result.measured_font_heights_mm).map(([k, mm]) => (
                      <tr key={k}>
                        <td className="px-4 py-2 font-medium">{k.replace(/_/g, ' ')}</td>
                        <td className="px-4 py-2 text-ink-muted">
                          {result.extracted_declarations[k] ?? '—'}
                        </td>
                        <td className={clsx(
                          'px-4 py-2 font-semibold tabular-nums',
                          mm < 1.0 && 'text-bad',
                        )}>
                          {mm} mm
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}

      <ScoreScale />
    </Page>
  );
}
