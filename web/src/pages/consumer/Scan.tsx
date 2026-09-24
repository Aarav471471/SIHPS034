import { useMutation } from '@tanstack/react-query';
import clsx from 'clsx';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Page } from '@/components/motion';
import {
  Callout, ComplianceBadge, ErrorBox, PageHeader, ScoreScale, Verdict,
  money, when,
} from '@/components/ui';
import { barcodeSupported } from '@/lib/arDetector';
import { cacheScan, readCachedScan } from '@/lib/offlineQueue';
import { api } from '@/store/auth';
import type { ScanResponse } from '@shared/types';

export default function Scan() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<any>(null);
  const loopRef = useRef<number>(0);

  const [scanning, setScanning] = useState(false);
  const [barcode, setBarcode] = useState('');
  const [price, setPrice] = useState('');
  const [store, setStore] = useState('');
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setGps({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => setGps(null),
      { timeout: 8000 },
    );
  }, []);

  const lookup = useMutation({
    mutationFn: async (code: string) => {
      const params = {
        barcode: code,
        mrp: price ? Number(price) : undefined,
        lat: gps?.lat,
        lng: gps?.lng,
        store_name: store || undefined,
      };
      try {
        const res = await api.scan(params);
        void cacheScan(code, res);
        setFromCache(false);
        return res;
      } catch (err) {
        // A shopper standing in a shop with no signal still deserves an answer.
        // The cache is age-checked, because a stale MRP could wrongly accuse a
        // retailer of overcharging after a legitimate price revision.
        const cached = (await readCachedScan(code)) as ScanResponse | null;
        if (cached) {
          setFromCache(true);
          return cached;
        }
        throw err;
      }
    },
    onSuccess: (data) => setResult(data),
  });

  const stopCamera = useCallback(() => {
    cancelAnimationFrame(loopRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setScanning(false);
  }, []);

  const startCamera = useCallback(async () => {
    setCameraError(null);
    if (!barcodeSupported()) {
      setCameraError(
        'This browser cannot decode barcodes from a live camera. Type the number below instead.',
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      const Ctor = (window as any).BarcodeDetector;
      detectorRef.current = new Ctor({
        formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'],
      });
      setScanning(true);
    } catch {
      setCameraError('Camera unavailable. Type the barcode number below instead.');
    }
  }, []);

  useEffect(() => {
    if (!scanning) return;
    let alive = true;
    let last = 0;

    const tick = async (t: number) => {
      if (!alive) return;
      if (t - last > 250 && videoRef.current && detectorRef.current) {
        last = t;
        try {
          const found = await detectorRef.current.detect(videoRef.current);
          const value = found?.[0]?.rawValue;
          if (value && alive) {
            setBarcode(String(value));
            stopCamera();
            lookup.mutate(String(value));
            return;
          }
        } catch {
          /* transient frame failure */
        }
      }
      loopRef.current = requestAnimationFrame(tick);
    };

    loopRef.current = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(loopRef.current); };
  }, [scanning, stopCamera, lookup]);

  useEffect(() => () => stopCamera(), [stopCamera]);

  return (
    <Page className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        eyebrow={<span className="eyebrow">Consumer check</span>}
        title="Scan before you buy"
        subtitle="Check the declared price and the compliance record of a packaged commodity before it reaches your basket."
      />

      {scanning ? (
        <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-ink">
          <video ref={videoRef} playsInline muted className="size-full object-cover" />
          <div className="pointer-events-none absolute inset-0 grid place-items-center">
            <div className="h-28 w-64 rounded-lg border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
          </div>
          <p className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-4 text-center text-sm text-white">
            Point at the barcode
          </p>
          <button
            type="button" onClick={stopCamera}
            className="absolute right-3 top-3 rounded-lg bg-black/50 px-3 py-1.5 text-xs font-semibold text-white"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="surface space-y-3 p-4">
          <button type="button" onClick={startCamera} className="btn-primary w-full py-3">
            Scan barcode with camera
          </button>
          {cameraError && <p className="text-xs text-warn">{cameraError}</p>}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="barcode">Barcode number</label>
              <input
                id="barcode" className="input font-mono" inputMode="numeric"
                value={barcode} onChange={(e) => setBarcode(e.target.value)}
                placeholder="8901234567890"
              />
            </div>
            <div>
              <label className="label" htmlFor="price">Price on the pack (₹)</label>
              <input
                id="price" className="input" type="number" step="0.01" inputMode="decimal"
                value={price} onChange={(e) => setPrice(e.target.value)}
                placeholder="45.00"
              />
            </div>
            <div>
              <label className="label" htmlFor="store">Shop name (optional)</label>
              <input
                id="store" className="input" value={store}
                onChange={(e) => setStore(e.target.value)}
                placeholder="Gupta General Store"
              />
            </div>
          </div>

          <button
            type="button"
            className="btn-primary w-full"
            disabled={!barcode || lookup.isPending}
            onClick={() => lookup.mutate(barcode)}
          >
            {lookup.isPending ? 'Checking…' : 'Check this product'}
          </button>
          <p className="text-xs text-ink-muted">
            Entering the printed price is what lets us tell you whether you are
            being overcharged. Your scan also helps build the price record for
            everyone else.
          </p>
        </div>
      )}

      {lookup.error && <ErrorBox error={lookup.error} />}

      {result && (
        <div className="space-y-4">
          {fromCache && (
            <p className="rounded-lg bg-surface-sunk px-3 py-2 text-xs text-ink-muted">
              You are offline — showing the last saved result for this product.
            </p>
          )}

          {/* The overcharge warning leads, because it is the one thing that
              changes what the shopper does in the next ten seconds. */}
          {result.is_price_gouged && result.anomaly_warning && (
            <div className="surface overflow-hidden border-bad/40">
              <div className="bg-bad p-5 text-white">
                <p className="eyebrow text-white/70">Price check</p>
                <p className="display mt-1.5 text-2xl font-semibold">
                  You are being overcharged
                </p>
                {result.overcharge_amount != null && (
                  <p className="nums display mt-2 text-display font-semibold leading-none">
                    +{money(result.overcharge_amount)}
                  </p>
                )}
              </div>
              <div className="p-5">
                <p className="text-pretty text-sm leading-relaxed text-ink-soft">
                  {result.anomaly_warning}
                </p>
                <Link to="/report" className="btn-danger mt-4">
                  <Icon.flag size={16} />
                  Report this shop
                </Link>
              </div>
            </div>
          )}

          {!result.found ? (
            <Callout tone="info" title="Not in the compliance catalogue yet">
              {result.message}
            </Callout>
          ) : (
            <div className="space-y-5">
              <Verdict
                score={result.compliance_score}
                title={result.product_name ?? 'Unidentified commodity'}
                subtitle={
                  <>
                    {result.brand_name}
                    {result.category ? ` · ${result.category}` : ''}
                  </>
                }
                meta={
                  <>
                    <ComplianceBadge level={result.badge_level} score={result.compliance_score} />
                    {result.barcode && (
                      <code className="font-mono text-2xs text-ink-faint">{result.barcode}</code>
                    )}
                  </>
                }
                note={
                  result.total_inspections
                    ? `Based on ${result.total_inspections} inspection${result.total_inspections === 1 ? '' : 's'} on record, most recently ${when(result.last_inspected)}.`
                    : 'No inspections on record yet — this score reflects the declared label only.'
                }
              />

            <article className="surface overflow-hidden">
              <dl className="grid grid-cols-2 divide-x divide-y divide-line">
                {[
                  ['Verified MRP', money(result.official_mrp)],
                  ['Net quantity', result.net_quantity ?? '—'],
                  ['Unit price', result.unit_price ?? '—'],
                  ['Country of origin', result.country_of_origin ?? '—'],
                ].map(([k, v]) => (
                  <div key={String(k)} className="p-4">
                    <dt className="eyebrow">{k}</dt>
                    <dd className="nums mt-1.5 text-lg font-semibold">{v}</dd>
                  </div>
                ))}
              </dl>

              <div className="space-y-2 border-t border-line p-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-ink-muted">FSSAI licence</span>
                  <span className={clsx('font-semibold', result.fssai_verified ? 'text-ok' : 'text-ink-muted')}>
                    {result.fssai_number ?? 'Not declared'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-ink-muted">Past violations</span>
                  <span className={clsx('font-semibold', result.past_violations ? 'text-bad' : 'text-ok')}>
                    {result.past_violations}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-ink-muted">Inspections on record</span>
                  <span className="font-semibold">{result.total_inspections}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-ink-muted">Last inspected</span>
                  <span className="font-semibold">{when(result.last_inspected)}</span>
                </div>
                {result.crowd_sample_count > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-ink-muted">Typical price seen by shoppers</span>
                    <span className="font-semibold">
                      {money(result.crowd_modal_mrp)}{' '}
                      <span className="text-xs font-normal text-ink-muted">
                        ({result.crowd_sample_count} scans)
                      </span>
                    </span>
                  </div>
                )}
              </div>

              {!result.is_price_gouged && result.scanned_mrp != null && (
                <p className="border-t border-line bg-ok-soft p-4 text-sm font-medium text-ok">
                  The price on this pack matches its declared MRP.
                </p>
              )}

              {result.barcode && (
                <Link
                  to={`/catalogue/${result.barcode}`}
                  className="block border-t border-line p-4 text-center text-sm font-semibold text-accent hover:bg-surface-sunk"
                >
                  Full compliance history →
                </Link>
              )}
            </article>

            <ScoreScale />
            </div>
          )}
        </div>
      )}
    </Page>
  );
}
