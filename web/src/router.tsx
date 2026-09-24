import { Suspense, lazy, useEffect, type ReactNode } from 'react';
import { Navigate, createBrowserRouter, useLocation } from 'react-router-dom';

import { Shell } from '@/components/Shell';
import { homeFor, useAuth } from '@/store/auth';

import Login from '@/pages/Login';

// Route-level code splitting. The bundle is otherwise dominated by
// Recharts (policy) and Leaflet (routing), and an officer opening the
// capture screen on a weak connection should not pay for either.
const OfficerDashboard = lazy(() => import('@/pages/officer/Dashboard'));
const Capture = lazy(() => import('@/pages/officer/Capture'));
const SessionDetailPage = lazy(() => import('@/pages/officer/SessionDetail'));
const RoutePlanner = lazy(() => import('@/pages/officer/RoutePlanner'));
const Leads = lazy(() => import('@/pages/officer/Leads'));
const PeerReviews = lazy(() => import('@/pages/officer/PeerReviews'));
const Scan = lazy(() => import('@/pages/consumer/Scan'));
const ReportForm = lazy(() => import('@/pages/consumer/ReportForm'));
const Alerts = lazy(() => import('@/pages/consumer/Alerts'));
const Trust = lazy(() => import('@/pages/consumer/Trust'));
const BrandOverview = lazy(() => import('@/pages/brand/Overview'));
const PreCertify = lazy(() => import('@/pages/brand/PreCertify'));
const Disputes = lazy(() => import('@/pages/brand/Disputes'));
const DisputePortal = lazy(() => import('@/pages/brand/DisputePortal'));
const Policy = lazy(() => import('@/pages/policy/Policy'));
const Catalogue = lazy(() => import('@/pages/Catalogue'));
const ProductDetail = lazy(() => import('@/pages/ProductDetail'));
const HowItWorks = lazy(() => import('@/pages/HowItWorks'));


function Fallback() {
  return (
    <div className="grid min-h-[40vh] place-items-center">
      <div className="text-sm text-ink-muted">Loading…</div>
    </div>
  );
}

/**
 * Gate a route on authentication and role.
 *
 * `restore` runs once on boot to validate a persisted token; until it settles
 * the guard renders a placeholder rather than bouncing an authenticated user to
 * the login screen and losing their destination.
 */
function Guard({ roles, children }: { roles?: string[]; children: ReactNode }) {
  const { user, status, restore } = useAuth();
  const location = useLocation();

  useEffect(() => {
    if (status === 'unknown') void restore();
  }, [status, restore]);

  if (status === 'unknown') {
    return (
      <div className="grid min-h-dvh place-items-center">
        <div className="text-sm text-ink-muted">Restoring session…</div>
      </div>
    );
  }

  if (status === 'anonymous' || !user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // Admin is the platform-operator role and is deliberately allowed everywhere;
  // excluding it would make an admin console impossible to build.
  if (roles && user.role !== 'admin' && !roles.includes(user.role)) {
    return <Navigate to={homeFor(user.role)} replace />;
  }

  return <Suspense fallback={<Fallback />}>{children}</Suspense>;
}

const OFFICER = ['officer', 'senior_officer'];
const SENIOR = ['senior_officer'];
const CONSUMER = ['consumer'];
const BRAND = ['brand'];

function RootRedirect() {
  const { user, status, restore } = useAuth();
  useEffect(() => {
    if (status === 'unknown') void restore();
  }, [status, restore]);
  if (status === 'unknown') return null;
  return <Navigate to={user ? homeFor(user.role) : '/login'} replace />;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  // The dispute portal is reached by a token in an emailed link, so it is
  // deliberately outside the authenticated shell: due process should not
  // require the brand to hold an account first.
  {
    path: '/brand/dispute/:token',
    element: <Suspense fallback={<Fallback />}><DisputePortal /></Suspense>,
  },

  {
    path: '/',
    element: <Guard><Shell /></Guard>,
    children: [
      { index: true, element: <RootRedirect /> },

      { path: 'officer', element: <Guard roles={OFFICER}><OfficerDashboard /></Guard> },
      { path: 'officer/capture', element: <Guard roles={OFFICER}><Capture /></Guard> },
      { path: 'officer/route', element: <Guard roles={OFFICER}><RoutePlanner /></Guard> },
      { path: 'officer/leads', element: <Guard roles={OFFICER}><Leads /></Guard> },
      { path: 'officer/reviews', element: <Guard roles={SENIOR}><PeerReviews /></Guard> },
      { path: 'officer/sessions/:sessionId', element: <Guard roles={OFFICER}><SessionDetailPage /></Guard> },

      { path: 'scan', element: <Guard roles={CONSUMER}><Scan /></Guard> },
      { path: 'report', element: <Guard roles={CONSUMER}><ReportForm /></Guard> },
      { path: 'alerts', element: <Guard roles={CONSUMER}><Alerts /></Guard> },
      { path: 'trust', element: <Guard roles={CONSUMER}><Trust /></Guard> },

      { path: 'brand', element: <Guard roles={BRAND}><BrandOverview /></Guard> },
      { path: 'brand/certify', element: <Guard roles={BRAND}><PreCertify /></Guard> },
      { path: 'brand/disputes', element: <Guard roles={[...BRAND, ...SENIOR]}><Disputes /></Guard> },

      { path: 'policy', element: <Guard roles={SENIOR}><Policy /></Guard> },

      { path: 'how-it-works', element: <Suspense fallback={<Fallback />}><HowItWorks /></Suspense> },

      { path: 'catalogue', element: <Catalogue /> },
      { path: 'catalogue/:barcode', element: <ProductDetail /> },
    ],
  },

  { path: '*', element: <Navigate to="/" replace /> },
]);
