/**
 * MetriX API client.
 *
 * One typed client shared by the web PWA and the Expo Android app. It owns
 * token refresh so no caller has to think about it: an officer's shift is
 * longer than an access token's life, and a session that silently expires
 * mid-inspection would lose captured evidence.
 */
import type {
  AgencyGraph, BrandDashboard, Category, CitizenReport, ConsumerAlert,
  Dispute, EcomCrossCheck, GeoCell, Lead, MacroTrends, OfficerDashboard,
  Paginated, PatrolRoute, PeerReviewItem, PlatformScorecard, PreCert,
  PreCertResponse, Product, RadarSummary, ReportSubmitResponse, ScanResponse,
  SessionCreate, SessionDetail, SessionSummary, TokenResponse, TrustProfile,
  UserProfile,
} from './types';

export interface Tokens {
  access: string;
  refresh: string;
}

export interface ClientOptions {
  baseUrl: string;
  /** Called whenever tokens change, so the host can persist them. */
  onTokens?: (tokens: Tokens | null) => void;
  /** Called when refresh fails and the user must sign in again. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Distinguishes "the network is gone" from "the server said no". */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

export class MetrixClient {
  private baseUrl: string;
  private tokens: Tokens | null = null;
  private onTokens?: (t: Tokens | null) => void;
  private onUnauthorized?: () => void;
  private doFetch: typeof fetch;
  /** In-flight refresh, so concurrent 401s trigger exactly one refresh. */
  private refreshing: Promise<boolean> | null = null;

  constructor(opts: ClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, '');
    this.onTokens = opts.onTokens;
    this.onUnauthorized = opts.onUnauthorized;
    this.doFetch = opts.fetchImpl ?? ((...a) => fetch(...a));
  }

  setTokens(tokens: Tokens | null): void {
    this.tokens = tokens;
    this.onTokens?.(tokens);
  }

  getTokens(): Tokens | null {
    return this.tokens;
  }

  get isAuthenticated(): boolean {
    return Boolean(this.tokens?.access);
  }

  /** Absolute URL for a storage path the API returned. */
  resolveUrl(path?: string | null): string | undefined {
    if (!path) return undefined;
    if (/^https?:\/\//.test(path)) return path;
    return `${this.baseUrl}${path.startsWith('/') ? '' : '/'}${path}`;
  }

  websocketUrl(path: string): string {
    const base = this.baseUrl.replace(/^http/, 'ws');
    const token = this.tokens?.access ?? '';
    const sep = path.includes('?') ? '&' : '?';
    return `${base}${path}${sep}token=${encodeURIComponent(token)}`;
  }

  // ------------------------------------------------------------ transport --
  private async request<T>(
    path: string,
    init: RequestInit = {},
    retry = true,
  ): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.tokens?.access) {
      headers.set('Authorization', `Bearer ${this.tokens.access}`);
    }
    // Let the browser set the multipart boundary itself.
    if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    let response: Response;
    try {
      response = await this.doFetch(`${this.baseUrl}${path}`, { ...init, headers });
    } catch (err) {
      // Status 0 means the request never reached the server. The offline queue
      // depends on telling this apart from a server rejection -- a 4xx must not
      // be retried forever, but a lost connection must.
      //
      // The underlying message is carried through rather than swallowed. Not
      // every fetch rejection is a lost connection: a malformed multipart body
      // or an unreadable file URI lands here too, and reporting those as "no
      // signal" sends the user to check their wifi for a bug in the request.
      const cause = err instanceof Error ? err.message : String(err ?? '');
      throw new ApiError(
        0,
        cause ? `Network request failed: ${cause}` : 'Network unavailable',
        err,
      );
    }

    if (response.status === 401 && retry && this.tokens?.refresh) {
      const ok = await this.refreshTokens();
      if (ok) return this.request<T>(path, init, false);
      this.setTokens(null);
      this.onUnauthorized?.();
    }

