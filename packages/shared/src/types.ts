/**
 * MetriX API types.
 *
 * Mirrors the Pydantic schemas on the backend. Shared by the web PWA and the
 * Expo Android app so a contract change breaks compilation in both rather than
 * surfacing as a runtime surprise on one of them.
 */

// ---------------------------------------------------------------- identity --
export type Role = 'officer' | 'senior_officer' | 'admin' | 'consumer' | 'brand';

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  role: Role;
  full_name?: string | null;
  phone?: string | null;

  officer_id?: string | null;
  department?: string | null;
  jurisdiction_name?: string | null;
  jurisdiction_geojson?: GeoJSONPolygon | null;

  citizen_trust_score: number;
  verified_reporter: boolean;
  reports_submitted: number;
  reports_confirmed: number;
  trust_badge?: string | null;

  brand_id?: number | null;
  brand_name?: string | null;

  is_active: boolean;
  created_at?: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface GeoJSONPolygon {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
}

// ------------------------------------------------------------- inspections --
export type SessionStatus =
  | 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FLAGGED'
  | 'PEER_REVIEW' | 'APPEALED' | 'RESOLVED' | 'FAILED';

export type ComplianceStatus = 'COMPLIANT' | 'NON_COMPLIANT' | 'WARNING';
export type Severity = 'CRITICAL' | 'MAJOR' | 'MINOR';
export type SurfaceType = 'FRONT' | 'BACK' | 'SIDE' | 'BOTTOM' | 'CAP' | 'DIE_LINE';

export interface SessionSummary {
  id: number;
  session_id: string;
  status: SessionStatus;
  source_type?: string | null;
  overall_score?: number | null;
  compliance_status?: ComplianceStatus | null;
  confidence_score?: number | null;
  estimated_penalty?: number | null;
  brand_name?: string | null;
  product_name?: string | null;
  product_category?: string | null;
  barcode?: string | null;
  barcode_verified: boolean;
  store_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  jurisdiction_status?: string | null;
  is_locked: boolean;
  created_at?: string | null;
  completed_at?: string | null;
  violation_count: number;
}

export interface ExtractedField {
  field_name: string;
  detected_value?: string | null;
  surface_found?: string | null;
  bbox_x?: number | null;
  bbox_y?: number | null;
  bbox_width?: number | null;
  bbox_height?: number | null;
  confidence_vision_llm?: number | null;
  confidence_ocr_verify?: number | null;
  ocr_agreement?: boolean | null;
  ocr_read_value?: string | null;
  crop_url?: string | null;
  font_height_mm?: number | null;
  effective_confidence?: number | null;
}

export interface Violation {
  id?: number;
  rule_id: string;
  rule_name?: string | null;
  field_name?: string | null;
  status: 'FAIL' | 'WARNING' | 'PASS';
  severity?: Severity | null;
  evidence_text?: string | null;
  legal_clause?: string | null;
  confidence?: number | null;
  calculated_value?: string | null;
  expected_value?: string | null;
  discrepancy?: string | null;
  suggested_fix?: string | null;
  penalty_amount?: number | null;
  crop_url?: string | null;
}

export interface SessionImage {
  id: number;
  surface_type: SurfaceType;
  image_path: string;
  url?: string | null;
  sha256_hash: string;
  image_width_px?: number | null;
  image_height_px?: number | null;
  is_curved_surface: boolean;
  curvature_score?: number | null;
  unwarp_method?: string | null;
  px_per_mm?: number | null;
  uploaded_at?: string | null;
}

export interface SessionDetail extends SessionSummary {
  location_address?: string | null;
  package_width_cm?: number | null;
  package_height_cm?: number | null;
  surface_area_cm2?: number | null;
  evidence_seal?: string | null;
  processing_error?: string | null;
  officer_name?: string | null;
  officer_id_code?: string | null;
  images: SessionImage[];
  fields: ExtractedField[];
  violations: Violation[];
}

export interface SessionCreate {
  product_name?: string;
  brand_name?: string;
  barcode?: string;
  category_id?: number;
  product_category?: string;
  package_width_cm?: number;
  package_height_cm?: number;
  latitude?: number;
  longitude?: number;
  store_name?: string;
  location_address?: string;
  captured_at?: string;
}

// --------------------------------------------------- live pipeline (WS) ----
export type PipelineStage =
  | 'CAPTURE' | 'PREPROCESS' | 'EXTRACT' | 'VERIFY' | 'VALIDATE' | 'REVIEW';

