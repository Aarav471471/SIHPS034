import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { API_BASE, API_BASE_SOURCE, homeFor, useAuth } from '@/api';
import { radius, space } from '@/theme';
import { Body, Button, Callout, Card, Eyebrow, Title, usePalette } from '@/ui';

/**
 * Seeded demo accounts, shown so a reviewer can enter either portal without
 * hunting through documentation. These exist only in the local demo corpus.
 */
const DEMO = [
  { role: 'Field Officer', username: 'officer.sharma', note: 'Delhi Central Zone' },
  { role: 'Senior Officer', username: 'senior.iyer', note: 'Peer review + policy' },
  { role: 'Consumer', username: 'citizen.priya', note: 'Verified Vigilant Citizen' },
];

export default function Login() {
  const { login, busy, error } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const router = useRouter();
  const p = usePalette();
  const insets = useSafeAreaInsets();

  async function submit() {
    if (!username.trim() || !password) return;
    try {
      const profile = await login(username.trim(), password);
      router.replace(homeFor(profile.role) as never);
    } catch {
      /* surfaced from the store */
    }
  }

  const field = {
    backgroundColor: p.surface,
    borderColor: p.line,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: 13,
    color: p.ink,
    fontSize: 15,
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: p.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={{
          padding: space.xl,
          paddingTop: insets.top + space.xxl,
          paddingBottom: insets.bottom + space.xl,
          gap: space.lg,
        }}
        keyboardShouldPersistTaps="handled"
      >
        <View>
          <View
            style={{
              width: 46, height: 46, borderRadius: radius.md,
              backgroundColor: p.accent, alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Text style={{ color: p.accentFg, fontSize: 24, fontWeight: '900' }}>M</Text>
          </View>
          <Eyebrow>Packaged Commodities Rules 2011</Eyebrow>
          <Title size={32} style={{ marginTop: space.sm }}>
            AI-assisted enforcement a court can rely on.
          </Title>
          <Body style={{ marginTop: space.md }}>
            Vision AI proposes what it reads on a pack. Deterministic OCR re-reads the
            same pixels. A rules engine checks the arithmetic against the Rules. A
            human approves the notice.
          </Body>
        </View>

        <Card style={{ gap: space.md }}>
          <Title size={20}>Sign in</Title>

          <View>
            <Eyebrow>Username or email</Eyebrow>
            <TextInput
              style={[field, { marginTop: 6 }]}
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="officer.sharma"
              placeholderTextColor={p.inkFaint}
              returnKeyType="next"
            />
          </View>

          <View>
            <Eyebrow>Password</Eyebrow>
            <TextInput
              style={[field, { marginTop: 6 }]}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="••••••••"
              placeholderTextColor={p.inkFaint}
              returnKeyType="go"
              onSubmitEditing={submit}
            />
          </View>

          {error && <Callout tone="bad">{error}</Callout>}

          <Button label={busy ? 'Signing in…' : 'Sign in'} onPress={submit} busy={busy} />
        </Card>

        <Card tone="sunk" style={{ gap: space.sm }}>
          <Eyebrow>Demo accounts</Eyebrow>
          {DEMO.map((d) => (
            <Pressable
              key={d.username}
              onPress={() => { setUsername(d.username); setPassword('Metrix@2026'); }}
              style={({ pressed }) => ({
                flexDirection: 'row', alignItems: 'center', gap: space.md,
                paddingVertical: space.sm, opacity: pressed ? 0.6 : 1,
              })}
            >
              <View style={{ flex: 1 }}>
                <Text style={{ color: p.ink, fontWeight: '700', fontSize: 14 }}>{d.role}</Text>
                <Text style={{ color: p.inkMuted, fontSize: 11.5 }}>{d.note}</Text>
              </View>
              <Text style={{ color: p.inkMuted, fontSize: 11, fontVariant: ['tabular-nums'] }}>
                {d.username}
              </Text>
            </Pressable>
          ))}
          <Text style={{ color: p.inkMuted, fontSize: 11.5 }}>
            Password for all demo accounts:{' '}
            <Text style={{ fontWeight: '700', color: p.inkSoft }}>Metrix@2026</Text>
          </Text>
        </Card>

        {/* A phone cannot reach the laptop's localhost. Stating the address the
            app will actually call turns the commonest setup failure from a
            mystery into a one-line fix. */}
        <Text style={{ color: p.inkFaint, fontSize: 11, textAlign: 'center', lineHeight: 16 }}>
          Server: {API_BASE}
          {'\n'}
          ({API_BASE_SOURCE})
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
