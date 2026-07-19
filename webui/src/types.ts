export interface RuntimeStatus {
  dataset: Record<string, boolean>;
  providers: { deepseek_configured: boolean };
  security: { scope: string; public_exposure_supported: boolean };
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
}

export interface AgentResult {
  name?: string;
  equity_curve: Array<[string, number]>;
  trades: Trade[];
  trajectory?: {
    days?: Array<Record<string, unknown>>;
    steps?: Array<Record<string, unknown>>;
  };
  behavior?: Record<string, unknown>;
  vs_benchmark?: Record<string, number>;
  metrics: Metrics;
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
  evidence_status: "complete" | "partial";
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
  days: AnalysisDay[];
  decisions: DecisionEvidence[];
  reasoning_coverage: { responses: number; with_reasoning: number };
  tools: ToolEvidence[];
  tool_usage: Array<{ name: string; count: number }>;
  securities: Record<string, SecurityDossier>;
  trade_reviews: TradeReviewEvidence[];
}

export interface ResultAnalysis {
  status: string;
  start_date?: string;
  end_date?: string;
  trading_days: number;
  config: Record<string, unknown>;
  benchmark: { name: string; daily: DailyPoint[] };
  agents: Record<string, AnalyzedAgent>;
  comparison: Comparison | null;
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