export interface PipelineEvent {
  type: 'pipeline';
  session_id: string;
  stage: PipelineStage;
  status: 'started' | 'progress' | 'completed' | 'failed';
  progress: number;
  message: string;
  detail?: Record<string, unknown>;
  timestamp: string;
}

// ---------------------------------------------------------------- consumer --
export interface ScanResponse {
  barcode: string;
  found: boolean;
  message?: string | null;
  product_name?: string | null;
  brand_name?: string | null;
  category?: string | null;
  official_mrp?: number | null;
  net_quantity?: string | null;
  unit_price?: string | null;
  country_of_origin?: string | null;
  compliance_score?: number | null;
  badge_level?: BadgeLevel | null;
  fssai_number?: string | null;
  fssai_verified: boolean;
  past_violations: number;
  total_inspections: number;
  last_inspected?: string | null;
  scanned_mrp?: number | null;
  is_price_gouged: boolean;
  gouging_severity?: 'WATCH' | 'LEAD' | 'PRIORITY' | null;
  overcharge_amount?: number | null;
  overcharge_pct?: number | null;
  anomaly_warning?: string | null;
  crowd_modal_mrp?: number | null;
  crowd_sample_count: number;
}

export type BadgeLevel = 'GOLD' | 'SILVER' | 'BRONZE' | 'STANDARD' | 'FLAGGED';

export type ReportCategory =
  | 'OVERCHARGING' | 'MISSING_MRP' | 'MISSING_EXPIRY'
  | 'EXPIRED_STOCK' | 'MISSING_NET_QTY' | 'OTHER';

export interface CitizenReport {
  id: number;
  report_ref: string;
  store_name: string;
  store_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  violation_category?: ReportCategory | null;
  citizen_remarks?: string | null;
  image_path?: string | null;
  barcode?: string | null;
  claimed_mrp?: number | null;
  charged_price?: number | null;
  status: 'SUBMITTED' | 'VERIFIED' | 'INVESTIGATING' | 'REJECTED';
  priority_score: number;
  officer_notes?: string | null;
  verified_at?: string | null;
  created_at?: string | null;
}

export interface ReportSubmitResponse {
  report_id: string;
  status: string;
  reporter_trust_score: number;
  priority_score: number;
  queue_guidance: string;
}

export interface ConsumerAlert {
  id: number;
  barcode?: string | null;
  alert_type: 'EXPIRED_BATCH_WARNING' | 'PRODUCT_RECALL' | 'PRICE_SURGE' | 'COMPLIANCE_UPDATE';
  severity?: 'INFO' | 'WARNING' | 'CRITICAL' | null;
  title: string;
  message: string;
  action_url?: string | null;
  is_read: boolean;
  created_at?: string | null;
}

export interface TrustProfile {
  trust_score: number;
  badge: string;
  verified_reporter: boolean;
  reports_submitted: number;
  reports_confirmed: number;
  reports_rejected: number;
  accuracy_rate?: number | null;
  rank: number;
  total_reporters: number;
  next_badge?: string | null;
  reports_to_next_badge?: number | null;
  how_it_works: string;
}

// ----------------------------------------------------------------- officer --
export interface RouteStop {
  rank: number;
  store_name: string;
  latitude: number;
  longitude: number;
  address?: string | null;
  risk_score: number;
  risk_reasons: string[];
  components: Record<string, number>;
  historical_violations: number;
  citizen_leads: number;
  price_anomalies: number;
  days_since_inspection?: number | null;
  seasonal_multiplier: number;
  watch_categories: string[];
}

export interface PatrolRoute {
  patrol_route: RouteStop[];
  summary: {
    stops: number;
    total_distance_km: number;
    estimated_duration_minutes: number;
    estimated_duration_readable: string;
    travel_optimisation: string;
    risk_covered_first_3: number;
    distance_if_visited_by_rank_km: number;
    distance_saved_km: number;
    aggregate_risk: number;
  };
  seasonal_context: Array<{
    festival: string;
    date: string;
    days_until: number;
    multiplier: number;
    category?: string;
    note?: string;
  }>;
  coverage_warnings: string[];
  officer?: { name?: string; officer_id?: string; jurisdiction?: string };
  candidates_considered?: number;
  upcoming_festivals?: FestivalWindow[];
}

export interface FestivalWindow {
  festival: string;
  date: string;
  days_until: number;
  watch_from: string;
  elevated_categories: string[];
  peak_multiplier: number;
  note?: string;
}

export interface Lead extends CitizenReport {
  image_url?: string | null;
  reporter_name?: string | null;
  reporter_trust_score?: number | null;
  reporter_verified: boolean;
}

