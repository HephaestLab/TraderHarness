import { ArrowLeft, ArrowRight, BrainCircuit, CheckCircle2, Info, TerminalSquare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  formatDate,
  phaseLabel,
  sideLabel,
  statusLabel,
  toolLabel,
  windowLabel,
} from "../locale";
import type { AnalyzedAgent } from "../types";
import { CandlestickChart } from "./CandlestickChart";

function sideOf(review: AnalyzedAgent["trade_reviews"][number]) {
  return review.marker.side || review.trade.side || review.trade.action || "trade";
}

function json(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function TradeReviewWorkbench({ agent }: { agent: AnalyzedAgent }) {
  const [selectedId, setSelectedId] = useState(agent.trade_reviews[0]?.id ?? "");
  useEffect(() => {
    if (!agent.trade_reviews.some((review) => review.id === selectedId)) {
      setSelectedId(agent.trade_reviews[0]?.id ?? "");
    }
  }, [agent.trade_reviews, selectedId]);

  const selectedIndex = Math.max(
    0,
    agent.trade_reviews.findIndex((review) => review.id === selectedId),
  );
  const review = agent.trade_reviews[selectedIndex];
  const decisions = useMemo(
    () => review?.decision_indices.map((index) => agent.decisions[index]).filter(Boolean) ?? [],
    [agent.decisions, review],
  );
  const order = review?.order_tool_index == null ? undefined : agent.tools[review.order_tool_index];

  if (!review) {
    return <div className="panel empty-state">本次回测没有可复盘的已成交订单。</div>;
  }

  const side = sideOf(review).toLowerCase();
  const rationale = review.marker.reasoning || review.trade.signal_reasoning || review.trade.reasoning;
  return (
    <div className="trade-review-workbench">
      <aside className="trade-review-rail" aria-label="已成交订单">
        <div className="rail-heading">
          <span>成交记录</span>
          <strong>{agent.trade_reviews.length}</strong>
        </div>
        <div className="fill-list">
          {agent.trade_reviews.map((item, index) => {
            const itemSide = sideOf(item).toLowerCase();
            return (
              <button
                key={item.id}
                className={item.id === review.id ? "active" : ""}
                onClick={() => setSelectedId(item.id)}
                aria-label={`交易 ${index + 1} ${item.code} ${sideLabel(itemSide)}`}
              >
                <span className={`fill-sequence ${itemSide}`}>{String(index + 1).padStart(2, "0")}</span>
                <span>
                  <strong>{item.code}</strong>
                  <small>{formatDate(item.marker.date)} · {windowLabel(item.marker.window)}</small>
                </span>
                <b className={`side ${itemSide}`}>{sideLabel(itemSide)}</b>
              </button>
            );
          })}
        </div>
      </aside>

      <div className="trade-review-main">
        <header className="trade-review-header">
          <div>
            <span className="eyebrow">第 {selectedIndex + 1} / {agent.trade_reviews.length} 笔交易</span>
            <h2>{review.code} <span className={`side ${side}`}>{sideLabel(side)}</span></h2>
            <p>{formatDate(review.marker.date)} · {windowLabel(review.marker.window)}</p>
          </div>
          <div className="fill-facts">
            <span><small>成交</small><strong>{review.marker.quantity.toLocaleString("zh-CN")} 股 @ {review.marker.price.toFixed(2)}</strong></span>
            <span><small>证据</small><strong className={review.evidence_status === "complete" ? "positive" : "warning"}>{statusLabel(review.evidence_status)}</strong></span>
          </div>
          <nav className="review-stepper" aria-label="交易切换">
            <button
              aria-label="上一笔交易"
              disabled={selectedIndex === 0}
              onClick={() => setSelectedId(agent.trade_reviews[selectedIndex - 1].id)}
            ><ArrowLeft size={16} /></button>
            <button
              aria-label="下一笔交易"
              disabled={selectedIndex === agent.trade_reviews.length - 1}
              onClick={() => setSelectedId(agent.trade_reviews[selectedIndex + 1].id)}
            ><ArrowRight size={16} /></button>
          </nav>
        </header>

        <section className="trade-market-pane">
          <div className="pane-heading">
            <div><span className="eyebrow">价格上下文</span><h3>成交时 K 线</h3></div>
            {review.bars_source === "evaluation" ? (
              <span className="evidence-label evaluation-only">
                <Info size={12} /> 评估视图 · 智能体当时未查看该 K 线，仅供回测后复盘参考
              </span>
            ) : (
              <span className="evidence-label">已记录市场证据 · 仅显示当前成交</span>
            )}
          </div>
          <CandlestickChart bars={review.bars} markers={[review.marker]} />
        </section>

        <section className="trade-reasoning-pane">
          <div className={`reasoning-coverage ${agent.reasoning_coverage.with_reasoning ? "" : "legacy"}`}>
            <Info size={15} />
            <span>
              共 <strong>{agent.reasoning_coverage.responses}</strong> 条模型回复，其中{" "}
              <strong>{agent.reasoning_coverage.with_reasoning}</strong> 条包含独立推理记录。
              {agent.reasoning_coverage.with_reasoning === 0
                ? " 当前工件仅保存了可见回复与下单理由；系统不会伪造缺失的隐藏推理。"
                : ""}
            </span>
          </div>
          <div className="execution-thesis">
            <span className="evidence-icon"><CheckCircle2 size={17} /></span>
            <div>
              <span className="eyebrow">已记录的下单理由</span>
              <p>{rationale || "该成交记录没有保存明确的交易信号理由。"}</p>
            </div>
          </div>

          <div className="reasoning-chain">
            <div className="pane-heading">
              <div><span className="eyebrow">决策链</span><h3>智能体决策依据</h3></div>
              <span className="evidence-label">关联 {decisions.length} 条回复</span>
            </div>
            {decisions.map((decision, index) => (
              <article className="reasoning-step" key={`${decision.date}-${decision.step}-${index}`}>
                <span className="reasoning-index"><BrainCircuit size={15} /> {index + 1}</span>
                <div>
                  <header><code>{phaseLabel(decision.phase)}{decision.sub_window ? ` · ${windowLabel(decision.sub_window)}` : ""}</code><small>步骤 {decision.step ?? "—"}</small></header>
                  {decision.reasoning ? <p className="reasoning-content">{decision.reasoning}</p> : <small className="trace-missing">未记录独立推理内容</small>}
                  {decision.content ? <p>{decision.content}</p> : null}
                </div>
              </article>
            ))}
            {!decisions.length ? <div className="evidence-empty">无法将智能体回复关联到该笔成交。</div> : null}
          </div>

          <div className="order-proof">
            <div className="pane-heading">
              <div><span className="eyebrow">执行证据</span><h3><TerminalSquare size={16} /> {order ? toolLabel(order.name) : "未记录下单工具"}</h3></div>
            </div>
            {order ? (
              <div className="order-proof-grid">
                <div><span>调用参数</span><pre>{json(order.args)}</pre></div>
                <div><span>执行结果</span><pre>{json(order.result)}</pre></div>
              </div>
            ) : <div className="evidence-empty">该旧版工件有成交记录，但没有可匹配的下单（place_order）步骤。</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
