import {
  type Character,
  type Seat,
  type PlacedFurniture,
  type OfficeLayout,
  type PointOfInterest,
  type BacktestEvent,
  type Direction,
  CharacterState,
  Direction as Dir,
  TileType,
  POIType,
} from "../types";
import {
  createCharacter,
  updateCharacter,
  showBubble,
  enqueueTask,
  enqueueOrderTask,
} from "./characters";
import { createDefaultOfficeLayout } from "../layout/defaultLayout";

export interface RunContextAgent {
  id: string;
  name: string;
  color: string;
}

export interface RunContext {
  status: "idle" | "running" | "done" | "failed" | "cancelled";
  date: string | null; // latest trading day, e.g. "2024-03-14"
  dayIndex: number; // 0-based
  totalDays: number;
  agents: RunContextAgent[];
  equity: Record<string, Array<[date: string, equity: number]>>;
}

export interface OfficeState {
  cols: number;
  rows: number;
  tiles: number[];
  furniture: PlacedFurniture[];
  characters: Map<string, Character>;
  seats: Map<string, Seat>;
  pois: PointOfInterest[];
  zoom: number;
  panX: number;
  panY: number;
  runContext: RunContext | null;
  showSparklines: boolean;
  /** Countdown until the next water-cooler chat between two idle agents. */
  socialTimer: number;
}

export function setRunContext(state: OfficeState, ctx: RunContext): void {
  state.runContext = ctx;
}

const CHAIR_TYPES = new Set(["Chair", "Chair-2", "Boss-Chair"]);

const POI_MAP: Record<string, { type: (typeof POIType)[keyof typeof POIType]; facingDir: Direction; standOffset: [number, number] }> = {
  "Coffee-Machine": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 1] },
  "Water-Dispenser": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 2] },
  "Vending-Machine": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 1] },
  "Board": { type: POIType.BOARD, facingDir: Dir.UP, standOffset: [0, 1] },
  "Wall-Graph": { type: POIType.BOARD, facingDir: Dir.UP, standOffset: [0, 1] },
  "Big-Round-Table": { type: POIType.MEETING, facingDir: Dir.DOWN, standOffset: [0, -1] },
  "Boss-Desk": { type: POIType.RISK, facingDir: Dir.UP, standOffset: [0, 2] },
};

function buildSeats(furniture: PlacedFurniture[]): Map<string, Seat> {
  const seats = new Map<string, Seat>();
  for (const f of furniture) {
    if (CHAIR_TYPES.has(f.type)) {
      seats.set(f.uid, {
        uid: f.uid,
        seatCol: f.col,
        seatRow: f.row,
        facingDir: Dir.UP,
        assigned: false,
        assignedTo: null,
      });
    }
  }
  return seats;
}

function buildPOIs(furniture: PlacedFurniture[]): PointOfInterest[] {
  const pois: PointOfInterest[] = [];
  for (const f of furniture) {
    const mapping = POI_MAP[f.type];
    if (mapping) {
      pois.push({
        uid: f.uid + "_poi",
        type: mapping.type,
        col: f.col + mapping.standOffset[0],
        row: f.row + mapping.standOffset[1],
        facingDir: mapping.facingDir,
      });
    }
  }
  return pois;
}

export function createDefaultState(): OfficeState {
  const layout = createDefaultOfficeLayout();
  const seats = buildSeats(layout.furniture);
  const pois = buildPOIs(layout.furniture);
  return {
    cols: layout.cols,
    rows: layout.rows,
    tiles: [...layout.tiles],
    furniture: [...layout.furniture],
    characters: new Map(),
    seats,
    pois,
    zoom: 3,
    panX: 0,
    panY: 0,
    runContext: null,
    showSparklines: true,
    socialTimer: 12 + Math.random() * 8,
  };
}

export function loadLayout(layout: OfficeLayout): OfficeState {
  const seats = buildSeats(layout.furniture);
  const pois = buildPOIs(layout.furniture);
  return {
    cols: layout.cols,
    rows: layout.rows,
    tiles: [...layout.tiles],
    furniture: [...layout.furniture],
    characters: new Map(),
    seats,
    pois,
    zoom: 3,
    panX: 0,
    panY: 0,
    runContext: null,
    showSparklines: true,
    socialTimer: 12 + Math.random() * 8,
  };
}

export function saveLayout(state: OfficeState): OfficeLayout {
  return {
    version: 1,
    cols: state.cols,
    rows: state.rows,
    tiles: [...state.tiles],
    furniture: [...state.furniture],
  };
}

