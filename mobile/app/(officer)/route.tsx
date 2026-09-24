import { useQuery, keepPreviousData } from '@tanstack/react-query';
import * as Location from 'expo-location';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { api, useAuth } from '@/api';
import { light, radius, riskBand, space } from '@/theme';
import {
  Body, Button, Callout, Card, Chip, Empty, ErrorBox, Eyebrow, Loading, Title,
  usePalette,
} from '@/ui';
import type { GeoJSONPolygon } from '@shared/types';

interface Point { lat: number; lng: number }

const FALLBACK: Point = { lat: 28.6519, lng: 77.1909 };

/** Centroid of a jurisdiction polygon's outer ring. Mirrors the web planner. */
function polygonCentre(geo: GeoJSONPolygon | null | undefined): Point | null {
  if (!geo?.coordinates?.length) return null;
  const first = geo.coordinates[0] as number[][] | number[][][];
  const ring = (Array.isArray(first[0]?.[0]) ? first[0] : first) as number[][];
  if (!ring?.length) return null;
  // GeoJSON is [lng, lat]; Leaflet and the API are [lat, lng].
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
 * Leaflet in a WebView rather than react-native-maps.
 *
 * react-native-maps uses Google Maps on Android, which needs a billed API key
 * before it will render anything but a grey rectangle. Leaflet over OpenStreetMap
 * needs no key, works in Expo Go without a native rebuild, and is the same tile
 * source the web console already uses -- so the two surfaces show the same map.
 */
function mapHtml(origin: Point, stops: Array<{
  rank: number; latitude: number; longitude: number; store_name: string; risk_score: number;
}>): string {
  const path = [[origin.lat, origin.lng], ...stops.map((s) => [s.latitude, s.longitude])];
  const markers = stops.map((s) => ({
    lat: s.latitude, lng: s.longitude, rank: s.rank,
    name: s.store_name, colour: light.score[riskBand(s.risk_score)],
    risk: s.risk_score,
  }));

  return `<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>html,body,#map{height:100%;margin:0;background:#f5f1ea}
.pin{display:grid;place-items:center;border-radius:50%;color:#fff;
  font:700 13px system-ui;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)}</style>
</head><body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  var map = L.map('map').setView([${origin.lat}, ${origin.lng}], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  var path = ${JSON.stringify(path)};
  if (path.length > 1) {
    L.polyline(path, { color: '#19306b', weight: 3, dashArray: '6 8' }).addTo(map);
  }
  L.circleMarker([${origin.lat}, ${origin.lng}], {
    radius: 7, color: '#fff', weight: 3, fillColor: '#19306b', fillOpacity: 1
  }).addTo(map).bindPopup('Start');
  ${JSON.stringify(markers)}.forEach(function (m) {
    L.marker([m.lat, m.lng], {
      icon: L.divIcon({
        className: '',
        html: '<div class="pin" style="width:30px;height:30px;background:' + m.colour + '">' + m.rank + '</div>',
        iconSize: [30, 30], iconAnchor: [15, 15]
      })
    }).addTo(map).bindPopup('<b>' + m.rank + '. ' + m.name + '</b><br>Risk ' + m.risk);
  });
  if (path.length > 1) { map.fitBounds(L.polyline(path).getBounds().pad(0.15)); }
</script></body></html>`;
}

export default function RoutePlanner() {
  const p = usePalette();
  const { user } = useAuth();

  const home = useMemo<Point>(
    () => polygonCentre(user?.jurisdiction_geojson) ?? FALLBACK,
    [user?.jurisdiction_geojson],
  );

  // The jurisdiction centre is the default, not the device fix. An officer
  // plans for the zone they are responsible for; starting from wherever the
  // phone happens to be returns an empty route the moment they are elsewhere.
  const [mode, setMode] = useState<'jurisdiction' | 'device'>('jurisdiction');
  const [device, setDevice] = useState<Point | null>(null);
  const [stops, setStops] = useState(5);
  const [radiusKm, setRadiusKm] = useState(15);

  const origin = mode === 'device' && device ? device : home;
  const drift = device ? haversineKm(home, device) : 0;

  const locate = useCallback(async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return;
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
    setDevice({ lat: pos.coords.latitude, lng: pos.coords.longitude });
    setMode('device');
  }, []);

  const route = useQuery({
    queryKey: ['route', origin.lat, origin.lng, radiusKm, stops],
    queryFn: () => api.routeSuggestions({
      lat: origin.lat, lng: origin.lng, radius_km: radiusKm, max_stops: stops,
    }),
    placeholderData: keepPreviousData,
  });

  const data = route.data;

  const Segmented = ({ value, options, onChange, suffix }: {
    value: number; options: number[]; onChange: (n: number) => void; suffix?: string;
  }) => (
    <View
      style={{
        flexDirection: 'row', backgroundColor: p.surfaceSunk,
        borderRadius: radius.md, padding: 2,
      }}
    >
      {options.map((o) => (
        <Pressable
          key={o}
          onPress={() => onChange(o)}
          style={{
            flex: 1, paddingVertical: 7, borderRadius: radius.sm,
            backgroundColor: o === value ? p.surface : 'transparent',
            alignItems: 'center',
          }}
        >
          <Text
            style={{
              fontSize: 12.5, fontWeight: '700',
              color: o === value ? p.ink : p.inkMuted,
              fontVariant: ['tabular-nums'],
            }}
          >
            {o}{suffix}
          </Text>
        </Pressable>
      ))}
    </View>
  );

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}>
      <View>
        <Eyebrow>Predictive patrol</Eyebrow>
        <Title size={24} style={{ marginTop: 2 }}>Today&apos;s priority route</Title>
        <Body muted size={13}>Stops ranked by risk, then ordered to cut travel time.</Body>
      </View>

      <Card style={{ gap: space.md }}>
        <View>
          <Eyebrow>Start from</Eyebrow>
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: 6 }}>
            <Pressable
              onPress={() => setMode('jurisdiction')}
              style={{
                flex: 1, paddingVertical: 9, borderRadius: radius.md, alignItems: 'center',
                backgroundColor: mode === 'jurisdiction' ? p.accent : p.surfaceSunk,
              }}
            >
              <Text
                numberOfLines={1}
                style={{
                  fontSize: 12.5, fontWeight: '700',
                  color: mode === 'jurisdiction' ? p.accentFg : p.inkMuted,
                }}
              >
                {user?.jurisdiction_name ?? 'Jurisdiction'}
              </Text>
            </Pressable>
            <Pressable
              onPress={() => (device ? setMode('device') : locate())}
              style={{
                flex: 1, paddingVertical: 9, borderRadius: radius.md, alignItems: 'center',
                backgroundColor: mode === 'device' ? p.accent : p.surfaceSunk,
              }}
            >
              <Text
                style={{
                  fontSize: 12.5, fontWeight: '700',
                  color: mode === 'device' ? p.accentFg : p.inkMuted,
                }}
              >
                My location
              </Text>
            </Pressable>
          </View>
        </View>

        <View>
          <Eyebrow>Stops</Eyebrow>
          <View style={{ marginTop: 6 }}>
            <Segmented value={stops} options={[3, 5, 8, 12]} onChange={setStops} />
          </View>
        </View>

        <View>
          <Eyebrow>Radius</Eyebrow>
          <View style={{ marginTop: 6 }}>
            <Segmented value={radiusKm} options={[5, 15, 30, 60]} onChange={setRadiusKm} suffix=" km" />
          </View>
        </View>

        <Text style={{ color: p.inkMuted, fontSize: 11.5 }}>
          {route.isFetching
            ? 'Recomputing route…'
            : `${data?.candidates_considered ?? 0} retailers assessed`}
        </Text>
      </Card>

      {mode === 'device' && drift > 25 && (
        <Callout tone="warn" title={`You are ${Math.round(drift)} km from ${user?.jurisdiction_name ?? 'your jurisdiction'}`}>
          <View style={{ gap: space.sm }}>
            <Text style={{ color: p.warn, fontSize: 12.5, lineHeight: 18 }}>
              Routes are built from retailers inside your jurisdiction, so starting
              here will usually return nothing.
            </Text>
            <Button
              label="Start from the jurisdiction centre"
              tone="ghost"
              onPress={() => setMode('jurisdiction')}
            />
          </View>
        </Callout>
      )}

      {route.error && <ErrorBox error={route.error} onRetry={() => route.refetch()} />}

      {!data ? (
        <Loading label="Building the route…" />
      ) : !data.patrol_route.length ? (
        <Empty
          title="No retailers within range"
          hint={
            mode === 'device' && drift > 25
              ? `Your device is ${Math.round(drift)} km from your jurisdiction, and the route only draws on retailers inside it.`
              : `Nothing on record within ${radiusKm} km. Widen the radius, or capture some inspections — the route is built from inspection history, citizen leads and price anomalies.`
          }
        />
      ) : (
        <>
          <View
            style={{
              height: 320, borderRadius: radius.lg, overflow: 'hidden',
              borderWidth: 1, borderColor: p.line,
            }}
          >
            <WebView
              originWhitelist={['*']}
              source={{ html: mapHtml(origin, data.patrol_route) }}
              style={{ flex: 1, backgroundColor: p.surfaceSunk }}
              scrollEnabled={false}
              // Two-finger pan inside a scrolling page is fiddly; the list below
              // carries the same information in a form that reads on a phone.
              nestedScrollEnabled
            />
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {[
              ['Stops', String(data.summary.stops)],
              ['Distance', `${data.summary.total_distance_km} km`],
              ['Estimated', data.summary.estimated_duration_readable],
              ['Saved', `${data.summary.distance_saved_km} km`],
            ].map(([k, v]) => (
              <Card key={k} style={{ flex: 1, minWidth: 140, padding: space.md }}>
                <Eyebrow>{k}</Eyebrow>
                <Text
                  style={{
                    color: p.ink, fontSize: 19, fontWeight: '800', marginTop: 3,
                    fontVariant: ['tabular-nums'],
                  }}
                >
                  {v}
                </Text>
              </Card>
            ))}
          </View>

          {data.coverage_warnings?.map((w) => (
            <Callout key={w} tone="warn" title="Ordering trade-off">{w}</Callout>
          ))}

          <View style={{ gap: space.sm }}>
            <Title size={19}>Stops in order</Title>
            {data.patrol_route.map((s) => {
              const band = riskBand(s.risk_score);
              return (
                <Card key={s.store_name} style={{ flexDirection: 'row', gap: space.md, padding: space.md }}>
                  <View
                    style={{
                      width: 30, height: 30, borderRadius: 15,
                      backgroundColor: p.score[band],
                      alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <Text style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}>{s.rank}</Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' }}>
                      <Text style={{ color: p.ink, fontWeight: '700', fontSize: 14.5 }}>
                        {s.store_name}
                      </Text>
                      <Chip tone="neutral">{`risk ${s.risk_score}`}</Chip>
                      {s.seasonal_multiplier > 1 && (
                        <Chip tone="warn">{`×${s.seasonal_multiplier} seasonal`}</Chip>
                      )}
                    </View>
                    {s.address && (
                      <Text style={{ color: p.inkMuted, fontSize: 11.5, marginTop: 2 }}>
                        {s.address}
                      </Text>
                    )}
                    {s.risk_reasons.slice(0, 2).map((r) => (
                      <Text key={r} style={{ color: p.inkSoft, fontSize: 12, marginTop: 3 }}>
                        • {r}
                      </Text>
                    ))}
                  </View>
                </Card>
              );
            })}
            <Text style={{ color: p.inkMuted, fontSize: 11.5 }}>
              Ordered by {data.summary.travel_optimisation}. Visiting strictly by risk
              rank would cover {data.summary.distance_if_visited_by_rank_km} km.
            </Text>
          </View>
        </>
      )}
    </ScrollView>
  );
}
