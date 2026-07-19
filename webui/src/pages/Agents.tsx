import { Copy, Pencil, Plus, Save, ShieldCheck, Trash2, Wrench, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNotice, PageHeader } from "../components/Metric";
import {
  agentDisplayName,
  riskLabel,
  strategyTagLabel,
} from "../locale";
import type { AgentCard, ToolCatalogEntry } from "../types";

const EMPTY: AgentCard = {
  id: "",
  name: "",
  description: "",
  persona: "",
  strategy_tags: ["custom"],
  risk_profile: "balanced",
  holding_period: "3-10 trading days",
  allowed_tools: [],
  model: "deepseek-v4-pro",
  initial_cash: 1_000_000,
  max_positions: 4,
  max_position_pct: 25,
};

const MODEL_OPTIONS = [
  { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro", note: "支持 thinking 深度推理，适合复杂决策" },
  { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash", note: "响应更快，无独立推理过程" },
];

const CATEGORY_LABELS: Record<ToolCatalogEntry["category"], string> = {
  market: "市场研究",
  fundamental: "基本面研究",
  information: "新闻与事件",
  portfolio: "账户控制",
  execution: "交易执行",
  workflow: "研究流程",
  quant: "量化工作区",
};

function draftFrom(agent?: AgentCard, tools: ToolCatalogEntry[] = []): AgentCard {
  if (agent) return { ...agent, strategy_tags: [...agent.strategy_tags], allowed_tools: [...agent.allowed_tools], builtin: false };
  const defaults = new Set(["get_kline", "get_stock_price", "get_stock_info", "get_market_overview"]);
  tools.filter((tool) => tool.required).forEach((tool) => defaults.add(tool.name));
  return { ...EMPTY, strategy_tags: [...EMPTY.strategy_tags], allowed_tools: [...defaults] };
}

export function Agents() {
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [tools, setTools] = useState<ToolCatalogEntry[]>([]);
  const [draft, setDraft] = useState<AgentCard>(() => draftFrom());
  const [editing, setEditing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const refresh = () =>
    Promise.all([api.agents(), api.tools()])
      .then(([cards, catalog]) => {
        setAgents(cards);
        setTools(catalog);
      })
      .catch((reason: Error) => setError(reason.message));
  useEffect(() => {
    void refresh();
  }, []);

  const openCreate = (template?: AgentCard) => {
    const next = draftFrom(template, tools);
    if (template) {
      next.id = `${template.id}-custom`;
      next.name = `${agentDisplayName(template.id, template.name)}（自定义）`;
    }
    setDraft(next);
    setEditingId(null);
    setEditing(true);
  };

  const openEdit = (agent: AgentCard) => {
    setDraft(draftFrom(agent, tools));
    setEditingId(agent.id);
    setEditing(true);
  };

  const toggleTool = (tool: ToolCatalogEntry) => {
    if (tool.required) return;
    setDraft((current) => ({
      ...current,
      allowed_tools: current.allowed_tools.includes(tool.name)
        ? current.allowed_tools.filter((name) => name !== tool.name)
        : [...current.allowed_tools, tool.name],
    }));
  };

  const builtinTemplates = agents.filter((agent) => agent.builtin);
  const groupedTools = Object.entries(
    tools.reduce<Record<string, ToolCatalogEntry[]>>((groups, tool) => {
      (groups[tool.category] ??= []).push(tool);
      return groups;
    }, {}),
  );

  return (
    <section>
      <PageHeader
        eyebrow="智能体注册表"
        title="交易研究团队"
        description="在市场时钟启动前固化策略职责、模型、工具权限与账户风控约束。"
        actions={
          <button className="button primary" onClick={() => openCreate()}>
            <Plus size={16} />
            新建智能体
          </button>
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      <div className="agent-grid">
        {agents.map((agent, index) => (
          <article className="agent-card" key={agent.id}>
            <div className={`agent-portrait palette-${index % 4}`}>
              <span>{agentDisplayName(agent.id, agent.name).slice(0, 2).toUpperCase()}</span>
              <small>{riskLabel(agent.risk_profile)}</small>
            </div>
            <div className="agent-card-main">
              <div className="agent-card-kicker"><span className="eyebrow">{agent.builtin ? "内置策略" : "本地策略"}</span><span className="model-chip">{agent.model}</span></div>
              <h2>{agentDisplayName(agent.id, agent.name)}</h2>
              <p>{agent.description || agent.persona}</p>
              <div className="strategy-tags">{agent.strategy_tags.map((tag) => <span key={tag}>{strategyTagLabel(tag)}</span>)}</div>
              <dl>
                <div><dt>风险档位</dt><dd>{riskLabel(agent.risk_profile)}</dd></div>
                <div><dt>持仓周期</dt><dd>{agent.holding_period.replace("trading days", "个交易日")}</dd></div>
                <div><dt>工具数量</dt><dd>{agent.allowed_tools.length}</dd></div>
                <div><dt>单票上限</dt><dd>{agent.max_position_pct}%</dd></div>
              </dl>
            </div>
            <div className="agent-card-actions">
              <button className="icon-button" aria-label={`复制 ${agentDisplayName(agent.id, agent.name)}`} onClick={() => openCreate(agent)}><Copy size={16} /></button>
              {!agent.builtin ? <button className="icon-button" aria-label={`编辑 ${agentDisplayName(agent.id, agent.name)}`} onClick={() => openEdit(agent)}><Pencil size={16} /></button> : null}
              {!agent.builtin ? <button className="icon-button danger-text" aria-label={`删除 ${agentDisplayName(agent.id, agent.name)}`} onClick={async () => { if (window.confirm(`确定删除 ${agentDisplayName(agent.id, agent.name)}？`)) { await api.deleteAgent(agent.id); void refresh(); } }}><Trash2 size={16} /></button> : null}
            </div>
          </article>
        ))}
      </div>
      {editing ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="agent-editor-title">
          <form
            className="agent-editor"
            onSubmit={async (event) => {
              event.preventDefault();
              try {
                if (editingId) await api.updateAgent(draft);
                else await api.createAgent(draft);
                setEditing(false);
                void refresh();
              } catch (reason) {
                setError((reason as Error).message);
              }
            }}
          >
            <header className="agent-editor-header">
              <div><span className="eyebrow">{editingId ? "编辑本地策略" : "智能体构建器"}</span><h2 id="agent-editor-title">定义交易职责</h2><p>选择成熟策略原型，并明确配置模型、风险边界和研究权限。</p></div>
              <button type="button" className="icon-button" aria-label="关闭智能体编辑器" onClick={() => setEditing(false)}><X /></button>
            </header>
            <div className="agent-editor-body">
              <aside className="strategy-template-rail">
                <span className="section-label">从策略风格开始</span>
                {builtinTemplates.map((template) => (
                  <button type="button" key={template.id} onClick={() => openCreate(template)}>
                    <strong>{agentDisplayName(template.id, template.name)}</strong><small>{template.description}</small>
                  </button>
                ))}
              </aside>
              <div className="agent-builder-main">
                <section className="builder-section">
                  <div className="builder-section-heading"><span>01</span><div><h3>身份与模型</h3><p>使用稳定元数据保证实验可复现。</p></div></div>
                  <div className="form-row identity-fields">
                    <label><span>技术 ID</span><input disabled={Boolean(editingId)} required pattern="[a-z0-9-]+" value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} /></label>
                    <label><span>名称</span><input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
                    <label>
                      <span>模型</span>
                      <select aria-label="模型" value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })}>
                        {MODEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        {!MODEL_OPTIONS.some((option) => option.value === draft.model) ? <option value={draft.model}>{draft.model}（旧版本，即将废弃）</option> : null}
                      </select>
                    </label>
                  </div>
                  <small className="model-thinking-note">{MODEL_OPTIONS.find((option) => option.value === draft.model)?.note ?? "该模型为旧版命名，DeepSeek Chat / DeepSeek Reasoner 即将废弃，建议迁移到 DeepSeek V4 系列。"}</small>
                  <label><span>策略摘要</span><textarea rows={2} maxLength={500} required value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
                </section>

                <section className="builder-section">
                  <div className="builder-section-heading"><span>02</span><div><h3>风险边界</h3><p>账户硬约束由回测环境强制执行。</p></div></div>
                  <fieldset className="risk-selector"><legend>风险档位</legend>{(["conservative", "balanced", "aggressive"] as const).map((risk) => <label key={risk}><input type="radio" name="risk-profile" checked={draft.risk_profile === risk} onChange={() => setDraft({ ...draft, risk_profile: risk })} /><span>{riskLabel(risk)}</span></label>)}</fieldset>
                  <div className="form-row">
                    <label><span>持仓周期</span><select value={draft.holding_period} onChange={(event) => setDraft({ ...draft, holding_period: event.target.value })}><option value="1-5 trading days">1-5 个交易日</option><option value="3-10 trading days">3-10 个交易日</option><option value="5-20 trading days">5-20 个交易日</option><option value="20-60 trading days">20-60 个交易日</option></select></label>
                    <label><span>初始资金</span><input type="number" min="10000" value={draft.initial_cash} onChange={(event) => setDraft({ ...draft, initial_cash: Number(event.target.value) })} /></label>
                  </div>
                  <div className="range-grid">
                    <label><span>最大持仓数量 <b>{draft.max_positions}</b></span><input type="range" min="1" max="12" value={draft.max_positions} onChange={(event) => setDraft({ ...draft, max_positions: Number(event.target.value) })} /></label>
                    <label><span>单票最大仓位 <b>{draft.max_position_pct}%</b></span><input type="range" min="5" max="50" step="5" value={draft.max_position_pct} onChange={(event) => setDraft({ ...draft, max_position_pct: Number(event.target.value) })} /></label>
                  </div>
                </section>

                <section className="builder-section">
                  <div className="builder-section-heading"><span>03</span><div><h3>研究工具箱</h3><p>核心控制工具始终启用，其他能力可按策略选择。</p></div></div>
                  <div className="tool-groups">
                    {groupedTools.map(([category, entries]) => (
                      <fieldset key={category}><legend>{CATEGORY_LABELS[category as ToolCatalogEntry["category"]]}</legend>{entries.map((tool) => {
                        const checked = tool.required || draft.allowed_tools.includes(tool.name);
                        return <label className={checked ? "checked" : ""} key={tool.name}><input type="checkbox" checked={checked} disabled={tool.required} onChange={() => toggleTool(tool)} /><span><strong>{tool.label}（{tool.name}）{tool.required ? <ShieldCheck size={12} /> : null}</strong><small>{tool.description}</small></span></label>;
                      })}</fieldset>
                    ))}
                  </div>
                </section>

                <section className="builder-section">
                  <div className="builder-section-heading"><span>04</span><div><h3>决策协议</h3><p>以下高级指令会追加到环境规则之后。</p></div></div>
                  <label><span>角色设定与交易职责</span><textarea required rows={10} value={draft.persona} onChange={(event) => setDraft({ ...draft, persona: event.target.value })} /></label>
                  <div className="decision-contract"><Wrench size={16} /><span>每笔订单必须记录信号、证据、风险、失效条件、仓位依据和退出计划。</span></div>
                </section>
              </div>
            </div>
            <footer className="agent-editor-footer"><span>已启用 {draft.allowed_tools.length} 个工具 · {riskLabel(draft.risk_profile)}风险</span><div><button type="button" className="button secondary" onClick={() => setEditing(false)}>取消</button><button className="button primary"><Save size={16} />{editingId ? "更新智能体" : "保存本地智能体"}</button></div></footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}
