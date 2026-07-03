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

export interface PortfolioKpis {
  portfolio_id: string;
  base_currency: string;
  total_invested: number;
  current_value: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  unrealized_gain_loss: number;
  realized_gain_loss: number;
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
}

export interface IndicatorSnapshotHistory {
  indicator: Indicator;
  snapshots: IndicatorSnapshot[];
}

// ── Price Levels ──────────────────────────────────────────────────────────────

export type PriceLevelDirection = 'above' | 'below';
export type AlertStatus = 'pending' | 'triggered' | 'dismissed';

export interface PriceLevel {
  id: string;
  holding_id: string;
  price: number;
  direction: PriceLevelDirection;
  label: string | null;
  per: number[];
  alert_status: AlertStatus;
  triggered_at: string | null;
  created_at: string;
}

// ── AI Analysis ───────────────────────────────────────────────────────────────

export interface AiReportSummary {
  id: string;
  holding_id: string;
  report_date: string | null;
  provider: string;
  model_version: string;
  global_signal: 'bullish' | 'neutral' | 'bearish' | null;
  executive_summary: string;
  created_at: string;
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