export function rebuildSeats(state: OfficeState): void {
  const oldAssignments = new Map<string, string>();
  for (const [uid, seat] of state.seats) {
    if (seat.assignedTo) oldAssignments.set(uid, seat.assignedTo);
  }
  state.seats = buildSeats(state.furniture);
  state.pois = buildPOIs(state.furniture);
  for (const [uid, agentId] of oldAssignments) {
    const seat = state.seats.get(uid);
    if (seat) {
      seat.assigned = true;
      seat.assignedTo = agentId;
    }
  }
}

export function addAgent(
  state: OfficeState,
  id: string,
  name: string,
  palette: number
): void {
  const seat = findFreeSeat(state);
  const ch = createCharacter(id, name, palette, seat);
  state.characters.set(id, ch);
  if (seat) {
    seat.assigned = true;
    seat.assignedTo = id;
  }
}

export function removeAgent(state: OfficeState, id: string): void {
  const ch = state.characters.get(id);
  if (ch?.seatId) {
    const seat = state.seats.get(ch.seatId);
    if (seat) {
      seat.assigned = false;
      seat.assignedTo = null;
    }
  }
  state.characters.delete(id);
}

function findFreeSeat(state: OfficeState): Seat | null {
  for (const seat of state.seats.values()) {
    if (!seat.assigned) return seat;
  }
  return null;
}

export function update(state: OfficeState, dt: number): void {
  for (const ch of state.characters.values()) {
    updateCharacter(ch, dt, state.tiles, state.cols, state.rows, state.seats, state.pois);
  }

  // Water-cooler chat: every so often, two idle agents meet in the aisle,
  // gesture at each other for a few seconds, then drift back to work.
  state.socialTimer -= dt;
  if (state.socialTimer <= 0) {
    state.socialTimer = 18 + Math.random() * 12;
    tryStartChat(state);
  }

  // Anti-freeze: the floor must never go fully still (unless everyone is
  // deliberately resting after hours). If nobody is visibly busy, nudge
  // the most-rested agent into motion within about a second.
  let lively = false;
  let allOffDuty = state.characters.size > 0;
  for (const ch of state.characters.values()) {
    if (!ch.offDuty) allOffDuty = false;
    if (
      ch.task ||
      ch.taskQueue.length > 0 ||
      (ch.state !== CharacterState.SIT_IDLE && ch.state !== CharacterState.IDLE)
    ) {
      lively = true;
    }
  }
  if (!lively && !allOffDuty && state.characters.size > 0) {
    let target: Character | null = null;
    for (const ch of state.characters.values()) {
      if (ch.offDuty) continue;
      if (!target || ch.restTimer < target.restTimer) target = ch;
    }
    if (target) {
      target.restTimer = Math.min(target.restTimer, 1.0);
      target.wanderTimer = Math.min(target.wanderTimer, 1.0);
    }
  }
}

function tryStartChat(state: OfficeState): void {
  const candidates = [...state.characters.values()].filter(
    (ch) =>
      !ch.isActive &&
      !ch.task &&
      ch.taskQueue.length === 0 &&
      (ch.state === CharacterState.SIT_IDLE ||
        ch.state === CharacterState.IDLE ||
        ch.state === CharacterState.TYPE)
  );
  if (candidates.length < 2) return;
  const a = candidates[Math.floor(Math.random() * candidates.length)];
  let b = candidates[Math.floor(Math.random() * candidates.length)];
  if (b === a) {
    b = candidates[(candidates.indexOf(a) + 1) % candidates.length];
  }

  // Find an adjacent tile pair in the central aisle.
  const aisleRow = 6;
  const pairs: number[] = [];
  for (let c = 2; c <= state.cols - 4; c++) {
    if (
      state.tiles[aisleRow * state.cols + c] === TileType.FLOOR &&
      state.tiles[aisleRow * state.cols + c + 1] === TileType.FLOOR
    ) {
      pairs.push(c);
    }
  }
  if (pairs.length === 0) return;
  const c0 = pairs[Math.floor(Math.random() * pairs.length)];

  const chatSeconds = 3 + Math.random() * 1.5;
  const setup = (ch: Character, col: number, dir: Direction) => {
    const seat = ch.seatId ? state.seats.get(ch.seatId) : null;
    enqueueTask(ch, {
      kind: "chat",
      standCol: col,
      standRow: aisleRow,
      standDir: dir,
      returnCol: seat ? seat.seatCol : ch.tileCol,
      returnRow: seat ? seat.seatRow : ch.tileRow,
      actDuration: chatSeconds,
      bubbleIcon: "think",
      bubbleDuration: Math.max(1.5, chatSeconds - 0.2),
    });
  };
  setup(a, c0, Dir.RIGHT);
  setup(b, c0 + 1, Dir.LEFT);
}

