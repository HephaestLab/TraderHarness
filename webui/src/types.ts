export interface RuntimeStatus {
  dataset: Record<string, boolean>;
  providers: { deepseek_configured: boolean; llm_source: "env" | "settings" | "none" };
  security: { scope: string; public_exposure_supported: boolean };
}

export type LLMConfigSource = "env" | "settings" | "none";

export type LLMBaseUrlSource = "env" | "settings" | "default" | "none";

export interface LLMConfig {
  configured: boolean;
  source: LLMConfigSource;
  api_key_masked: string;
  base_url: string;
  base_url_source: LLMBaseUrlSource;
}

export interface LLMTestResult {
  ok: boolean;
  detail: string;
  model: string;
}

export interface AgentCard {
  id: string;
  name: string;
  description: string;
  persona: string;
  strategy_tags: string[];
  risk_profile: "conservative" | "balanced" | "aggressive";
  holding_period: string;
  allowed_tools: string[];
  model: string;
  initial_cash: number;
  max_positions: number;
  max_position_pct: number;
  builtin?: boolean;
}

export interface ToolCatalogEntry {
  name: string;
  label: string;
  description: string;
  category: "market" | "fundamental" | "information" | "portfolio" | "execution" | "workflow" | "quant";
  required: boolean;
}

export interface Metrics {
  total_return_pct?: number;
  annual_return_pct?: number;
  sharpe_ratio?: number;
  sortino_ratio?: number;
  max_drawdown_pct?: number;
  win_rate?: number;
  profit_loss_ratio?: number;
  total_trades?: number;
  final_value?: number;
}

export interface ComparisonAgentSummary {
  agent_id: string;
  total_return_pct: number;
  annual_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  final_value: number;
  trade_count: number;
  rank: number;
}

export interface Comparison {
  ranking: string[];
  agents: ComparisonAgentSummary[];
  best_agent_id: string;
}

export interface ResultSummary {
  file: string;
  status: string;
  start_date?: string;
  end_date?: string;
  trading_days: number;
  metrics?: Metrics;
  agent_count?: number;
  agents?: ComparisonAgentSummary[];
  best_agent_id?: string;
  best_return?: number;
  error?: string;
}

export interface Trade {
  date?: string;
  trade_date?: string;
  stock_code?: string;
  stock_name?: string;
  action?: string;
  side?: string;
  quantity?: number;
  price?: number;
  reasoning?: string;
  signal_reasoning?: string;
  window?: string;
  amount?: number | string;
  commission?: number | string;
  stamp_tax?: number | string;
  total_fee?: number | string;
  total_cost?: number | string;
  net_income?: number | string;
  pnl?: number | string;
}

export interface AgentResult {
  name?: string;
  equity_curve: Array<[string, number]>;
  trades: Trade[];
  conditional_orders?: ConditionalOrder[];
  conditional_order_events?: Array<Record<string, unknown>>;
  memory_events?: Array<Record<string, unknown>>;
  trajectory?: {
    days?: Array<Record<string, unknown>>;
    steps?: Array<Record<string, unknown>>;
  };
  behavior?: Record<string, unknown>;
  vs_benchmark?: Record<string, number>;
  metrics: Metrics;
}

export interface ConditionalOrder {
  order_id: string;
  stock_code: string;
  side: "buy" | "sell";
  quantity: number;
  comparator: "price_lte" | "price_gte";
  trigger_price: number;
  status: "active" | "triggered" | "cancelled" | "expired";
  reasoning?: string;
  created_day_index?: number;
  triggered_day_index?: number;
  triggered_time?: string;
  protective?: boolean;
  revisions?: Array<Record<string, unknown>>;
  attempts?: Array<{ success?: boolean; error?: string | null }>;
}

export interface ResultDocument {
  status: string;
  trading_days: number;
  start_date: string;
  end_date: string;
  config: Record<string, unknown>;
  agent_data: Record<string, AgentResult>;
  benchmark?: {
    name: string;
    equity_curve: Array<[string, number]>;
  };
}

export interface DailyPoint {
  date: string;
  equity: number;
  daily_return_pct: number;
  drawdown_pct: number;
}

export interface DecisionEvidence {
  date: string;
  step?: number;
  phase: string;
  sub_window?: string | null;
  content: string;
  reasoning: string;
  tool_calls: Array<Record<string, unknown>>;
}

export interface ToolEvidence {
  date: string;
  step?: number;
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  phase?: string;
  sub_window?: string | null;
}

export interface SecurityBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source?: "trajectory" | "evaluation";
}

export interface TradeMarker {
  date: string;
  side: string;
  price: number;
  quantity: number;
  reasoning: string;
  window: string;
}

export interface SecurityDossier {
  code: string;
  bars: SecurityBar[];
  markers: TradeMarker[];
}

