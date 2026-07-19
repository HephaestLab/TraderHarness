"""Normalize persisted runs into a compact, UI-oriented research dossier."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

# (code, real_trade_date_iso) -> raw bar dicts (real ISO dates, no masking).
# This is deliberately a plain callable protocol (not a class) so the caller
# (e.g. the server, wiring in a MarketDataManager-backed source) controls
# caching/lifetime, and unit tests can inject a trivial fixture without
# touching the on-disk dataset.
EvaluationBarProvider = Callable[[str, str], list[dict[str, Any]]]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _real_date(anchor: str, masked: Any) -> str:
    text = str(masked or "")
    if text.startswith("D") and len(text) > 1:
        try:
            return (date.fromisoformat(anchor) + timedelta(days=int(text[1:]))).isoformat()
        except (ValueError, TypeError):
            return text
    return text


def _daily_curve(curve: list[list[Any]]) -> list[dict[str, Any]]:
    if not curve:
        return []
    peak = _number(curve[0][1])
    previous = peak
    rows = []
    for index, point in enumerate(curve):
        current = _number(point[1])
        peak = max(peak, current)
        daily_return = 0.0 if index == 0 or previous == 0 else (current / previous - 1) * 100
        drawdown = 0.0 if peak == 0 else (current / peak - 1) * 100
        rows.append(
            {
                "date": str(point[0]),
                "equity": round(current, 2),
                "daily_return_pct": round(daily_return, 2),
                "drawdown_pct": round(drawdown, 2),
            }
        )
        previous = current
    return rows


def _extract_bars(
    anchor: str,
    result: dict[str, Any],
    securities: dict[str, dict[str, Any]],
) -> None:
    code = str(result.get("stock_code") or result.get("code") or "")
    raw_bars = result.get("recent_20") or result.get("bars") or result.get("data")
    if not code or not isinstance(raw_bars, list):
        return
    security = securities.setdefault(code, {"code": code, "bars": [], "markers": []})
    merged = {bar["date"]: bar for bar in security["bars"]}
    for raw in raw_bars:
        if not isinstance(raw, dict):
            continue
        masked_date = raw.get("day") or raw.get("date") or raw.get("datetime")
        bar_date = _real_date(anchor, masked_date)
        required = ("open", "high", "low", "close")
        if not bar_date or not all(key in raw for key in required):
            continue
        merged[bar_date] = {
            "date": bar_date,
            "open": _number(raw["open"]),
            "high": _number(raw["high"]),
            "low": _number(raw["low"]),
            "close": _number(raw["close"]),
            "volume": _number(raw.get("volume")),
            "source": "trajectory",
        }
    security["bars"] = [merged[key] for key in sorted(merged)]


def _bars_source(bars: list[dict[str, Any]]) -> str:
    """Summarize whether a trade review's bars were agent-visible or backfilled.

    ``evaluation`` bars come from the preloaded market dataset purely for
    human review; the agent never saw them during the backtest.
    """
    if not bars:
        return "none"
    sources = {bar.get("source", "trajectory") for bar in bars}
    if sources == {"trajectory"}:
        return "trajectory"
    if sources == {"evaluation"}:
        return "evaluation"
    return "mixed"


def _backfill_evaluation_bars(
    code: str,
    trade_date: str,
    security: dict[str, Any],
    evaluation_bars: EvaluationBarProvider,
) -> None:
    """Fill in evaluation-only bars when the agent never called get_kline.

    Trajectory-derived bars (what the agent actually saw) always win on a
    date collision; this only ever fills gaps.
    """
    try:
        raw_bars = evaluation_bars(code, trade_date)
    except Exception:
        return
    if not raw_bars:
        return
    merged = {bar["date"]: bar for bar in security["bars"]}
    for raw in raw_bars:
        if not isinstance(raw, dict):
            continue
        bar_date = str(raw.get("date") or "")
        required = ("open", "high", "low", "close")
        if not bar_date or not all(key in raw for key in required):
            continue
        merged.setdefault(
            bar_date,
            {
                "date": bar_date,
                "open": _number(raw["open"]),
                "high": _number(raw["high"]),
                "low": _number(raw["low"]),
                "close": _number(raw["close"]),
                "volume": _number(raw.get("volume")),
                "source": "evaluation",
            },
        )
    security["bars"] = [merged[key] for key in sorted(merged)]


def _trade_marker(trade: dict[str, Any]) -> dict[str, Any]:
    side = str(trade.get("side") or trade.get("action") or "").lower()
    return {
        "date": str(trade.get("trade_date") or trade.get("date") or ""),
        "side": side,
        "price": _number(trade.get("price")),
        "quantity": int(_number(trade.get("quantity"))),
        "reasoning": str(trade.get("signal_reasoning") or trade.get("reasoning") or ""),
        "window": str(trade.get("window") or ""),
    }


def _trade_bars(bars: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
    """Keep a readable market window around one fill without inventing bars."""
    ordered = sorted(bars, key=lambda bar: bar["date"])
    before = [bar for bar in ordered if bar["date"] <= trade_date][-24:]
    after = [bar for bar in ordered if bar["date"] > trade_date][:6]
    return before + after


def _matches_order(tool: dict[str, Any], marker: dict[str, Any], code: str) -> bool:
    if tool["name"] != "place_order" or tool["date"] != marker["date"]:
        return False
    args = tool["args"]
    tool_code = str(args.get("stock_code") or args.get("code") or "")
    tool_side = str(args.get("action") or args.get("side") or "").lower()
    result = tool.get("result")
    succeeded = not isinstance(result, dict) or result.get("success") is not False
    return succeeded and tool_code == code and tool_side == marker["side"]


def _agent_analysis(
    agent: dict[str, Any],
    evaluation_bars: EvaluationBarProvider | None = None,
) -> dict[str, Any]:
    trajectory = agent.get("trajectory") or {}
    steps = trajectory.get("steps") or []
    trades = agent.get("trades") or []
    decisions: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    days: dict[str, dict[str, Any]] = {}
    securities: dict[str, dict[str, Any]] = {}
    usage: Counter[str] = Counter()

    def day_bucket(value: Any) -> dict[str, Any]:
        key = str(value or "")
        return days.setdefault(
            key,
            {
                "date": key,
                "brief": "",
                "decision_indices": [],
                "tool_indices": [],
                "trades": [],
            },
        )

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_date = str(step.get("date") or "")
        kind = str(step.get("type") or "")
        raw_data = step.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        bucket = day_bucket(step_date)
        if kind in {"morning_brief", "open_window", "close_window"}:
            content = data.get("content")
            if kind == "morning_brief" and isinstance(content, str):
                bucket["brief"] = content
        elif kind == "assistant":
            decision = {
                "date": step_date,
                "step": step.get("step"),
                "phase": str(data.get("phase") or ""),
                "sub_window": data.get("sub_window"),
                "content": str(data.get("content") or ""),
                "reasoning": str(data.get("reasoning_content") or ""),
                "tool_calls": data.get("tool_calls") or [],
            }
            bucket["decision_indices"].append(len(decisions))
            decisions.append(decision)
        elif kind == "tool_call":
            name = str(data.get("name") or data.get("tool") or "")
            result = data.get("result")
            tool = {
                "date": step_date,
                "step": step.get("step"),
                "name": name,
                "args": data.get("args") or {},
                "result": result,
                "phase": str(data.get("phase") or ""),
                "sub_window": data.get("sub_window"),
            }
            bucket["tool_indices"].append(len(tools))
            tools.append(tool)
            usage[name] += 1
            if name in {"get_kline", "get_kline_5min"} and isinstance(result, dict):
                _extract_bars(step_date, result, securities)

    for trade in trades:
        if not isinstance(trade, dict):
            continue
        code = str(trade.get("stock_code") or trade.get("code") or "")
        marker = _trade_marker(trade)
        security = securities.setdefault(code, {"code": code, "bars": [], "markers": []})
        security["markers"].append(marker)
        day_bucket(marker["date"])["trades"].append(trade)

    for security in securities.values():
        security["markers"].sort(key=lambda marker: marker["date"])

    trade_reviews: list[dict[str, Any]] = []
    matched_orders: set[int] = set()
    for trade_index, trade in enumerate(trades):
        if not isinstance(trade, dict):
            continue
        code = str(trade.get("stock_code") or trade.get("code") or "")
        marker = _trade_marker(trade)
        security = securities.get(code, {"bars": []})
        if not security.get("bars") and evaluation_bars is not None and code:
            _backfill_evaluation_bars(code, marker["date"], security, evaluation_bars)
        order_tool_index = next(
            (
                index
                for index, tool in enumerate(tools)
                if index not in matched_orders and _matches_order(tool, marker, code)
            ),
            None,
        )
        if order_tool_index is not None:
            matched_orders.add(order_tool_index)
            order_step = tools[order_tool_index].get("step")
        else:
            order_step = None

        candidates = [
            index
            for index, decision in enumerate(decisions)
            if decision["date"] == marker["date"]
            and (
                order_step is None
                or decision.get("step") is None
                or decision["step"] <= order_step
            )
        ]
        window = marker["window"]
        if window:
            phase = "close_window" if window.startswith("close") else "open_window"
            phase_candidates = [index for index in candidates if decisions[index]["phase"] == phase]
            if phase_candidates:
                candidates = phase_candidates
        decision_indices = candidates[-3:]
        bars = _trade_bars(security.get("bars") or [], marker["date"])
        evidence_parts = (bool(bars), bool(decision_indices), order_tool_index is not None)
        evidence_status = "complete" if all(evidence_parts) else "partial"
        trade_reviews.append(
            {
                "id": f"trade-{trade_index + 1}",
                "code": code,
                "trade": trade,
                "marker": marker,
                "bars": bars,
                "bars_source": _bars_source(bars),
                "decision_indices": decision_indices,
                "order_tool_index": order_tool_index,
                "evidence_status": evidence_status,
            }
        )

    return {
        "metrics": agent.get("metrics") or {},
        "behavior": agent.get("behavior") or {},
        "vs_benchmark": agent.get("vs_benchmark") or {},
        "daily": _daily_curve(agent.get("equity_curve") or []),
        "trades": trades,
        "days": [days[key] for key in sorted(days)],
        "decisions": decisions,
        "reasoning_coverage": {
            "responses": len(decisions),
            "with_reasoning": sum(bool(decision["reasoning"].strip()) for decision in decisions),
        },
        "tools": tools,
        "tool_usage": [
            {"name": name, "count": count}
            for name, count in sorted(usage.items(), key=lambda item: (-item[1], item[0]))
        ],
        "securities": securities,
        "trade_reviews": trade_reviews,
    }


def build_comparison(agents: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Rank multi-agent runs by total return, reusing the same metrics the UI shows.

    Returns ``None`` for single-agent (or empty) documents: there is nothing
    to rank, and the caller should fall back to the single-agent view.
    """
    if len(agents) < 2:
        return None
    rows = []
    for agent_id, agent in agents.items():
        metrics = agent.get("metrics") or {}
        rows.append(
            {
                "agent_id": agent_id,
                "total_return_pct": _number(metrics.get("total_return_pct")),
                "annual_return_pct": _number(metrics.get("annual_return_pct")),
                "sharpe_ratio": _number(metrics.get("sharpe_ratio")),
                "max_drawdown_pct": _number(metrics.get("max_drawdown_pct")),
                "win_rate": _number(metrics.get("win_rate")),
                "final_value": _number(metrics.get("final_value")),
                "trade_count": len(agent.get("trades") or []),
            }
        )
    rows.sort(key=lambda row: _number(row["total_return_pct"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "ranking": [row["agent_id"] for row in rows],
        "agents": rows,
        "best_agent_id": rows[0]["agent_id"],
    }


class MarketDatasetBarSource:
    """Default ``EvaluationBarProvider``, backed by the on-disk daily dataset.

    This is deliberately *not* the in-memory ``MarketData`` the backtest
    engine preloads: by the time a result artifact is analyzed (a later
    HTTP request against a persisted JSON file), the engine process may be
    long gone. Reading a handful of stock codes back out of
    ``daily.parquet`` via ``MarketDataManager.load_daily_for_codes`` is the
    smallest amount of I/O that still avoids a full-market reload.

    Every bar returned here is evaluation-only: the agent never saw it
    during the backtest. Callers must keep it out of the agent-visible
    trajectory and only use it for post-hoc human review.
    """

    def __init__(self, manager: Any = None, before: int = 24, after: int = 6) -> None:
        if manager is None:
            from traderharness.data.market_data_manager import MarketDataManager

            manager = MarketDataManager()
        self._manager = manager
        self._before = before
        self._after = after
        self._frames: dict[str, Any] = {}

    def _frame(self, code: str) -> Any:
        if code not in self._frames:
            try:
                df = self._manager.load_daily_for_codes([code])
            except Exception:
                df = None
            self._frames[code] = df
        return self._frames[code]

    def __call__(self, code: str, trade_date: str) -> list[dict[str, Any]]:
        df = self._frame(code)
        if df is None or df.empty:
            return []
        frame = df.sort_values("date")
        rows = [(str(row["date"]), row) for _, row in frame.iterrows()]
        before = [row for stamp, row in rows if stamp <= trade_date][-self._before :]
        after = [row for stamp, row in rows if stamp > trade_date][: self._after]
        return [
            {
                "date": str(row["date"]),
                "open": _number(row["open"]),
                "high": _number(row["high"]),
                "low": _number(row["low"]),
                "close": _number(row["close"]),
                "volume": _number(row.get("volume")),
            }
            for row in (before + after)
        ]


def build_result_analysis(
    document: dict[str, Any],
    *,
    evaluation_bars: EvaluationBarProvider | None = None,
) -> dict[str, Any]:
    """Build a normalized research dossier without mutating the source artifact.

    ``evaluation_bars`` is an optional evaluation-only K-line backfill source
    (see ``EvaluationBarProvider``). It is never required — without one,
    trade reviews simply keep whatever bars the agent's own tool calls
    produced, exactly as before.
    """
    agents = {
        str(agent_id): _agent_analysis(agent, evaluation_bars)
        for agent_id, agent in (document.get("agent_data") or {}).items()
        if isinstance(agent, dict)
    }
    benchmark = document.get("benchmark") or {}
    return {
        "status": document.get("status", "done"),
        "start_date": document.get("start_date") or document.get("config", {}).get("start_date"),
        "end_date": document.get("end_date") or document.get("config", {}).get("end_date"),
        "trading_days": document.get("trading_days", 0),
        "config": document.get("config") or {},
        "benchmark": {
            "name": benchmark.get("name", "CSI 300"),
            "daily": _daily_curve(benchmark.get("equity_curve") or []),
        },
        "agents": agents,
        "comparison": build_comparison(agents),
    }