export function handleBacktestEvent(
  state: OfficeState,
  event: BacktestEvent
): void {
  switch (event.type) {
    case "run_start":
      for (const ch of state.characters.values()) {
        ch.isActive = true;
        ch.offDuty = false;
        showBubble(ch, "rocket");
      }
      break;
    case "run_end":
      // One round of check marks, then everyone sits back down on standby.
      for (const ch of state.characters.values()) {
        ch.isActive = false;
        ch.offDuty = true;
        showBubble(ch, "check");
      }
      break;
    case "day_start":
      for (const ch of state.characters.values()) {
        ch.isActive = true;
        ch.offDuty = false;
      }
      break;
    case "day_end":
      // Characters wrap up and sit at their desks on standby (SIT_IDLE);
      // after a 20-40s breather the normal idle life-rhythm resumes.
      for (const ch of state.characters.values()) {
        ch.isActive = false;
        ch.offDuty = true;
      }
      break;
    case "phase_change": {
      const phase = event.data.phase as string;
      if (phase === "pre_market") {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
          showBubble(ch, "globe");
        }
      } else if (phase === "open_window" || phase === "close_window") {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
          showBubble(ch, "bell");
        }
      }
      break;
    }
    case "tool_call": {
      const agentId = (event.data.agent_id as string) || "agent_0";
      const ch = state.characters.get(agentId);
      if (ch) {
        ch.currentTool = (event.data.tool as string) || null;
        ch.isActive = true;
        const tool = ch.currentTool;
        if (tool === "place_order") {
          const side = String(event.data.side || "").toLowerCase();
          showBubble(ch, side === "sell" ? "sell" : "buy", 3.5);
        } else if (tool === "get_kline" || tool === "get_stock_price") {
          showBubble(ch, "board");
        } else if (tool === "execute_code") {
          showBubble(ch, "code");
        } else if (tool === "get_market_overview") {
          showBubble(ch, "globe");
        } else if (tool) {
          showBubble(ch, "think");
        }
      }
      break;
    }
    case "llm_response": {
      const agentId = (event.data.agent_id as string) || "";
      if (agentId) {
        const ch = state.characters.get(agentId);
        if (ch) {
          ch.isActive = true;
          showBubble(ch, "think");
        }
      } else {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
        }
      }
      break;
    }
    case "order_placed": {
      const agentId = (event.data.agent_id as string) || "";
      const side = String(event.data.side || event.data.action || "").toLowerCase();
      const icon = side === "sell" ? "sell" : "buy";
      const targets = agentId
        ? [state.characters.get(agentId)].filter((character): character is Character => Boolean(character))
        : [...state.characters.values()];
      const riskPOI = state.pois.find((poi) => poi.type === POIType.RISK) ?? null;
      for (const ch of targets) {
        ch.isActive = true;
        if (riskPOI) {
          // Walk the order over to the risk/execution desk, act there, then
          // head back to the desk and keep typing.
          const seat = ch.seatId ? state.seats.get(ch.seatId) : null;
          const returnCol = seat ? seat.seatCol : ch.tileCol;
          const returnRow = seat ? seat.seatRow : ch.tileRow;
          enqueueOrderTask(
            ch,
            riskPOI.col,
            riskPOI.row,
            riskPOI.facingDir,
            returnCol,
            returnRow,
            icon
          );
        } else {
          // Custom layout without a risk desk: react in place.
          showBubble(ch, icon, 3.5);
        }
      }
      break;
    }
  }
}

// Undo/Redo system
export interface UndoEntry {
  tiles: number[];
  furniture: PlacedFurniture[];
}

export class UndoStack {
  private stack: UndoEntry[] = [];
  private pointer = -1;
  private maxSize = 50;

  push(state: OfficeState): void {
    const entry: UndoEntry = {
      tiles: [...state.tiles],
      furniture: state.furniture.map((f) => ({ ...f })),
    };
    this.stack = this.stack.slice(0, this.pointer + 1);
    this.stack.push(entry);
    if (this.stack.length > this.maxSize) {
      this.stack.shift();
    }
    this.pointer = this.stack.length - 1;
  }

  undo(state: OfficeState): boolean {
    if (this.pointer <= 0) return false;
    this.pointer--;
    this.apply(state);
    return true;
  }

  redo(state: OfficeState): boolean {
    if (this.pointer >= this.stack.length - 1) return false;
    this.pointer++;
    this.apply(state);
    return true;
  }

  private apply(state: OfficeState): void {
    const entry = this.stack[this.pointer];
    state.tiles = [...entry.tiles];
    state.furniture = entry.furniture.map((f) => ({ ...f }));
    rebuildSeats(state);
  }

  get canUndo(): boolean {
    return this.pointer > 0;
  }

  get canRedo(): boolean {
    return this.pointer < this.stack.length - 1;
  }
}
