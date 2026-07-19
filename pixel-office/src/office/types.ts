export const TILE_SIZE = 16;
export const DEFAULT_COLS = 12;
export const DEFAULT_ROWS = 10;
export const MAX_COLS = 32;
export const MAX_ROWS = 32;

export const TileType = {
  WALL: 0,
  FLOOR: 1,
  BLOCKED: 2,
  VOID: 255,
} as const;
export type TileType = (typeof TileType)[keyof typeof TileType];

export const CharacterState = {
  IDLE: "idle",
  WALK: "walk",
  TYPE: "type",
  COFFEE: "coffee",
  MEETING: "meeting",
  BOARD: "board",
  SIT_IDLE: "sit_idle",
  RELAX: "relax",
  ACT: "act",
} as const;
export type CharacterState =
  (typeof CharacterState)[keyof typeof CharacterState];

export const Direction = {
  DOWN: 0,
  LEFT: 1,
  RIGHT: 2,
  UP: 3,
} as const;
export type Direction = (typeof Direction)[keyof typeof Direction];

export interface ActionBubble {
  icon: string;
  timer: number;
  duration: number;
}

/** A scripted errand: walk to a spot, act briefly, walk back. */
export interface CharacterTask {
  kind: "order" | "chat";
  phase: "go" | "act" | "back";
  standCol: number;
  standRow: number;
  standDir: Direction;
  returnCol: number;
  returnRow: number;
  actTimer: number;
  actDuration: number;
  bubbleIcon: string;
  bubbleDuration: number;
}

export interface Character {
  id: string;
  name: string;
  state: CharacterState;
  dir: Direction;
  x: number;
  y: number;
  tileCol: number;
  tileRow: number;
  path: Array<{ col: number; row: number }>;
  moveProgress: number;
  palette: number;
  frame: number;
  frameTimer: number;
  wanderTimer: number;
  isActive: boolean;
  seatId: string | null;
  currentTool: string | null;
  bubble: ActionBubble | null;
  bubbleQueue: ActionBubble[];
  activityTimer: number;
  /** Countdown driving the idle life-rhythm (paperwork bouts / breaks). */
  restTimer: number;
  /** Set on day_end/run_end: first sit-down afterwards lasts 20-40s. */
  offDuty: boolean;
  task: CharacterTask | null;
  taskQueue: CharacterTask[];
}

export interface Seat {
  uid: string;
  seatCol: number;
  seatRow: number;
  facingDir: Direction;
  assigned: boolean;
  assignedTo: string | null;
}

export interface PlacedFurniture {
  uid: string;
  type: string;
  col: number;
  row: number;
  mirrored?: boolean;
}

export interface FurnitureDefinition {
  type: string;
  label: string;
  footprintW: number;
  footprintH: number;
  imageSrc: string;
  isDesk: boolean;
  isChair: boolean;
  category: string;
}

export interface OfficeLayout {
  version: 1;
  cols: number;
  rows: number;
  tiles: number[];
  furniture: PlacedFurniture[];
}

export const EditTool = {
  SELECT: "select",
  FLOOR_PAINT: "floor_paint",
  WALL_PAINT: "wall_paint",
  FURNITURE_PLACE: "furniture_place",
  ERASE: "erase",
} as const;
export type EditTool = (typeof EditTool)[keyof typeof EditTool];

export const POIType = {
  COFFEE: "coffee",
  BOARD: "board",
  MEETING: "meeting",
  RISK: "risk",
} as const;
export type POIType = (typeof POIType)[keyof typeof POIType];

export interface PointOfInterest {
  uid: string;
  type: POIType;
  col: number;
  row: number;
  facingDir: Direction;
}

export interface BacktestEvent {
  type: string;
  ts: number;
  data: Record<string, unknown>;
}
