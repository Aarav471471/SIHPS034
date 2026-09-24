import { useMutation } from '@tanstack/react-query';
import clsx from 'clsx';
import { useEffect, useState } from 'react';

import { Page } from '@/components/motion';
import { ErrorBox, PageHeader } from '@/components/ui';
import { api } from '@/store/auth';

const CATEGORIES = [
  { value: 'OVERCHARGING', label: 'Charged above the printed MRP' },
  { value: 'MISSING_MRP', label: 'No price printed on the pack' },
  { value: 'MISSING_EXPIRY', label: 'No expiry or best-before date' },
  { value: 'EXPIRED_STOCK', label: 'Expired stock on sale' },
  { value: 'MISSING_NET_QTY', label: 'No net quantity declared' },
  { value: 'OTHER', label: 'Something else' },
];

export default function ReportForm() {
  const [form, setForm] = useState({
    store_name: '', store_address: '', violation_category: 'OVERCHARGING',
    remarks: '', barcode: '', claimed_mrp: '', charged_price: '',
  });
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setGps({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => setGps(null),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);

  useEffect(() => {
    if (!photo) { setPreview(null); return; }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const submit = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('store_name', form.store_name);
      fd.append('violation_category', form.violation_category);
      if (form.remarks) fd.append('remarks', form.remarks);
      if (form.store_address) fd.append('store_address', form.store_address);
      if (form.barcode) fd.append('barcode', form.barcode);
      if (form.claimed_mrp) fd.append('claimed_mrp', form.claimed_mrp);
      if (form.charged_price) fd.append('charged_price', form.charged_price);
      if (gps) {
        fd.append('latitude', String(gps.lat));
        fd.append('longitude', String(gps.lng));
      }
      if (photo) fd.append('image', photo, photo.name);
      return api.submitReport(fd);
    },
  });

  if (submit.isSuccess) {
    const r = submit.data;
    return (
      <div className="mx-auto max-w-lg">
        <div className="surface border-ok/30 bg-ok-soft p-6 text-center">
          <p className="text-lg font-bold text-ok">Report filed</p>
          <p className="mt-1 font-mono text-sm text-ok">{r.report_id}</p>
          <p className="mt-3 text-sm text-ink-soft">{r.queue_guidance}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-surface p-3">
              <dt className="text-xs text-ink-muted">Your trust score</dt>
              <dd className="text-xl font-bold">{r.reporter_trust_score}</dd>
            </div>
            <div className="rounded-lg bg-surface p-3">
              <dt className="text-xs text-ink-muted">Queue priority</dt>
              <dd className="text-xl font-bold">{r.priority_score}</dd>
            </div>
          </dl>
          <button
            type="button" className="btn-primary mt-5"
            onClick={() => { submit.reset(); setPhoto(null); }}
          >
            File another report
          </button>
        </div>
      </div>
    );
  }

  return (
    <Page className="mx-auto max-w-lg space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Citizen report</span>}
        title="Report a violation"
        subtitle="This goes into a Legal Metrology enforcement queue. A photograph and a location fix make it far more actionable, and a confirmed report raises your trust score — which moves your future reports up the queue."
      />

      <form
        className="surface space-y-4 p-5"
        onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}
      >
        <div>
          <label className="label" htmlFor="cat">What is wrong?</label>
          <select
            id="cat" className="input" value={form.violation_category}
            onChange={(e) => setForm({ ...form, violation_category: e.target.value })}
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="store">Shop name</label>
          <input
            id="store" className="input" required value={form.store_name}
            onChange={(e) => setForm({ ...form, store_name: e.target.value })}
            placeholder="Gupta General Store"
          />
        </div>

        <div>
          <label className="label" htmlFor="addr">Shop address</label>
          <input
            id="addr" className="input" value={form.store_address}
            onChange={(e) => setForm({ ...form, store_address: e.target.value })}
            placeholder="B-14 Lajpat Nagar II, New Delhi"
          />
        </div>

        {form.violation_category === 'OVERCHARGING' && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="mrp">Printed MRP</label>
              <input
                id="mrp" className="input" type="number" step="0.01" inputMode="decimal"
                value={form.claimed_mrp}
                onChange={(e) => setForm({ ...form, claimed_mrp: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="paid">You were charged</label>
              <input
                id="paid" className="input" type="number" step="0.01" inputMode="decimal"
                value={form.charged_price}
                onChange={(e) => setForm({ ...form, charged_price: e.target.value })}
              />
            </div>
          </div>
        )}

        <div>
          <label className="label" htmlFor="barcode">Barcode (optional)</label>
          <input
            id="barcode" className="input font-mono" inputMode="numeric" value={form.barcode}
            onChange={(e) => setForm({ ...form, barcode: e.target.value })}
            placeholder="8901234567890"
          />
        </div>

        <div>
          <label className="label" htmlFor="remarks">What happened?</label>
          <textarea
            id="remarks" className="input" rows={3} value={form.remarks}
            onChange={(e) => setForm({ ...form, remarks: e.target.value })}
            placeholder="A new MRP sticker was pasted over the printed price."
          />
        </div>

        <div>
          <label className="label">Photograph</label>
          {preview ? (
            <div className="relative">
              <img src={preview} alt="Evidence" className="w-full rounded-lg" />
              <button
                type="button" onClick={() => setPhoto(null)}
                className="absolute right-2 top-2 rounded-lg bg-black/60 px-2 py-1 text-xs text-white"
              >
                Remove
              </button>
            </div>
          ) : (
            <label className="btn-ghost w-full cursor-pointer justify-center py-6">
              Take or choose a photo
              <input
                type="file" accept="image/*" capture="environment" className="hidden"
                onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
        </div>

        <div className={clsx(
          'rounded-lg px-3 py-2 text-xs font-medium',
          gps ? 'bg-ok-soft text-ok' : 'bg-surface-sunk text-ink-muted',
        )}>
          {gps
            ? `Location attached (${gps.lat.toFixed(4)}, ${gps.lng.toFixed(4)})`
            : 'No location fix. The report is still accepted, but is harder for an officer to act on.'}
        </div>

        {submit.error && <ErrorBox error={submit.error} />}

        <button
          type="submit" className="btn-primary w-full py-3"
          disabled={submit.isPending || !form.store_name}
        >
          {submit.isPending ? 'Filing…' : 'File this report'}
        </button>

        <p className="text-xs text-ink-muted">
          A report found to be false costs twice what a confirmed report earns.
          Please report only what you actually saw.
        </p>
      </form>
    </Page>
  );
}