    if (!response.ok) {
      let detail: unknown;
      let message = `${response.status} ${response.statusText}`;
      try {
        detail = await response.json();
        const d = (detail as { detail?: unknown }).detail;
        if (typeof d === 'string') message = d;
        else if (Array.isArray(d) && d.length) {
          message = d.map((e: { msg?: string }) => e.msg ?? '').filter(Boolean).join('; ') || message;
        }
      } catch {
        /* body was not JSON */
      }
      throw new ApiError(response.status, message, detail);
    }

    if (response.status === 204) return undefined as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  private async refreshTokens(): Promise<boolean> {
    // Collapse concurrent refreshes: several requests failing at once must not
    // each burn a refresh token.
    if (this.refreshing) return this.refreshing;

    this.refreshing = (async () => {
      try {
        const res = await this.doFetch(`${this.baseUrl}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.tokens?.refresh }),
        });
        if (!res.ok) return false;
        const data: TokenResponse = await res.json();
        this.setTokens({ access: data.access_token, refresh: data.refresh_token });
        return true;
      } catch {
        return false;
      } finally {
        this.refreshing = null;
      }
    })();

    return this.refreshing;
  }

  private qs(params: Record<string, unknown>): string {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
    }
    const s = sp.toString();
    return s ? `?${s}` : '';
  }

  // ----------------------------------------------------------------- auth --
  async login(username: string, password: string): Promise<TokenResponse> {
    const data = await this.request<TokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    this.setTokens({ access: data.access_token, refresh: data.refresh_token });
    return data;
  }

  async register(payload: {
    username: string; email: string; password: string;
    full_name?: string; phone?: string; role?: 'consumer' | 'brand'; brand_name?: string;
  }): Promise<TokenResponse> {
    const data = await this.request<TokenResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    this.setTokens({ access: data.access_token, refresh: data.refresh_token });
    return data;
  }

  me(): Promise<UserProfile> {
    return this.request<UserProfile>('/api/auth/me');
  }

  logout(): void {
    this.setTokens(null);
  }

  // ---------------------------------------------------------- inspections --
  createSession(payload: SessionCreate): Promise<SessionSummary> {
    return this.request<SessionSummary>('/api/inspections/session', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  uploadSurface(
    sessionId: string,
    file: Blob,
    surfaceType: string,
    filename = 'surface.jpg',
  ): Promise<{
    image_id: number; surface_type: string; sha256_hash: string;
    perceptual_hash?: string | null; width_px?: number | null;
    height_px?: number | null; size_bytes?: number | null;
    url?: string | null; duplicate_warning?: string | null;
  }> {
    const form = new FormData();
    form.append('file', file, filename);
    form.append('surface_type', surfaceType);
    return this.request(`/api/inspections/${sessionId}/images`, {
      method: 'POST',
      body: form,
    });
  }

  processSession(sessionId: string): Promise<{
    session_id: string; task_id: string; status: string;
    message: string; websocket_url: string;
  }> {
    return this.request(`/api/inspections/${sessionId}/process`, { method: 'POST' });
  }

  getSession(sessionId: string): Promise<SessionDetail> {
    return this.request<SessionDetail>(`/api/inspections/${sessionId}`);
  }

  listSessions(params: {
    page?: number; page_size?: number; status?: string; mine?: boolean; search?: string;
  } = {}): Promise<{ items: SessionSummary[]; total: number; page: number; page_size: number }> {
    return this.request(`/api/inspections${this.qs(params)}`);
  }

  escalate(sessionId: string, reason?: string): Promise<{ detail: string }> {
    return this.request(`/api/inspections/${sessionId}/escalate`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  decidePeerReview(
    sessionId: string,
    decision: 'APPROVED' | 'REJECTED' | 'MODIFIED',
    remarks: string,
  ): Promise<{ detail: string }> {
    return this.request(`/api/inspections/${sessionId}/peer-review`, {
      method: 'POST',
      body: JSON.stringify({ decision, remarks }),
    });
  }

  verifyEvidenceSeal(sessionId: string): Promise<{
    session_id: string; seal?: string | null; recomputed: string;
    intact: boolean; image_count: number; image_hashes: string[]; verdict: string;
  }> {
    return this.request(`/api/inspections/${sessionId}/evidence-seal`);
  }

  // ------------------------------------------------------------- consumer --
  scan(params: {
    barcode: string; mrp?: number; lat?: number; lng?: number; store_name?: string;
  }): Promise<ScanResponse> {
    return this.request<ScanResponse>(`/api/consumer/scan${this.qs(params)}`);
  }

  priceHistory(barcode: string, days = 30): Promise<{
    barcode: string; product_name?: string | null; official_mrp?: number | null;
    window_days: number;
    statistics: {
      modal_mrp?: number | null; median_mrp?: number | null; sample_count: number;
      usable_count: number; outliers_rejected: number; price_spread: number;
      confidence: number; is_stable: boolean; note: string;
    };
    market_revision_detected?: string | null;
    gouging_findings: unknown[];
    series: Array<{ date: string; mrp: number; store?: string | null; anomalous: boolean }>;
  }> {
    return this.request(`/api/consumer/price-history/${barcode}${this.qs({ days })}`);
  }

  submitReport(form: FormData): Promise<ReportSubmitResponse> {
    return this.request<ReportSubmitResponse>('/api/consumer/report', {
      method: 'POST',
      body: form,
    });
  }

  myReports(): Promise<CitizenReport[]> {
    return this.request<CitizenReport[]>('/api/consumer/reports');
  }

  alerts(unreadOnly = false): Promise<ConsumerAlert[]> {
    return this.request<ConsumerAlert[]>(
      `/api/consumer/alerts${this.qs({ unread_only: unreadOnly })}`,
    );
  }

  markAlertRead(id: number): Promise<{ detail: string }> {
    return this.request(`/api/consumer/alerts/${id}/read`, { method: 'POST' });
  }

  trustProfile(): Promise<TrustProfile> {
    return this.request<TrustProfile>('/api/consumer/trust');
  }

  leaderboard(): Promise<{
    leaderboard: Array<{
      rank: number; display_name: string; trust_score: number;
      badge?: string | null; reports_confirmed: number; verified: boolean;
    }>;
    note: string;
  }> {
    return this.request('/api/consumer/leaderboard');
  }

  // -------------------------------------------------------------- officer --
  routeSuggestions(params: {
    lat: number; lng: number; radius_km?: number; max_stops?: number;
  }): Promise<PatrolRoute> {
    return this.request<PatrolRoute>(`/api/officer/route-suggestions${this.qs(params)}`);
  }

  leads(status?: string): Promise<Lead[]> {
    return this.request<Lead[]>(`/api/officer/leads${this.qs({ status })}`);
  }

  decideLead(
    reportRef: string,
    verdict: 'VERIFIED' | 'REJECTED' | 'INVESTIGATING',
    notes: string,
  ): Promise<{ detail: string }> {
    return this.request(`/api/officer/leads/${reportRef}/verdict`, {
      method: 'POST',
      body: JSON.stringify({ verdict, notes }),
    });
  }

  pendingPeerReviews(): Promise<PeerReviewItem[]> {
    return this.request<PeerReviewItem[]>('/api/officer/peer-reviews/pending');
  }

  radar(params: { lat?: number; lng?: number; radius_km?: number } = {}): Promise<RadarSummary> {
    return this.request<RadarSummary>(`/api/officer/radar${this.qs(params)}`);
  }

  officerDashboard(): Promise<OfficerDashboard> {
    return this.request<OfficerDashboard>('/api/officer/dashboard');
  }

  // ---------------------------------------------------------------- brand --
  preCertify(form: FormData): Promise<PreCertResponse> {
    return this.request<PreCertResponse>('/api/brand/pre-certify', {
      method: 'POST',
      body: form,
    });
  }

  myCertifications(): Promise<PreCert[]> {
    return this.request<PreCert[]>('/api/brand/pre-certifications');
  }

  verifyBadge(token: string): Promise<Record<string, unknown>> {
    return this.request(`/api/brand/verify-badge/${token}`);
  }

  openDispute(sessionId: string): Promise<{
    dispute_token: string; portal_url?: string; expires_at?: string | null;
    window_days?: number; already_issued: boolean;
  }> {
    return this.request(`/api/brand/disputes/open/${sessionId}`, { method: 'POST' });
  }

  viewDispute(token: string): Promise<Dispute> {
    return this.request<Dispute>(`/api/brand/disputes/${token}`);
  }

  submitDispute(
    token: string,
    grounds: string,
    documents?: string[],
  ): Promise<{ detail: string }> {
    return this.request(`/api/brand/disputes/${token}`, {
      method: 'POST',
      body: JSON.stringify({ grounds_of_appeal: grounds, evidence_documents: documents }),
    });
  }

  appellateQueue(): Promise<Dispute[]> {
    return this.request<Dispute[]>('/api/brand/disputes');
  }

  decideDispute(
    token: string,
    decision: 'ACCEPTED' | 'REJECTED',
    remarks: string,
  ): Promise<{ detail: string }> {
    return this.request(`/api/brand/disputes/${token}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, remarks }),
    });
  }

