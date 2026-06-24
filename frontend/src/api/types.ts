// Shared TypeScript types mirroring backend Pydantic models (Spec D10 §13).
// Kept in manual sync with the backend's API contract.

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginUserOut {
  id: string;
  email: string;
  display_name: string | null;
  preferred_language: string;
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

export interface Holding {
  id: string;
  portfolio_id: string;
  asset_id: string;
  ticker: string;
  name: string;
  asset_class: string;
  quantity: number;
  average_cost: number;
  current_price: number | null;
  current_value: number | null;
  unrealized_gain_loss: number | null;
  unrealized_gain_loss_pct: number | null;
}

export interface Lot {
  id: string;
  holding_id: string;
  quantity: number;
  cost_per_unit: number;
  acquired_at: string;
  notes: string | null;
}

export interface Sale {
  id: string;
  lot_id: string;
  quantity: number;
  price_per_unit: number;
  sold_at: string;
  realized_gain_loss: number;
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
  code: string;
  name_key: string;
  name: string;
  data_type: 'quantitative' | 'qualitative';
  unit: string | null;
  description_key: string | null;
  is_active: boolean;
}

export interface IndicatorSnapshot {
  id: string;
  holding_id: string;
  indicator_code: string;
  value_numeric: number | null;
  value_text: string | null;
  value_text_display: string | null;
  zone: string | null;
  computed_at: string;
  period_label: string | null;
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

export type AnalysisStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface AiReport {
  id: string;
  holding_id: string;
  status: AnalysisStatus;
  pdf_filename: string | null;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface Notification {
  report_id: string;
  holding_id: string;
  ticker: string;
  status: AnalysisStatus;
  completed_at: string | null;
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
