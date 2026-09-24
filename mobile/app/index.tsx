import { Redirect } from 'expo-router';

import { homeFor, useAuth } from '@/api';
import { Loading, Screen } from '@/ui';

/**
 * Entry route. The gate in _layout handles signed-out users; this only has to
 * decide which portal a signed-in one belongs to, and hold still while the
 * stored session is being restored.
 */
export default function Index() {
  const { status, user } = useAuth();
  if (status === 'loading') {
    return <Screen><Loading label="Restoring your session…" /></Screen>;
  }
  if (status === 'anonymous') return <Redirect href="/login" />;
  return <Redirect href={homeFor(user?.role) as never} />;
}