export interface TradeReviewEvidence {
  id: string;
  code: string;
  trade: Trade;
  marker: TradeMarker;
  bars: SecurityBar[];
  bars_source?: "trajectory" | "evaluation" | "mixed" | "none";
  decision_indices: number[];
  order_tool_index?: number | null;
  decisions?: DecisionEvidence[];
  order_tool?: ToolEvidence | null;
  evidence_status: "complete" | "partial";
}

export interface SecurityPerformance {
  code: string;
  name: string;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  bought_quantity: number;
  sold_quantity: number;
  open_quantity: number;
  buy_amount: number;
  sell_amount: number;
  fees: number;
  realized_pnl: number;
  realized_cost_basis: number;
  realized_return_pct: number | null;
  first_trade_date: string;
  last_trade_date: string;
  status: "open" | "closed";
}

export interface AnalysisDay {
  date: string;
  brief: string;
  decision_indices: number[];
  tool_indices: number[];
  trades: Trade[];
}

export interface AnalyzedAgent {
  metrics: Metrics;
  behavior: Record<string, unknown>;
  vs_benchmark: Record<string, number>;
  daily: DailyPoint[];
  trades: Trade[];
  conditional_orders?: ConditionalOrder[];
  conditional_order_events?: Array<Record<string, unknown>>;
  memory_events?: Array<Record<string, unknown>>;
  days: AnalysisDay[];
  decisions: DecisionEvidence[];
  reasoning_coverage: { responses: number; with_reasoning: number };
  tools: ToolEvidence[];
  tool_usage: Array<{ name: string; count: number }>;
  securities: Record<string, SecurityDossier>;
  trade_reviews: TradeReviewEvidence[];
  security_performance?: SecurityPerformance[];
}

export interface ResultAnalysis {
  detail?: "summary" | "full";
  status: string;
  start_date?: string;
  end_date?: string;
  trading_days: number;
  config: Record<string, unknown>;
  benchmark: { name: string; daily: DailyPoint[] };
  agents: Record<string, AnalyzedAgent>;
  comparison: Comparison | null;
  entity_view?: {
    available: boolean;
    mode: "masked" | "original";
  };
}

export interface RunState {
  id: string;
  status: "running" | "cancelling" | "cancelled" | "done" | "failed";
  created_at: string;
  error?: string | null;
  result_file?: string | null;
  event_count?: number;
  agents?: string[];
}

export interface LiveEvent {
  sequence: number;
  type: string;
  ts: number;
  data: Record<string, unknown>;
}

export interface PaperAccount {
  cash: number;
  equity: number;
  return_pct: number;
}

export interface PaperPosition {
  stock_code: string;
  quantity: number;
  available_quantity?: number;
  avg_cost?: number;
  last_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
}

export interface PaperAgentState {
  agent_id: string;
  agent_name: string;
  model?: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "done" | "failed";
  phase: string;
  account: PaperAccount;
  positions: PaperPosition[];
  trades: Trade[];
  equity_curve: Array<[string, number]>;
  quote_health?: PaperSession["quote_health"];
  last_event?: LiveEvent | null;
  error?: string | null;
}

export interface PaperSession {
  id: string;
  status: "running" | "cancelling" | "cancelled" | "done" | "failed";
  created_at: string;
  agent_id: string;
  agent_name: string;
  agent_ids?: string[];
  agents?: PaperAgentState[];
  session_date: string;
  mode: "live" | "accelerated";
  initial_cash: number;
  clock_state: string;
  phase: string;
  error?: string | null;
  event_count: number;
  account: PaperAccount;
  positions: PaperPosition[];
  trades: Trade[];
  equity_curve: Array<[string, number]>;
  quote_health: {
    source?: string;
    granularity?: string;
    missing_codes?: string[];
    attention_codes?: string[];
    one_minute_bars?: number;
    as_of?: string;
    request_metrics?: Record<string, unknown>;
  };
  broadcasts?: LiveEvent[];
  last_event?: LiveEvent | null;
}

export interface MaskingShowcaseMetrics {
  total_return_pct?: number;
  alpha_pct?: number;
  sharpe_ratio?: number;
  max_drawdown_pct?: number;
  total_trades?: number;
  final_value?: number;
  llm_total_tokens?: number;
  tool_calls?: number;
}

export interface MaskingShowcaseCondition {
  label: string;
  mask_dates: boolean;
  mask_entities: boolean;
  audit: { status: string; finding_count: number };
  metrics: MaskingShowcaseMetrics;
  runs: Array<{
    id: string;
    repetition: number;
    metrics: MaskingShowcaseMetrics;
    llm_total_tokens: number;
  }>;
  equity_curve?: Array<[string, number]>;
}

export interface MaskingShowcase {
  schema_version: number;
  experiment_id: string;
  status: "pending" | "complete";
  generated_at?: string | null;
  title: string;
  summary: string;
  model: string;
  window: { start: string; end: string };
  repetitions: number;
  commit?: string;
  conditions: {
    masked: MaskingShowcaseCondition;
    unmasked: MaskingShowcaseCondition;
  };
  paired_deltas: MaskingShowcaseMetrics;
  limitations: string[];
}
