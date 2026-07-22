const STATUS: Record<string, string> = {
  pending: "等待中",
  loading: "加载中",
  running: "运行中",
  cancelling: "正在取消",
  cancelled: "已取消",
  done: "已完成",
  failed: "失败",
  ready: "就绪",
  missing: "缺失",
  connected: "已连接",
  offline: "离线",
  connecting: "连接中",
  live: "实时",
  complete: "完整",
  partial: "部分缺失",
};

const PHASES: Record<string, string> = {
  pre_market: "盘前阶段",
  open_window: "开盘阶段",
  close_window: "尾盘阶段",
  run_start: "回测启动",
  run_end: "回测结束",
  all: "全部阶段",
};

const WINDOWS: Record<string, string> = {
  open_1: "开盘窗口 1",
  open_2: "开盘窗口 2",
  close_1: "尾盘窗口 1",
  close_2: "尾盘窗口 2",
};

const SIDES: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  trade: "交易",
};

const RISKS: Record<string, string> = {
  conservative: "保守",
  balanced: "均衡",
  aggressive: "进取",
};

const LLM_SOURCES: Record<string, string> = {
  env: "环境变量",
  settings: "页面设置",
  default: "内置默认",
  none: "未配置",
};

const TOOLS: Record<string, string> = {
  get_kline: "查询 K 线",
  get_stock_price: "查询最新可见价格",
  get_stock_info: "查询证券资料",
  get_market_overview: "查询市场宽度",
  screen_stocks: "条件选股",
  get_sector_summary: "查询行业概览",
  get_fundamentals: "查询基本面",
  get_business_segments: "查询主营构成",
  get_valuation: "查询估值",
  get_announcements: "查询公告",
  get_news: "查询市场新闻",
  get_portfolio: "查询账户组合",
  get_position: "查询持仓明细",
  place_order: "下单",
  add_watchlist: "加入自选",
  remove_watchlist: "移出自选",
  get_watchlist: "查询自选",
  execute_code: "执行 Python 研究",
  finish_day: "结束交易日",
  run_python: "运行 Python 脚本",
  run_script: "运行研究脚本",
  read_file: "读取文件",
  write_file: "写入文件",
  list_files: "列出文件",
};

const STRATEGY_TAGS: Record<string, string> = {
  custom: "自定义",
  momentum: "动量",
  breakout: "突破",
  "relative-strength": "相对强度",
  quality: "质量",
  value: "价值",
  "low-turnover": "低换手",
  "event-driven": "事件驱动",
  news: "新闻",
  catalyst: "催化剂",
  "sector-rotation": "行业轮动",
  "top-down": "自上而下",
  contrarian: "逆向",
  "mean-reversion": "均值回归",
  "drawdown-control": "回撤控制",
  quant: "量化",
  "cross-sectional": "横截面",
  systematic: "系统化",
  focused: "聚焦",
  "price-action": "价格行为",
};

const AGENT_NAMES: Record<string, string> = {
  "momentum-dragon": "趋势龙",
  "value-sage": "价值贤者",
  "trend-breakout": "趋势突破者",
  "quality-compounder": "质量复利者",
  "event-hawk": "事件猎鹰",
  "sector-rotator": "行业轮动者",
  "contrarian-guardian": "逆向守门人",
  "quant-researcher": "量化研究员",
};

const BEHAVIOR: Record<string, string> = {
  avg_tool_calls_per_day: "日均工具调用",
  max_single_position_pct: "单票最高仓位",
  empty_days_pct: "空仓日占比",
  avg_trade_size_pct: "平均单笔仓位",
  most_traded_stocks: "交易最频繁证券",
  total_buy_count: "买入次数",
  total_sell_count: "卖出次数",
  trading_days: "交易日数",
  active_days: "活跃交易日",
  holding_days: "持仓天数",
  avg_holding_days: "平均持仓天数",
  turnover_rate: "换手率",
  max_positions: "最大持仓数",
  avg_positions: "平均持仓数",
  tool_calls: "工具调用数",
  research_calls: "研究调用数",
};

export function statusLabel(value?: string | null) {
  if (!value) return "未知";
  return STATUS[value.toLowerCase()] ?? value;
}

/** Maps a run/result status to a semantic tone for status dots and chips. */
export function statusTone(value?: string | null): "ok" | "err" | "warn" | "idle" {
  const normalized = (value ?? "").toLowerCase();
  if (["done", "ready", "connected", "live", "complete"].includes(normalized)) return "ok";
  if (["failed", "missing", "offline"].includes(normalized)) return "err";
  if (["running", "pending", "loading", "cancelling", "connecting", "partial"].includes(normalized))
    return "warn";
  return "idle";
}

export function phaseLabel(value?: string | null) {
  if (!value) return "未标注阶段";
  return PHASES[value] ?? value;
}

export function windowLabel(value?: string | null) {
  if (!value) return "未记录窗口";
  return WINDOWS[value] ?? value;
}

export function sideLabel(value?: string | null) {
  if (!value) return "交易";
  return SIDES[value.toLowerCase()] ?? value;
}

export function riskLabel(value?: string | null) {
  if (!value) return "未知";
  return RISKS[value] ?? value;
}

/** Maps an LLM credential/base_url source to a Chinese label. */
export function llmSourceLabel(value?: string | null) {
  if (!value) return "未知";
  return LLM_SOURCES[value] ?? value;
}

export function toolLabel(value?: string | null) {
  if (!value) return "未知工具";
  const label = TOOLS[value];
  return label ? `${label}（${value}）` : value;
}

export function strategyTagLabel(value: string) {
  return STRATEGY_TAGS[value] ?? value;
}

export function agentDisplayName(id: string, fallback: string) {
  return AGENT_NAMES[id] ?? fallback;
}

export function behaviorLabel(value: string) {
  return BEHAVIOR[value] ?? value;
}

export function benchmarkLabel(value: string) {
  const labels: Record<string, string> = {
    "CSI 300": "沪深 300",
    "沪深300": "沪深 300",
  };
  return labels[value] ?? value;
}

export function formatDate(value?: string | null) {
  if (!value) return "待定";
  const match = /^(\d{4})-(\d{2})-(\d{2})(.*)$/.exec(value);
  return match ? `${match[1]}/${match[2]}/${match[3]}${match[4]}` : value;
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions) {
  return value.toLocaleString("zh-CN", options);
}

export function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    run_start: "回测启动",
    loading_data: "加载数据",
    day_start: "交易日开始",
    day_end: "交易日结束",
    phase_change: "阶段切换",
    committee_memo: "委员会备忘",
    llm_response: "模型响应",
    tool_call: "工具调用",
    order_placed: "订单已提交",
    run_end: "回测结束",
    run_error: "运行错误",
  };
  return labels[type] ?? type;
}
