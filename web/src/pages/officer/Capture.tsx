import clsx from 'clsx';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Page } from '@/components/motion';
import { PageHeader, Section } from '@/components/ui';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import {
  analyseFrame, barcodeSupported, drawOverlay, type FrameAnalysis,
} from '@/lib/arDetector';
import { enqueueCapture } from '@/lib/offlineQueue';
import { api } from '@/store/auth';

const SURFACES = ['FRONT', 'BACK', 'SIDE', 'BOTTOM', 'CAP'] as const;
type Surface = (typeof SURFACES)[number];

interface Shot {
  surface: Surface;
  blob: Blob;
  url: string;
  barcode?: string | null;
}

export default function Capture() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const workRef = useRef<HTMLCanvasElement>(document.createElement('canvas'));
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number>(0);

  const [cameraOn, setCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<FrameAnalysis | null>(null);
  const [surface, setSurface] = useState<Surface>('FRONT');
  const [shots, setShots] = useState<Shot[]>([]);
  const [gps, setGps] = useState<{ lat: number; lng: number; accuracy: number } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [form, setForm] = useState({
    product_name: '', brand_name: '', barcode: '', store_name: '',
    location_address: '', package_width_cm: '', package_height_cm: '',
  });

  const navigate = useNavigate();
  const { sync } = useOfflineQueue();

  // Physical scale is only knowable once the officer states the pack width;
  // without it the HUD reports geometry but never millimetres, rather than
  // inventing a measurement.
  const pxPerMm = (() => {
    const width = parseFloat(form.package_width_cm);
    const video = videoRef.current;
    if (!width || !video?.videoWidth) return undefined;
    // Assume the pack spans roughly 70% of the frame when properly framed.
    return (video.videoWidth * 0.7) / (width * 10);
  })();

  // ------------------------------------------------------------- camera --
  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
    } catch (err) {
      setCameraError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Camera permission denied. Allow camera access, or upload a photograph instead.'
          : 'No camera available on this device. Upload a photograph instead.',
      );
    }
  }, []);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraOn(false);
    setAnalysis(null);
  }, []);

  useEffect(() => () => {
    stopCamera();
    cancelAnimationFrame(rafRef.current);
  }, [stopCamera]);

  // --- analysis loop ---
  useEffect(() => {
    if (!cameraOn) return;
    let alive = true;
    let last = 0;

    const tick = async (t: number) => {
      if (!alive) return;
      // ~6 analyses/second. Faster adds no useful information to a human eye
      // and drains the battery an officer needs for the rest of their shift.
      if (t - last > 160 && videoRef.current) {
        last = t;
        const result = await analyseFrame(videoRef.current, workRef.current, pxPerMm);
        if (!alive) return;
        setAnalysis(result);
        const canvas = overlayRef.current;
        const video = videoRef.current;
        if (canvas && video) {
          drawOverlay(
            canvas, result,
            canvas.clientWidth, canvas.clientHeight,
            video.videoWidth, video.videoHeight,
          );
        }
        // A decoded barcode is hard evidence of identity -- fill it in rather
        // than making the officer type thirteen digits.
        if (result?.barcode?.value) {
          setForm((f) => (f.barcode ? f : { ...f, barcode: result.barcode!.value }));
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      alive = false;
      cancelAnimationFrame(rafRef.current);
    };
  }, [cameraOn, pxPerMm]);

  // --------------------------------------------------------------- gps --
  useEffect(() => {
    if (!navigator.geolocation) return;
    const id = navigator.geolocation.watchPosition(
      (p) => setGps({
        lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy,
      }),
      () => setGps(null),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, []);

  // ------------------------------------------------------------ capture --
  const shoot = useCallback(async () => {
    const video = videoRef.current;
    if (!video?.videoWidth) return;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0);

    const blob = await new Promise<Blob | null>((res) =>
      canvas.toBlob(res, 'image/jpeg', 0.92),
    );
    if (!blob) return;

    setShots((prev) => [
      ...prev.filter((s) => s.surface !== surface),
      {
        surface,
        blob,
        url: URL.createObjectURL(blob),
        barcode: analysis?.barcode?.value ?? null,
      },
    ]);

    // Advance to the next uncaptured surface so the officer keeps moving.
    const next = SURFACES.find(
      (s) => s !== surface && !shots.some((x) => x.surface === s),
    );
    if (next) setSurface(next);
  }, [analysis, shots, surface]);

  const pickFile = useCallback(async (file: File) => {
    setShots((prev) => [
      ...prev.filter((s) => s.surface !== surface),
      { surface, blob: file, url: URL.createObjectURL(file) },
    ]);
  }, [surface]);

  // ------------------------------------------------------------- submit --
  async function submit() {
    if (!shots.length) {
      setMessage('Capture at least one surface first.');
      return;
    }
    setSubmitting(true);
    setMessage(null);

    const session = {
      product_name: form.product_name || undefined,
      brand_name: form.brand_name || undefined,
      barcode: form.barcode || undefined,
      store_name: form.store_name || undefined,
      location_address: form.location_address || undefined,
      package_width_cm: form.package_width_cm ? Number(form.package_width_cm) : undefined,
      package_height_cm: form.package_height_cm ? Number(form.package_height_cm) : undefined,
      latitude: gps?.lat,
      longitude: gps?.lng,
      captured_at: new Date().toISOString(),
    };

    try {
      if (!navigator.onLine) throw new Error('offline');

      const created = await api.createSession(session);
      for (const shot of shots) {
        await api.uploadSurface(
          created.session_id, shot.blob, shot.surface,
          `${shot.surface.toLowerCase()}.jpg`,
        );
      }
      await api.processSession(created.session_id);
      stopCamera();
      navigate(`/officer/sessions/${created.session_id}`);
    } catch {
      // Anything that stops the upload -- no signal, a dead gateway -- must not
      // lose the evidence. It goes to the device queue and drains later.
      await enqueueCapture(
        session,
        shots.map((s) => ({
          surfaceType: s.surface,
          blob: s.blob,
          filename: `${s.surface.toLowerCase()}.jpg`,
        })),
      );
      setShots([]);
      setMessage(
        'Saved on this device. It will upload automatically when you have signal.',
      );
      void sync();
    } finally {
      setSubmitting(false);
    }
  }

  const captured = new Set(shots.map((s) => s.surface));

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Field capture</span>}
        title="New inspection"
        subtitle="Photograph every panel that carries declarations. The front is required; a second surface is what lets the engine prove a declaration is absent rather than merely unphotographed."
      />

      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        {/* ------------------------------------------------ viewfinder -- */}
        <div className="space-y-3">
          <div className="relative aspect-[3/4] overflow-hidden rounded-xl bg-ink">
            <video
              ref={videoRef}
              playsInline muted
              className="size-full object-cover"
            />
            <canvas
              ref={overlayRef}
              className="pointer-events-none absolute inset-0 size-full"
            />

            {!cameraOn && (
              <div className="absolute inset-0 grid place-items-center p-6 text-center">
                <div>
                  <p className="text-sm text-white/80">
                    {cameraError ?? 'Live viewfinder with on-device capture checks'}
                  </p>
                  <button type="button" onClick={startCamera} className="btn-primary mt-3">
                    Start camera
                  </button>
                  <label className="btn-ghost mt-2 block cursor-pointer">
                    Upload a photograph
                    <input
                      type="file" accept="image/*" capture="environment" className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void pickFile(f);
                      }}
                    />
                  </label>
                </div>
              </div>
            )}

            {/* Live capture-quality readout. Deliberately about framing and
                legibility -- the things a phone can actually know. */}
            {cameraOn && analysis && (
              <div className="absolute inset-x-0 top-0 space-y-1 bg-gradient-to-b from-black/70 to-transparent p-3">
                <div className="flex items-center gap-2 text-[11px] font-semibold text-white">
                  <span className={clsx(
                    'chip', analysis.ready ? 'bg-ok text-white' : 'bg-warn text-white',
                  )}>
                    {analysis.ready ? 'Ready to capture' : 'Adjust framing'}
                  </span>
                  <span className="opacity-80">{analysis.regions.length} text blocks</span>
                  {analysis.barcode && (
                    <span className="chip bg-white/15 text-white ring-1 ring-inset ring-white/25">
                      {analysis.barcode.format.toUpperCase()}
                    </span>
                  )}
                </div>
                {analysis.advice.slice(0, 2).map((a) => (
                  <p key={a} className="text-[11px] font-medium text-amber-200">{a}</p>
                ))}
              </div>
            )}

            {cameraOn && (
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-3 bg-gradient-to-t from-black/70 to-transparent p-4">
                <button type="button" onClick={stopCamera} className="text-xs font-semibold text-white/80">
                  Stop
                </button>
                <button
                  type="button" onClick={shoot}
                  className={clsx(
                    'size-16 rounded-full border-4 border-white transition',
                    analysis?.ready ? 'bg-ok' : 'bg-white/30',
                  )}
                  aria-label={`Capture ${surface} surface`}
                />
                <span className="text-xs font-semibold text-white/80">{surface}</span>
              </div>
            )}
          </div>

          {/* Surface selector */}
          <div className="flex flex-wrap gap-2">
            {SURFACES.map((s) => (
              <button
                key={s} type="button" onClick={() => setSurface(s)}
                className={clsx(
                  'chip border transition',
                  s === surface
                    ? 'border-accent bg-accent text-accent-fg'
                    : captured.has(s)
                      ? 'border-ok/30 bg-ok-soft text-ok'
                      : 'border-line-strong bg-surface text-ink-soft hover:border-accent/40',
                )}
              >
                {captured.has(s) && '✓ '}{s}
              </button>
            ))}
          </div>

          {shots.length > 0 && (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {shots.map((s) => (
                <figure key={s.surface} className="relative overflow-hidden rounded-lg border border-line">
                  <img src={s.url} alt={s.surface} className="aspect-square w-full object-cover" />
                  <figcaption className="absolute inset-x-0 bottom-0 bg-black/60 px-1 py-0.5 text-center text-[10px] font-semibold text-white">
                    {s.surface}
                  </figcaption>
                  <button
                    type="button"
                    onClick={() => setShots((p) => p.filter((x) => x.surface !== s.surface))}
                    className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-black/60 text-xs text-white"
                    aria-label={`Remove ${s.surface}`}
                  >
                    ×
                  </button>
                </figure>
              ))}
            </div>
          )}

          {!barcodeSupported() && (
            <p className="text-xs text-ink-muted">
              This browser has no barcode API — enter the barcode manually. The
              server still decodes it from the uploaded photograph.
            </p>
          )}
        </div>

        {/* ---------------------------------------------------- details -- */}
        <div className="space-y-4">
          <Section title="Commodity">
            <div className="surface space-y-3 p-4">
              <div>
                <label className="label" htmlFor="product">Product name</label>
                <input
                  id="product" className="input" value={form.product_name}
                  onChange={(e) => setForm({ ...form, product_name: e.target.value })}
                  placeholder="Parle-G Glucose Biscuits"
                />
              </div>
              <div>
                <label className="label" htmlFor="brand">Brand / manufacturer</label>
                <input
                  id="brand" className="input" value={form.brand_name}
                  onChange={(e) => setForm({ ...form, brand_name: e.target.value })}
                  placeholder="Parle Products"
                />
              </div>
              <div>
                <label className="label" htmlFor="barcode">
                  Barcode {analysis?.barcode && <span className="text-ok">· detected</span>}
                </label>
                <input
                  id="barcode" className="input font-mono" value={form.barcode}
                  onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                  placeholder="8901234567890" inputMode="numeric"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="w">Pack width (cm)</label>
                  <input
                    id="w" className="input" type="number" step="0.1" inputMode="decimal"
                    value={form.package_width_cm}
                    onChange={(e) => setForm({ ...form, package_width_cm: e.target.value })}
                    placeholder="12.0"
                  />
                </div>
                <div>
                  <label className="label" htmlFor="h">Pack height (cm)</label>
                  <input
                    id="h" className="input" type="number" step="0.1" inputMode="decimal"
                    value={form.package_height_cm}
                    onChange={(e) => setForm({ ...form, package_height_cm: e.target.value })}
                    placeholder="18.0"
                  />
                </div>
              </div>
              <p className="text-xs text-ink-muted">
                Pack dimensions set the minimum permitted declaration height under
                Rule 11. Without them the font-height check cannot run, and the
                engine will say so rather than guess.
              </p>
            </div>
          </Section>

          <Section title="Location">
            <div className="surface space-y-3 p-4">
              <div>
                <label className="label" htmlFor="store">Store / premises</label>
                <input
                  id="store" className="input" value={form.store_name}
                  onChange={(e) => setForm({ ...form, store_name: e.target.value })}
                  placeholder="Sharma Supermart"
                />
              </div>
              <div>
                <label className="label" htmlFor="addr">Address</label>
                <input
                  id="addr" className="input" value={form.location_address}
                  onChange={(e) => setForm({ ...form, location_address: e.target.value })}
                  placeholder="12/4 Karol Bagh Main Road, New Delhi"
                />
              </div>
              <div className={clsx(
                'rounded-lg px-3 py-2 text-xs font-medium',
                gps ? 'bg-ok-soft text-ok' : 'bg-surface-sunk text-ink-muted',
              )}>
                {gps
                  ? `GPS fixed: ${gps.lat.toFixed(5)}, ${gps.lng.toFixed(5)} (±${Math.round(gps.accuracy)} m)`
                  : 'Waiting for a GPS fix — the capture is still valid without one, but jurisdiction cannot be verified.'}
              </div>
            </div>
          </Section>

          {message && (
            <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm font-medium text-warn">
              {message}
            </p>
          )}

          <button
            type="button" onClick={submit} disabled={submitting || !shots.length}
            className="btn-primary w-full py-3"
          >
            {submitting
              ? 'Submitting…'
              : `Run inspection on ${shots.length} surface${shots.length === 1 ? '' : 's'}`}
          </button>

          {!navigator.onLine && (
            <p className="text-center text-xs text-ink-muted">
              You are offline. This capture will be stored on the device and
              uploaded automatically.
            </p>
          )}
        </div>
      </div>
    </Page>
  );
}
