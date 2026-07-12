// Shared TypeScript types mirroring backend Pydantic models (Spec D10 §13).
// Kept in manual sync with the backend's API contract.

// ── Market data ───────────────────────────────────────────────────────────────

export interface AssetSearchResult {
  ticker: string;
  name: string;
  asset_type: string;
  quote_currency: string;
  market: string | null;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginUserOut {
  id: string;
  email: string;
  display_name: string | null;
  preferred_language: string;
  auth_provider: string;
  must_change_password: boolean;
  roles: string[];
  permissions: string[];
}

export interface LoginSessionOut {
  portfolios_count: number;
  notifications_poll_interval_seconds: number;
  csrf_token: string;
}

export interface LoginResponse {
  user: LoginUserOut;
  session: LoginSessionOut;
}

export interface UserResponse {
  id: string;
  email: string;
  auth_provider: string;
  display_name: string | null;
  preferred_language: string;
}

// ── Admin (Spec D11 §7.2, §7.3) ─────────────────────────────────────────────

export interface AdminUserSummary {
  id: string;
  email: string;
  auth_provider: string;
  display_name: string | null;
  roles: string[];
  must_change_password: boolean;
  created_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserSummary[];
  total: number;
}

export interface AdminUserDetail extends AdminUserSummary {
  portfolios_count: number;
}

export interface ResetPasswordResponse {
  new_password: string;
}

export interface AdminRoleOut {
  code: string;
  name: string;
  description: string;
  is_default: boolean;
  is_admin_role: boolean;
  permissions: string[];
}

// ── Portfolios ────────────────────────────────────────────────────────────────

export type Currency = 'EUR' | 'USD' | 'GBP' | 'JPY' | 'CHF' | 'CAD' | 'AUD';
export type PortfolioStatus = 'active' | 'archived';

export interface Portfolio {
  id: string;
  name: string;
  base_currency: Currency;
  status: PortfolioStatus;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

// PortfolioHeader summary (Changeset C08). Decimal fields arrive as strings
// (Spec D10 §7.4) to preserve precision — parse with Number() before formatting.
export interface TrendPoint {
  date: string;
  value: string;
  estimated: boolean;
}

export interface PortfolioSummary {
  total_value: string;
  total_invested: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: string;
  trend_30d: TrendPoint[];
  computed_at: string;
  base_currency: string;
}

// ── Holdings ──────────────────────────────────────────────────────────────────

export interface HoldingAsset {
  id: string;
  ticker: string;
  name: string;
  asset_type: string;
  quote_currency: string;
  market: string | null;
  created_at: string;
}

export interface HoldingAggregates {
  quantity_held: number;
  total_invested_base: number;
  avg_purchase_price_quote: number;
  avg_purchase_price_base: number;
}

export interface Holding {
  id: string;
  asset: HoldingAsset;
  aggregates: HoldingAggregates;
  lot_count?: number;
  sale_count?: number;
  lots?: Lot[];
  sales?: Sale[];
  created_at: string;
  updated_at: string;
}

export interface LotConsumption {
  lot_id: string;
  quantity_consumed: number;
}

export interface Lot {
  id: string;
  purchase_date: string;
  quantity: number;
  unit_price: number;
  fx_rate_at_purchase: number | null;
  fx_rate_origin: string;
  notes: string | null;
  quantity_consumed: number;
  created_at: string;
  updated_at: string;
}

export interface Sale {
  id: string;
  sale_date: string;
  quantity: number;
  unit_price: number;
  fx_rate_at_sale: number | null;
  fx_rate_origin: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  lot_consumptions: LotConsumption[];
}

// ── Assets ────────────────────────────────────────────────────────────────────

export interface Asset {
  id: string;
  ticker: string;
  name: string;
  asset_class: string;
  currency: string;
}

// ── Indicators ────────────────────────────────────────────────────────────────

export interface Indicator {
  id: string;
  code: string;
  name_key: string;
  name: string;
  description_key: string;
  scope: string;
  nature: string;
  data_type: string;
  unit: string | null;
  update_strategy: string;
  threshold_config: Record<string, unknown>;
  active: boolean;
}

export interface IndicatorSnapshot {
  id: string;
  as_of_date: string;
  value_numeric: number | null;
  value_text: string | null;
  value_text_display: string | null;
  zone: string | null;
  source: string;
  created_at: string;
  source_report_name: string | null;
}

export interface IndicatorSnapshotHistory {
  indicator: Indicator;
  snapshots: IndicatorSnapshot[];
}

// ── Price Levels ──────────────────────────────────────────────────────────────

export type PriceLevelDirection = 'buy' | 'sell';
export type PriceLevelStatus = 'armed' | 'touched';

export interface PriceLevel {
  id: string;
  holding_id: string;
  direction: PriceLevelDirection;
  target_price: number;
  note: string | null;
  status: PriceLevelStatus;
  created_at: string;
  updated_at: string;
  touched_at: string | null;
  touched_at_close_price: number | null;
  touched_at_close_date: string | null;
  // Null = unread alert. Only meaningful while status is 'touched' (Changeset C12).
  alert_seen_at: string | null;
}

// Alerts Panel (Spec D06 §6): a price level enriched with asset context.
export interface PortfolioAlertItem extends PriceLevel {
  asset_ticker: string;
  asset_name: string;
  asset_quote_currency: string;
  current_price: number | null;
  gap_pct: number | null;
}

// ── Date Alerts (Changeset C17) ────────────────────────────────────────────────

export type DateAlertStatus = 'pending' | 'due';

export interface DateAlert {
  id: string;
  holding_id: string;
  alert_date: string;
  description: string;
  status: DateAlertStatus;
  created_at: string;
  updated_at: string;
  // Null = unread alert. Only meaningful once status is 'due'.
  alert_seen_at: string | null;
}

// Alerts Panel (Changeset C17 §7): a date alert enriched with asset context.
export interface PortfolioDateAlertItem extends DateAlert {
  asset_ticker: string;
  asset_name: string;
}

export interface PortfolioAlerts {
  touched: PortfolioAlertItem[];
  near_crossing: PortfolioAlertItem[];
  // Date alerts whose date has arrived, and ones coming up soon (Changeset C17 §7).
  date_due: PortfolioDateAlertItem[];
  date_upcoming: PortfolioDateAlertItem[];
  // Sum of unread touched price levels (Changeset C12) and unread due date
  // alerts (Changeset C17).
  unread_count: number;
}

// ── AI Analysis ───────────────────────────────────────────────────────────────

export type ReportDateSource = 'ai_extracted' | 'upload_fallback' | 'user_edited' | 'legacy_unknown';
export type ReportPeriodNameSource = 'ai_extracted' | 'user_edited' | 'unset';

export interface AiReportSummary {
  id: string;
  holding_id: string;
  asset_id: string;
  report_date: string | null;
  report_date_source: ReportDateSource;
  report_period_name: string | null;
  report_period_name_source: ReportPeriodNameSource;
  provider: string;
  model_version: string;
  global_signal: 'bullish' | 'neutral' | 'bearish' | null;
  executive_summary: string;
  created_at: string;
  // Whether the current user uploaded this analysis — shared history across
  // every holder of the asset (Changeset C13), edit/delete stay uploader-only.
  is_own: boolean;
}

export interface AiReportDetail extends AiReportSummary {
  uploaded_file_id: string | null;
  analysis_job_id: string;
  extracted_metrics: {
    per: number | null;
    roe: number | null;
    debt_ebitda: number | null;
    revenue_growth_yoy: number | null;
    analyst_sentiment: 'bullish' | 'mixed' | 'bearish' | null;
  };
  confidence_notes: string | null;
}

// ── Upload response ───────────────────────────────────────────────────────────

export interface UploadReportResponse {
  job_id: string;
  status: string;
  message: string;
}

// ── Notifications (mirrors AnalysisJobResponse) ───────────────────────────────

export interface Notification {
  id: string;
  holding_id: string;
  status: string;
  provider: string | null;
  model_version: string | null;
  attempt_count: number;
  last_error: string | null;
  analysis_report_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ── Data providers (Spec D12 §7, Changeset C04 §5) ────────────────────────────

export interface ProviderKeyStatus {
  provider: string;
  display_name: string;
  requires_api_key: boolean;
  configured: boolean;
  masked_key: string | null;
}

export interface DataProvidersResponse {
  market_data_providers: string[];
  market_data_available: string[];
  fx_data_providers: string[];
  fx_data_available: string[];
  api_keys: ProviderKeyStatus[];
}

// ── Cascade failure reports (Spec D12 §6/§7.4, Changeset C04 §6) ─────────────

export interface CascadeFailureEntryOut {
  id: string;
  report_id: string;
  run_completed_at: string;
  asset_id: string;
  ticker: string;
  reason: string;
  providers_tried: string[];
  last_error_by_provider: Record<string, string>;
}

export interface CascadeFailureListResponse {
  items: CascadeFailureEntryOut[];
  total: number;
}

// ── API Error ─────────────────────────────────────────────────────────────────

export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
