import { Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { agentDisplayName } from "../locale";
import type { AgentCard } from "../types";

interface RunFormProps {
  agents: AgentCard[];
  multiple?: boolean;
  busy?: boolean;
  onSubmit: (payload: {
    agents: string[];
    start_date: string;
    end_date: string;
    initial_cash: number;
    mask_entities: boolean;
    entity_mask_seed: number;
  }) => void;
}

export function RunForm({ agents, multiple = false, busy, onSubmit }: RunFormProps) {
  const [selected, setSelected] = useState<string[]>(agents[0] ? [agents[0].id] : []);
  const [startDate, setStartDate] = useState("2024-03-04");
  const [endDate, setEndDate] = useState("2024-03-29");
  const [seed, setSeed] = useState(42);
  const selectedCards = useMemo(
    () => agents.filter((agent) => selected.includes(agent.id)),
    [agents, selected],
  );
  useEffect(() => {
    if (!selected.length && agents[0]) setSelected([agents[0].id]);
  }, [agents, selected.length]);

  function toggle(id: string) {
    setSelected((current) => {
      if (!multiple) return [id];
      return current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id];
    });
  }

  return (
    <form
      className="run-form"
      onSubmit={(event) => {
        event.preventDefault();
        const cash = selectedCards[0]?.initial_cash ?? 1_000_000;
        onSubmit({
          agents: selected,
          start_date: startDate,
          end_date: endDate,
          initial_cash: cash,
          mask_entities: true,
          entity_mask_seed: seed,
        });
      }}
    >
      <div className="form-row">
        <label>
          <span>开始日期</span>
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label>
          <span>结束日期</span>
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
        <label>
          <span>遮罩种子</span>
          <input
            type="number"
            value={seed}
            onChange={(event) => setSeed(Number(event.target.value))}
          />
        </label>
      </div>
      <fieldset>
        <legend>{multiple ? "选择至少两个智能体" : "执行智能体"}</legend>
        <div className="agent-picker">
          {agents.map((agent) => {
            const active = selected.includes(agent.id);
            const displayName = agentDisplayName(agent.id, agent.name);
            return (
              <button
                key={agent.id}
                type="button"
                className={active ? "agent-choice selected" : "agent-choice"}
                onClick={() => toggle(agent.id)}
              >
                <span className="agent-avatar">{displayName.slice(0, 2).toUpperCase()}</span>
                <span>
                  <strong>{displayName}</strong>
                  <small>{agent.model}</small>
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>
      <div className="form-submit">
        <span>
          本次回测强制启用实体遮罩与日期遮罩。
        </span>
        <button
          className="button primary"
          type="submit"
          disabled={
            busy ||
            selected.length === 0 ||
            (multiple && selected.length < 2) ||
            startDate > endDate
          }
        >
          <Play size={16} fill="currentColor" />
          {busy ? "正在启动…" : multiple ? "运行对比" : "开始回测"}
        </button>
      </div>
    </form>
  );
}
