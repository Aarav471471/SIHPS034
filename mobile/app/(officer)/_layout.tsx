import { Feather } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { useEffect, useState } from 'react';

import { pendingCount, subscribe, type QueuedCapture } from '@/queue';
import { usePalette } from '@/ui';

export default function OfficerLayout() {
  const p = usePalette();
  const [pending, setPending] = useState(0);

  // The queue badge is the officer's only signal that work is still on the
  // device and not yet with the department, so it lives in the chrome rather
  // than on a screen they might not open.
  useEffect(() => subscribe((items: QueuedCapture[]) => setPending(pendingCount(items))), []);

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: p.bg },
        headerTintColor: p.ink,
        headerTitleStyle: { fontFamily: 'Fraunces_600SemiBold', fontSize: 19 },
        headerShadowVisible: false,
        tabBarStyle: { backgroundColor: p.surface, borderTopColor: p.line },
        tabBarActiveTintColor: p.accent,
        tabBarInactiveTintColor: p.inkFaint,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        sceneStyle: { backgroundColor: p.bg },
      }}
    >
      <Tabs.Screen
        name="today"
        options={{
          title: 'Today',
          tabBarIcon: ({ color, size }) => <Feather name="grid" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="capture"
        options={{
          title: 'Inspect',
          tabBarIcon: ({ color, size }) => <Feather name="camera" size={size - 2} color={color} />,
          tabBarBadge: pending > 0 ? pending : undefined,
          tabBarBadgeStyle: { backgroundColor: p.warn, fontSize: 10 },
        }}
      />
      <Tabs.Screen
        name="route"
        options={{
          title: 'Route',
          tabBarIcon: ({ color, size }) => <Feather name="map" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="leads"
        options={{
          title: 'Leads',
          tabBarIcon: ({ color, size }) => <Feather name="flag" size={size - 2} color={color} />,
        }}
      />
    </Tabs>
  );
}