export interface PeerReviewItem {
  id: number;
  session_id: number;
  trigger_reason?: string | null;
  trigger_detail?: string | null;
  triggering_confidence?: number | null;
  review_status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'MODIFIED';
  created_at?: string | null;
  session_ref?: string | null;
  brand_name?: string | null;
  product_name?: string | null;
  store_name?: string | null;
  overall_score?: number | null;
  estimated_penalty?: number | null;
  violation_count: number;
  requested_by_name?: string | null;
}

export interface GougingFinding {
  barcode: string;
  product_name?: string | null;
  brand_name?: string | null;
  store_name: string;
  latitude?: number | null;
  longitude?: number | null;
  modal_mrp: number;
  observed_mrp: number;
  overcharge_amount: number;
  overcharge_pct: number;
  scan_count: number;
  distinct_reporters: number;
  confidence: number;
  severity: 'WATCH' | 'LEAD' | 'PRIORITY';
  reasons: string[];
}

export interface Hotspot {
  centre: { latitude: number; longitude: number };
  radius_km: number;
  stores: string[];
  finding_count: number;
  distinct_products: number;
  total_overcharge_per_unit: number;
  severity: string;
  findings: GougingFinding[];
}

export interface RadarSummary {
  window_days: number;
  scans_analysed: number;
  products_analysed: number;
  findings: number;
  priority_findings: number;
  hotspots: Hotspot[];
  top_findings: GougingFinding[];
}

export interface OfficerDashboard {
  officer: { name?: string; officer_id?: string; jurisdiction?: string; is_senior: boolean };
  inspections: { total: number; this_week: number; flagged: number; penalty_exposure: number };
  queues: { citizen_leads_pending: number; peer_reviews_pending: number };
  upcoming_festivals: FestivalWindow[];
}

// ------------------------------------------------------------------- brand --
export interface PreCertFinding {
  rule: string;
  rule_name: string;
  clause: string;
  severity: Severity;
  status: 'FAIL' | 'WARNING' | 'PASS';
  message: string;
  fix?: string | null;
  measured?: string | null;
  required?: string | null;
}

export interface PreCertResponse {
  pre_cert_id: string;
  is_compliant: boolean;
  compliance_score: number;
  blocking_issues: number;
  digital_badge_token?: string | null;
  audit_report_url?: string | null;
  findings: PreCertFinding[];
  extracted_declarations: Record<string, string | null>;
  measured_font_heights_mm: Record<string, number>;
  warnings: string[];
  message: string;
}

export interface PreCert {
  id: number;
  cert_ref: string;
  product_name: string;
  brand_name?: string | null;
  compliance_score?: number | null;
  is_approved: boolean;
  findings?: PreCertFinding[] | null;
  digital_badge_token?: string | null;
  target_pack_width_cm?: number | null;
  target_pack_height_cm?: number | null;
  sha256_hash?: string | null;
  created_at?: string | null;
  die_line_url?: string | null;
  badge_qr_url?: string | null;
  audit_report_url?: string | null;
}

export interface Dispute {
  id: number;
  dispute_token: string;
  brand_name?: string | null;
  grounds_of_appeal?: string | null;
  counter_evidence_urls?: string[] | null;
  appellate_status: 'UNDER_REVIEW' | 'ACCEPTED' | 'REJECTED';
  appellate_remarks?: string | null;
  hearing_date?: string | null;
  decided_at?: string | null;
  token_expires_at?: string | null;
  created_at?: string | null;
  is_expired: boolean;
  window_days: number;
  session_ref?: string | null;
  product_name?: string | null;
  store_name?: string | null;
  overall_score?: number | null;
  estimated_penalty?: number | null;
  inspected_at?: string | null;
  cited_violations: Array<Violation & { evidence_crop_url?: string | null }>;
  evidence_images: Array<{ surface: string; url?: string | null; sha256: string }>;
}

export interface BrandDashboard {
  brand_name?: string | null;
  field_inspections: {
    total: number;
    avg_compliance_score?: number | null;
    flagged: number;
    penalty_exposure: number;
  };
  pre_certifications: {
    total: number; approved: number; rejected: number; badges_issued: number;
  };
  disputes: { total: number; under_review: number; accepted: number };
  most_common_findings: Array<{ finding: string; count: number }>;
  guidance: string;
}

// ------------------------------------------------------------------ policy --
export interface ClauseStat {
  clause: string;
  rule_id: string;
  rule_name: string;
  violations: number;
  applicable_inspections: number;
  violation_rate: number;
  severity_mix: Record<string, number>;
  penalty_exposure: number;
  trend_pp?: number | null;
  direction?: 'worsening' | 'improving' | 'stable' | null;
}

