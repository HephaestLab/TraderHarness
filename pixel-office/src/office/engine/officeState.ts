import {
  type Character,
  type Seat,
  type PlacedFurniture,
  type OfficeLayout,
  type PointOfInterest,
  type BacktestEvent,
  type Direction,
  Direction as Dir,
  POIType,
} from "../types";
import { createCharacter, updateCharacter, showBubble } from "./characters";
import { createDefaultOfficeLayout } from "../layout/defaultLayout";

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
}

const CHAIR_TYPES = new Set(["Chair", "Chair-2", "Boss-Chair"]);

const POI_MAP: Record<string, { type: (typeof POIType)[keyof typeof POIType]; facingDir: Direction; standOffset: [number, number] }> = {
  "Coffee-Machine": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 1] },
  "Water-Dispenser": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 1] },
  "Vending-Machine": { type: POIType.COFFEE, facingDir: Dir.UP, standOffset: [0, 1] },
  "Board": { type: POIType.BOARD, facingDir: Dir.UP, standOffset: [0, 1] },
  "Wall-Graph": { type: POIType.BOARD, facingDir: Dir.UP, standOffset: [0, 1] },
  "Big-Round-Table": { type: POIType.MEETING, facingDir: Dir.DOWN, standOffset: [0, -1] },
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
}

export function handleBacktestEvent(
  state: OfficeState,
  event: BacktestEvent
): void {
  switch (event.type) {
    case "run_start":
      for (const ch of state.characters.values()) {
        ch.isActive = true;
        showBubble(ch, "🚀");
      }
      break;
    case "run_end":
      for (const ch of state.characters.values()) {
        ch.isActive = false;
        showBubble(ch, "✅");
      }
      break;
    case "day_start":
      for (const ch of state.characters.values()) {
        ch.isActive = true;
      }
      break;
    case "day_end":
      for (const ch of state.characters.values()) {
        ch.isActive = false;
      }
      break;
    case "phase_change": {
      const phase = event.data.phase as string;
      if (phase === "pre_market") {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
          showBubble(ch, "📰");
        }
      } else if (phase === "open_window") {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
          showBubble(ch, "🔔");
        }
      } else if (phase === "close_window") {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
          showBubble(ch, "🔔");
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
          const side = event.data.side as string;
          showBubble(ch, side === "sell" ? "📉" : "📈");
        } else if (tool === "get_kline" || tool === "get_stock_price") {
          showBubble(ch, "📊");
        } else if (tool === "execute_code") {
          showBubble(ch, "💻");
        } else if (tool === "get_market_overview") {
          showBubble(ch, "🌐");
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
          showBubble(ch, "💭");
        }
      } else {
        for (const ch of state.characters.values()) {
          ch.isActive = true;
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
