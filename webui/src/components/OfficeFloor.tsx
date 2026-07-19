import { useEffect, useRef, useState } from "react";
import { OfficeCanvas } from "@office/components/OfficeCanvas";
import * as officeEngine from "@office/engine/officeState";
import {
  addAgent,
  createDefaultState,
  handleBacktestEvent,
  removeAgent,
  type OfficeState,
} from "@office/engine/officeState";
import { eventTypeLabel } from "../locale";
import type { RunContext } from "../liveDerived";
import type { LiveEvent } from "../types";

const FURNITURE = [
  "Desk-2",
  "Chair-2",
  "Small-Plant",
  "Big-Round-Table",
  "Boss-Desk",
  "Boss-Chair",
  "Big-Office-Printer",
  "Water-Dispenser",
  "Filing-Cabinet-Small",
  "Bin",
  "Wall-Graph",
  "Board",
  "Coffee-Machine",
  "Big-Filing-Cabinet",
  "Filing-Cabinet-Tall",
  "Bookshelf",
  "Small-Sofa",
  "Small-Table",
];

export function OfficeFloor({
  agents,
  latestEvent,
  runContext,
  className,
}: {
  agents: Array<{ id: string; name: string }>;
  latestEvent?: LiveEvent;
  /** 实时运行上下文；pixel-office 用它驱动工位名牌与净值看板。 */
  runContext?: RunContext;
  className?: string;
}) {
  const [state] = useState<OfficeState>(() => createDefaultState());
  const [images, setImages] = useState<Map<string, HTMLImageElement>>(new Map());
  const [characterSheet, setCharacterSheet] = useState<HTMLImageElement | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const loaded = new Map<string, HTMLImageElement>();
    let settled = 0;
    FURNITURE.forEach((name) => {
      const image = new Image();
      image.src = `/assets/furniture/${name}.png`;
      const done = () => {
        settled += 1;
        if (image.complete && image.naturalWidth) loaded.set(name, image);
        if (settled === FURNITURE.length) setImages(new Map(loaded));
      };
      image.onload = done;
      image.onerror = done;
    });
  }, []);

  useEffect(() => {
    const image = new Image();
    image.onload = () => setCharacterSheet(image);
    image.src = "/assets/characters/characters.png";
    return () => {
      image.onload = null;
    };
  }, []);

  useEffect(() => {
    const expected = new Set(agents.map((agent) => agent.id));
    for (const id of state.characters.keys()) {
      if (!expected.has(id)) removeAgent(state, id);
    }
    agents.forEach((agent, index) => {
      if (!state.characters.has(agent.id)) {
        addAgent(state, agent.id, agent.name, index);
      }
    });
  }, [agents, state]);

  useEffect(() => {
    if (latestEvent) handleBacktestEvent(stateRef.current, latestEvent);
  }, [latestEvent]);

  useEffect(() => {
    if (!runContext) return;
    // pixel-office 侧的 setRunContext 契约由并行任务实现；落地前做防御性检查，
    // 避免在旧版引擎上直接崩溃。
    const setter = (
      officeEngine as {
        setRunContext?: (state: OfficeState, context: RunContext) => void;
      }
    ).setRunContext;
    setter?.(state, runContext);
  }, [runContext, state]);

  return (
    <div className={`office-floor${className ? ` ${className}` : ""}`} aria-label="智能体实时运行大厅">
      <OfficeCanvas
        state={state}
        furnitureImages={images}
        characterSheet={characterSheet}
        showGrid={false}
      />
      <div className="office-caption">
        <span className="pulse-dot" />
        量化研究大厅 · 事件联动仿真
      </div>
      <div className="office-scene-title"><span>TRADERHARNESS 实验室</span><strong>市场仿真 · {latestEvent?.type ? eventTypeLabel(latestEvent.type) : "待命"}</strong></div>
      <div className="office-zone-legend"><span><i className="research" />研究工位</span><span><i className="risk" />风控执行台</span><span><i className="war" />策略会议室</span></div>
    </div>
  );
}