export interface CategoryTrend {
  slug: string;
  name: string;
  current_avg_score: number;
  previous_avg_score?: number | null;
  change?: number | null;
  direction: 'degrading' | 'improving' | 'stable' | 'insufficient_data';
  current_samples: number;
  previous_samples: number;
  note: string;
}

export interface MacroTrends {
  window: { days: number; current_from: string; previous_from: string; generated_at: string };
  headline: {
    inspections_current: number;
    inspections_previous: number;
    overall_compliance_rate?: number | null;
    avg_compliance_score?: number | null;
    total_penalty_exposure: number;
    cases_escalated: number;
  };
  most_violated_clauses: ClauseStat[];
  degrading_categories: CategoryTrend[];
  improving_categories: CategoryTrend[];
  all_category_trends: CategoryTrend[];
  upcoming_enforcement_windows: FestivalWindow[];
  methodology: string;
}

export interface AgencyEntity {
  brand_name: string;
  legal_entity_name?: string | null;
  identifiers: {
    fssai: { number?: string | null; valid: boolean; expiry?: string | null };
    bis: { number?: string | null; valid: boolean };
    gstin: { number?: string | null; active: boolean };
  };
  legal_metrology: {
    violation_count: number;
    critical_count: number;
    products_flagged: number;
    total_products: number;
    avg_compliance_score?: number | null;
    penalty_exposure: number;
  };
  risk_index: number;
  flags: string[];
  referrals: Array<{
    authority: string;
    authority_name: string;
    priority: 'HIGH' | 'MEDIUM' | 'LOW';
    reason: string;
    recommended_action: string;
    supporting_evidence?: string;
  }>;
}

export interface AgencyGraph {
  generated_at: string;
  entity_count: number;
  high_risk_count: number;
  entities: AgencyEntity[];
  referrals_by_authority: Record<string, {
    authority_name: string; count: number; high_priority: number; items: unknown[];
  }>;
  summary: {
    entities_with_lapsed_fssai: number;
    entities_with_invalid_bis: number;
    entities_with_inactive_gstin: number;
    total_referrals: number;
    aggregate_penalty_exposure: number;
  };
}

export interface GeoCell {
  centre: { latitude: number; longitude: number };
  cell_size_deg: number;
  inspections: number;
  avg_score?: number | null;
  non_compliant: number;
  non_compliance_rate: number;
}

// --------------------------------------------------------------- catalogue --
export interface Category {
  id: number;
  slug: string;
  name: string;
  sector?: string | null;
  icon?: string | null;
  total_inspections: number;
  avg_compliance_score?: number | null;
  badge: BadgeLevel;
  rules_applied: number;
  seasonal_multiplier: number;
  seasonal_reason?: string | null;
  rank?: number;
}

export interface Product {
  id: number;
  product_name: string;
  brand_name: string;
  barcode?: string | null;
  official_mrp?: number | null;
  net_quantity?: string | null;
  unit_price?: string | null;
  country_of_origin?: string | null;
  fssai_number?: string | null;
  avg_score?: number | null;
  badge_level?: BadgeLevel | null;
  total_inspections: number;
  violation_count: number;
  last_inspected_at?: string | null;
}

export interface Paginated<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

// -------------------------------------------------------------- e-commerce --
export interface EcomCrossCheck {
  barcode: string;
  product_name?: string | null;
  physical_pack: {
    mrp?: number | null;
    net_quantity?: string | null;
    country_of_origin?: string | null;
    source: string;
  };
  listings_checked: number;
  compliant_listings: number;
  non_compliant_listings: number;
  is_compliant: boolean;
  findings: Array<{
    platform: string;
    listing_url: string;
    issue: string;
    legal_clause: string;
    severity: Severity;
    listed_value?: string | null;
    physical_pack_value?: string | null;
    detail: string;
  }>;
  ecom_listings: Array<{
    platform: string;
    listing_url: string;
    listing_title?: string | null;
    listed_mrp?: number | null;
    discrepancy: boolean;
    issue_count: number;
    issues: string[];
  }>;
}

export interface PlatformScorecard {
  generated_at: string;
  products_compared: number;
  listings_checked: number;
  non_compliant_listings: number;
  overall_non_compliance_rate: number;
  platforms: Array<{
    platform: string;
    listings_checked: number;
    non_compliant_listings: number;
    non_compliance_rate: number;
    top_issues: Array<{ issue: string; count: number }>;
    assessment: string;
  }>;
  legal_basis: string;
}
