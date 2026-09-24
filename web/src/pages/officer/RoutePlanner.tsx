import { keepPreviousData, useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import L from 'leaflet';
import { useEffect, useMemo, useState } from 'react';
import { MapContainer, Marker, Polyline, Popup, TileLayer } from 'react-leaflet';

import { Icon } from '@/components/icons';
import { Page } from '@/components/motion';
import {
  Callout, Card, Empty, ErrorBox, Loading, PageHeader, Section, Stagger, Stat,
} from '@/components/ui';
import { api, useAuth } from '@/store/auth';
import type { GeoJSONPolygon } from '@shared/types';

/** Risk maps onto the same five-band ramp the compliance scores use, inverted:
 *  high risk lands in the band a LOW score would, so the two never disagree.
 *  Band 1 is the clean/green end and band 5 the severe/red end, so a risk of 80
 *  belongs at 5 -- getting this backwards paints the worst shop green. */
function riskBand(risk: number): number {
  return risk >= 70 ? 5 : risk >= 40 ? 3 : 1;
}

// Leaflet's default marker images resolve to broken paths under a bundler.
// Numbered inline markers are also simply better here: the officer needs to see
// the visit order, not identical pins.
function stopIcon(rank: number, risk: number): L.DivIcon {
  const colour = `hsl(var(--score-${riskBand(risk)}))`;
  return L.divIcon({
    className: '',
    html: `<div style="
      width:30px;height:30px;border-radius:50%;background:${colour};
      color:#fff;display:grid;place-items:center;font:700 13px system-ui;
      border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)">${rank}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

const startIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:18px;height:18px;border-radius:50%;background:hsl(var(--accent));
    border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)"></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

interface Point { lat: number; lng: number }

// Karol Bagh — the seeded Delhi Central Zone centre, used only when an officer
// has no jurisdiction polygon on their record at all.
const FALLBACK: Point = { lat: 28.6519, lng: 77.1909 };

/** Centroid of a jurisdiction polygon's outer ring. Accepts Polygon or MultiPolygon. */
function polygonCentre(geo: GeoJSONPolygon | null | undefined): Point | null {
  if (!geo?.coordinates?.length) return null;
  // A Polygon nests rings one deep, a MultiPolygon two. Take the first outer
  // ring either way -- a jurisdiction's centre only needs to be representative.
  const first = geo.coordinates[0] as number[][] | number[][][];
  const ring = (Array.isArray(first[0][0]) ? first[0] : first) as number[][];
  if (!ring?.length) return null;
  // GeoJSON is [lng, lat]. Leaflet and our API are [lat, lng] — mixing the two
  // up puts Delhi in the Indian Ocean, so the swap happens exactly here.
  const sum = ring.reduce(
    (acc, [lng, lat]) => ({ lat: acc.lat + lat, lng: acc.lng + lng }),
    { lat: 0, lng: 0 },
  );
  return { lat: sum.lat / ring.length, lng: sum.lng / ring.length };
}

function haversineKm(a: Point, b: Point): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

/**
 * Debounce a control value before it reaches a query key.
 *
 * Without this every keystroke in the radius or stops field starts a new
 * request, and because a new query key has no cached data the page falls into
 * its loading branch — unmounting the very input being typed into. The field
 * then loses focus after one character and appears frozen.
 */
function useDebounced<T>(value: T, ms = 400): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return settled;
}

type OriginMode = 'jurisdiction' | 'device';

export default function RoutePlanner() {
  const { user } = useAuth();

  const home = useMemo<Point>(
    () => polygonCentre(user?.jurisdiction_geojson) ?? FALLBACK,
    [user?.jurisdiction_geojson],
  );

  // The jurisdiction centre is the default, not the device fix. An officer
  // plans a shift for the zone they are responsible for; where the laptop
  // happens to be sitting is a different question, and defaulting to it
  // silently returns an empty route whenever they are working from elsewhere.
  const [mode, setMode] = useState<OriginMode>('jurisdiction');
  const [device, setDevice] = useState<Point | null>(null);
  const [geoState, setGeoState] = useState<'idle' | 'locating' | 'denied' | 'ok'>('idle');

  const [radius, setRadius] = useState(15);
  const [stops, setStops] = useState(5);
  const debRadius = useDebounced(radius);
  const debStops = useDebounced(stops);

  const origin = mode === 'device' && device ? device : home;
  const drift = device ? haversineKm(home, device) : 0;

  function locate() {
    if (!navigator.geolocation) { setGeoState('denied'); return; }
    setGeoState('locating');
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setDevice({ lat: p.coords.latitude, lng: p.coords.longitude });
        setGeoState('ok');
        setMode('device');
      },
      () => setGeoState('denied'),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  const route = useQuery({
    queryKey: ['route', origin.lat, origin.lng, debRadius, debStops],
    queryFn: () => api.routeSuggestions({
      lat: origin.lat, lng: origin.lng, radius_km: debRadius, max_stops: debStops,
    }),
    // Keep the previous route on screen while a new one is computed, so the
    // map and the controls never unmount mid-adjustment.
    placeholderData: keepPreviousData,
  });

  const data = route.data;
  const busy = route.isFetching;

  const path: [number, number][] = data
    ? [
      [origin.lat, origin.lng],
      ...data.patrol_route.map((s) => [s.latitude, s.longitude] as [number, number]),
    ]
    : [];

  const controls = (
    <Card className="flex flex-wrap items-end gap-x-5 gap-y-4 p-4">
      <fieldset className="min-w-0">
        <legend className="label">Start from</legend>
        <div className="flex rounded-lg border border-line bg-surface-sunk p-0.5">
          <button
            type="button"
            onClick={() => setMode('jurisdiction')}
            className={clsx(
              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              mode === 'jurisdiction'
                ? 'bg-surface text-ink shadow-xs'
                : 'text-ink-muted hover:text-ink',
            )}
          >
            {user?.jurisdiction_name ?? 'Jurisdiction'}
          </button>
          <button
            type="button"
            onClick={() => (device ? setMode('device') : locate())}
            className={clsx(
              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              mode === 'device'
                ? 'bg-surface text-ink shadow-xs'
                : 'text-ink-muted hover:text-ink',
            )}
          >
            {geoState === 'locating' ? 'Locating…' : 'My location'}
          </button>
        </div>
      </fieldset>

      <div>
        <label className="label" htmlFor="radius">Radius (km)</label>
        <input
          id="radius" type="number" min={1} max={100} value={radius}
          onChange={(e) => {
            const n = Number(e.target.value);
            // An empty field parses as 0; clamping on every keystroke would
            // fight the typist, so only the query-bound value is guarded.
            setRadius(Number.isFinite(n) ? n : 0);
          }}
          onBlur={() => setRadius((r) => Math.min(100, Math.max(1, r || 1)))}
          className="input w-24"
        />
      </div>

      <div>
        <label className="label" htmlFor="stops">Stops</label>
        <input
          id="stops" type="number" min={1} max={12} value={stops}
          onChange={(e) => {
            const n = Number(e.target.value);
            setStops(Number.isFinite(n) ? n : 0);
          }}
          onBlur={() => setStops((s) => Math.min(12, Math.max(1, s || 1)))}
          className="input w-20"
        />
      </div>

      <p className="ml-auto flex items-center gap-2 text-2xs text-ink-muted">
        {busy && <span className="size-1.5 animate-pulse rounded-full bg-accent" />}
        {busy
          ? 'Recomputing route…'
          : `${data?.candidates_considered ?? 0} retailers assessed`}
      </p>
    </Card>
  );

  return (
    <Page className="space-y-5">
      <PageHeader
        eyebrow={<span className="eyebrow">Predictive patrol</span>}
        title="Today's priority route"
        subtitle="Stops ranked by risk, then ordered to cut travel time."
      />

      {controls}

      {geoState === 'denied' && (
        <Callout tone="info" title="Location unavailable">
          The browser would not share a position, so the route starts from your
          jurisdiction centre.
        </Callout>
      )}

      {/* A device fix far outside the officer's zone is the single most common
          reason this page comes back empty. Say so before they conclude the
          planner is broken. */}
      {mode === 'device' && drift > 25 && (
        <Callout tone="warn" title={`You are ${Math.round(drift)} km from ${user?.jurisdiction_name ?? 'your jurisdiction'}`}>
          Routes are built from retailers inside your jurisdiction, so starting
          here will usually return nothing.{' '}
          <button
            type="button"
            onClick={() => setMode('jurisdiction')}
            className="font-semibold underline underline-offset-2"
          >
            Start from the jurisdiction centre instead
          </button>
          .
        </Callout>
      )}

      {route.error && <ErrorBox error={route.error} retry={() => route.refetch()} />}

      {!data ? (
        <Loading rows={4} variant="stats" />
      ) : (
        <>
          {data.coverage_warnings?.map((w) => (
            <Callout key={w} tone="warn" title="Ordering trade-off">{w}</Callout>
          ))}

          <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Stops" value={data.summary.stops} icon="pin" />
            <Stat label="Distance" value={`${data.summary.total_distance_km} km`} icon="route" />
            <Stat label="Estimated" value={data.summary.estimated_duration_readable} icon="clock" />
            <Stat
              label="Saved by ordering"
              value={`${data.summary.distance_saved_km} km`}
              icon="trending"
              tone={data.summary.distance_saved_km > 0 ? 'good' : 'default'}
              hint={`vs ${data.summary.distance_if_visited_by_rank_km} km by risk rank`}
            />
          </Stagger>

          {data.seasonal_context.length > 0 && (
            <Callout tone="warn" icon="sparkle" title="Seasonal risk in effect">
              <ul className="mt-1 space-y-0.5">
                {data.seasonal_context.slice(0, 4).map((c) => (
                  <li key={`${c.festival}-${c.category}`}>
                    <strong>{c.festival}</strong> in {c.days_until} days —{' '}
                    {String(c.category ?? '').replace(/-/g, ' ')} risk ×{c.multiplier}
                  </li>
                ))}
              </ul>
            </Callout>
          )}

          {!data.patrol_route.length ? (
            <Empty
              icon="map"
              title="No retailers within range of this start point"
              hint={
                mode === 'device' && drift > 25
                  ? `Your device is ${Math.round(drift)} km from ${user?.jurisdiction_name ?? 'your jurisdiction'}, and the route only draws on retailers inside it.`
                  : `Nothing on record within ${debRadius} km. Widen the radius, or capture some inspections — the route is built from inspection history, citizen leads and price anomalies.`
              }
              action={
                mode === 'device' ? (
                  <button type="button" className="btn-primary" onClick={() => setMode('jurisdiction')}>
                    <Icon.map size={16} />
                    Start from {user?.jurisdiction_name ?? 'jurisdiction'}
                  </button>
                ) : (
                  <button type="button" className="btn-ghost" onClick={() => setRadius((r) => Math.min(100, r * 2))}>
                    Widen to {Math.min(100, radius * 2)} km
                  </button>
                )
              }
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
              <div className="h-[420px] overflow-hidden rounded-xl border border-line lg:h-[560px]">
                <MapContainer
                  // Remounting on origin change is deliberate: MapContainer
                  // ignores a changed `center` prop after mount, so without this
                  // the map stays on the previous city while the list updates.
                  key={`${origin.lat.toFixed(4)},${origin.lng.toFixed(4)}`}
                  center={[origin.lat, origin.lng]}
                  zoom={12}
                  scrollWheelZoom
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <Polyline
                    positions={path}
                    pathOptions={{ color: 'hsl(var(--accent))', weight: 3, dashArray: '6 8' }}
                  />
                  <Marker position={[origin.lat, origin.lng]} icon={startIcon}>
                    <Popup>Start — {mode === 'device' ? 'your location' : user?.jurisdiction_name}</Popup>
                  </Marker>
                  {data.patrol_route.map((s) => (
                    <Marker
                      key={s.store_name}
                      position={[s.latitude, s.longitude]}
                      icon={stopIcon(s.rank, s.risk_score)}
                    >
                      <Popup>
                        <strong>{s.rank}. {s.store_name}</strong>
                        <br />Risk {s.risk_score}
                        <br />
                        <span style={{ fontSize: 11 }}>{s.risk_reasons[0]}</span>
                      </Popup>
                    </Marker>
                  ))}
                </MapContainer>
              </div>

              <Section title="Stops in order">
                <ol className="space-y-2">
                  {data.patrol_route.map((s) => (
                    <li key={s.store_name} className="surface p-4">
                      <div className="flex items-start gap-3">
                        <span
                          className="nums grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold text-white"
                          style={{ background: `hsl(var(--score-${riskBand(s.risk_score)}))` }}
                        >
                          {s.rank}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-bold">{s.store_name}</h3>
                            <span className="chip nums bg-surface-sunk text-ink-soft">
                              risk {s.risk_score}
                            </span>
                            {s.seasonal_multiplier > 1 && (
                              <span className="chip bg-warn-soft text-warn">
                                ×{s.seasonal_multiplier} seasonal
                              </span>
                            )}
                          </div>
                          {s.address && (
                            <p className="mt-0.5 text-xs text-ink-muted">{s.address}</p>
                          )}
                          <ul className="mt-2 space-y-0.5 text-xs text-ink-soft">
                            {s.risk_reasons.slice(0, 3).map((r) => (
                              <li key={r}>• {r}</li>
                            ))}
                          </ul>
                          {/* Component breakdown makes the score auditable rather
                              than a number the officer has to take on faith. */}
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {Object.entries(s.components).map(([k, v]) => (
                              <span key={k} className="chip bg-surface-sunk text-[10px] text-ink-muted">
                                {k.replace(/_/g, ' ')} {Math.round(v)}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="text-xs text-ink-muted">
                  Ordered by {data.summary.travel_optimisation}. Visiting strictly by
                  risk rank would cover {data.summary.distance_if_visited_by_rank_km} km.
                </p>
              </Section>
            </div>
          )}
        </>
      )}
    </Page>
  );
}