  brandDashboard(): Promise<BrandDashboard> {
    return this.request<BrandDashboard>('/api/brand/dashboard');
  }

  // --------------------------------------------------------------- policy --
  macroTrends(days = 90): Promise<MacroTrends> {
    return this.request<MacroTrends>(`/api/policy/macro-trends${this.qs({ days })}`);
  }

  agencyGraph(brandName?: string): Promise<AgencyGraph> {
    return this.request<AgencyGraph>(`/api/policy/agency-graph${this.qs({ brand_name: brandName })}`);
  }

  geographic(days = 180, gridDeg = 0.05): Promise<{
    window_days: number; grid_size_deg: number; cells: GeoCell[];
    inspections_mapped: number; privacy_note: string;
  }> {
    return this.request(`/api/policy/geographic${this.qs({ days, grid_deg: gridDeg })}`);
  }

  amendmentImpact(params: {
    effective_date: string; amendment_name?: string;
    window_days?: number; category_slug?: string;
  }): Promise<Record<string, unknown>> {
    return this.request(`/api/policy/amendment-impact${this.qs(params)}`);
  }

  ruleCatalogue(): Promise<{ rules: unknown[]; count: number; note: string }> {
    return this.request('/api/policy/rules');
  }

  // ----------------------------------------------------------- e-commerce --
  ecomCrossCheck(barcode: string): Promise<EcomCrossCheck> {
    return this.request<EcomCrossCheck>(`/api/ecom/cross-check${this.qs({ barcode })}`);
  }

  platformScorecard(): Promise<PlatformScorecard> {
    return this.request<PlatformScorecard>('/api/ecom/platform-scorecard');
  }

  // ------------------------------------------------------------ catalogue --
  categories(sector?: string): Promise<{
    categories: Category[];
    sectors: Array<{ sector: string; categories: number; avg_compliance_score?: number | null }>;
  }> {
    return this.request(`/api/categories${this.qs({ sector })}`);
  }

  category(slug: string): Promise<Record<string, unknown>> {
    return this.request(`/api/categories/${slug}`);
  }

  products(params: {
    search?: string; brand?: string; category_id?: number; badge?: string;
    flagged_only?: boolean; page?: number; page_size?: number;
  } = {}): Promise<Paginated<Product>> {
    return this.request<Paginated<Product>>(`/api/products${this.qs(params)}`);
  }

  product(barcode: string): Promise<Record<string, unknown>> {
    return this.request(`/api/products/${barcode}`);
  }

  // --------------------------------------------------------------- system --
  health(): Promise<Record<string, unknown>> {
    return this.request('/health');
  }

  capabilities(): Promise<Record<string, unknown>> {
    return this.request('/health/capabilities');
  }
}
