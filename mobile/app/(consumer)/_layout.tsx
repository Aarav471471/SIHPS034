import { Feather } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import { Alert, Pressable } from 'react-native';

import { useAuth } from '@/api';
import { space } from '@/theme';
import { usePalette } from '@/ui';

/**
 * Sign out lives in the header, on every tab.
 *
 * It was previously a button at the foot of the Alerts list, which meant a
 * consumer had to scroll past their whole inbox to find it -- effectively no
 * sign-out at all on a shared phone.
 */
function SignOutButton() {
  const p = usePalette();
  const router = useRouter();
  const { user, logout } = useAuth();

  return (
    <Pressable
      hitSlop={12}
      style={{ paddingHorizontal: space.md }}
      accessibilityRole="button"
      accessibilityLabel="Sign out"
      onPress={() =>
        Alert.alert(
          'Sign out',
          `End the session for ${user?.full_name ?? user?.username ?? 'this account'}?`,
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Sign out',
              style: 'destructive',
              onPress: () => { void logout().then(() => router.replace('/login')); },
            },
          ],
        )
      }
    >
      <Feather name="log-out" size={18} color={p.inkMuted} />
    </Pressable>
  );
}

export default function ConsumerLayout() {
  const p = usePalette();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: p.bg },
        headerTintColor: p.ink,
        headerTitleStyle: { fontFamily: 'Fraunces_600SemiBold', fontSize: 19 },
        headerShadowVisible: false,
        headerRight: () => <SignOutButton />,
        tabBarStyle: { backgroundColor: p.surface, borderTopColor: p.line },
        tabBarActiveTintColor: p.accent,
        tabBarInactiveTintColor: p.inkFaint,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        sceneStyle: { backgroundColor: p.bg },
      }}
    >
      <Tabs.Screen
        name="scan"
        options={{
          title: 'Scan',
          tabBarIcon: ({ color, size }) => <Feather name="maximize" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="report"
        options={{
          title: 'Report',
          tabBarIcon: ({ color, size }) => <Feather name="flag" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ color, size }) => <Feather name="bell" size={size - 2} color={color} />,
        }}
      />
    </Tabs>
  );
}
