import { Fraunces_600SemiBold, useFonts } from '@expo-google-fonts/fraunces';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { bootstrapAuth, homeFor, useAuth } from '@/api';
import { dark, light } from '@/theme';

void SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, error) => {
        // A 4xx will not become a 2xx on retry; only a transport failure is
        // worth trying again, and an officer on a bad connection should see
        // the failure quickly rather than after four silent attempts.
        const status = (error as { status?: number })?.status;
        if (status && status >= 400 && status < 500) return false;
        return count < 2;
      },
    },
  },
});

/**
 * Sends the user to the right place once auth has settled.
 *
 * Kept as a component inside the provider tree rather than logic in each screen,
 * so there is exactly one place that decides "signed out -> /login".
 */
function AuthGate() {
  const { status, user } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (status === 'loading') return;
    const inAuthGroup = segments[0] === 'login';

    if (status === 'anonymous' && !inAuthGroup) {
      router.replace('/login');
    } else if (status === 'authenticated' && inAuthGroup) {
      router.replace(homeFor(user?.role) as never);
    }
  }, [status, user?.role, segments, router]);

  return null;
}

export default function RootLayout() {
  const scheme = useColorScheme();
  const p = scheme === 'dark' ? dark : light;
  const [fontsLoaded] = useFonts({ Fraunces_600SemiBold });
  const { status } = useAuth();

  useEffect(() => { void bootstrapAuth(); }, []);

  useEffect(() => {
    // Hold the splash until both the font and the stored session have
    // resolved, so the first frame is never an unstyled or wrongly-routed one.
    if (fontsLoaded && status !== 'loading') void SplashScreen.hideAsync();
  }, [fontsLoaded, status]);

  if (!fontsLoaded) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
          <AuthGate />
          <Stack
            screenOptions={{
              headerStyle: { backgroundColor: p.bg },
              headerTintColor: p.ink,
              headerTitleStyle: { fontFamily: 'Fraunces_600SemiBold', fontSize: 18 },
              headerShadowVisible: false,
              contentStyle: { backgroundColor: p.bg },
            }}
          >
            <Stack.Screen name="login" options={{ headerShown: false }} />
            <Stack.Screen name="(officer)" options={{ headerShown: false }} />
            <Stack.Screen name="(consumer)" options={{ headerShown: false }} />
            <Stack.Screen
              name="session/[id]"
              options={{ title: 'Inspection', presentation: 'card' }}
            />
          </Stack>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
