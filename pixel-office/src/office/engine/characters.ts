import {
  type Character,
  type CharacterTask,
  type Direction,
  type Seat,
  type PointOfInterest,
  CharacterState,
  Direction as Dir,
  TILE_SIZE,
  TileType,
  POIType,
} from "../types";
import { findPath } from "../layout/pathfinding";

const WALK_SPEED = 48;
const WALK_FRAME_DURATION = 0.18;
const TYPE_FRAME_DURATION = 0.5;
const IDLE_FRAME_DURATION = 0.9;
const ACTIVITY_FRAME_DURATION = 0.6;
const WANDER_PAUSE_MIN = 1.5;
const WANDER_PAUSE_MAX = 4.0;
const ACTIVITY_DURATION_MIN = 3.0;
const ACTIVITY_DURATION_MAX = 6.0;
const BUBBLE_DURATION = 2.0;
const ORDER_BUBBLE_DURATION = 3.5;
const ORDER_ACT_DURATION = 1.2;
const MAX_BUBBLE_BACKLOG = 4;
const MAX_TASK_BACKLOG = 5;

// Idle life-rhythm timings (seconds)
const SIT_REST_MIN = 6;
const SIT_REST_MAX = 14;
const PAPERWORK_MIN = 5;
const PAPERWORK_MAX = 12;
const OFF_DUTY_REST_MIN = 20;
const OFF_DUTY_REST_MAX = 40;
const GUEST_SIT_MIN = 4;
const GUEST_SIT_MAX = 8;

/** Lounge area (strategy meeting room) where seatless agents hang out. */
const LOUNGE = { col0: 1, row0: 7, col1: 8, row1: 11 };

function tileCenter(col: number, row: number) {
  return {
    x: col * TILE_SIZE + TILE_SIZE / 2,
    y: row * TILE_SIZE + TILE_SIZE / 2,
  };
}

function dirBetween(
  fromCol: number,
  fromRow: number,
  toCol: number,
  toRow: number
): Direction {
  const dc = toCol - fromCol;
  const dr = toRow - fromRow;
  if (dc > 0) return Dir.RIGHT;
  if (dc < 0) return Dir.LEFT;
  if (dr > 0) return Dir.DOWN;
  return Dir.UP;
}

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

export function createCharacter(
  id: string,
  name: string,
  palette: number,
  seat: Seat | null
): Character {
  const col = seat ? seat.seatCol : 2;
  const row = seat ? seat.seatRow : 2;
  const center = tileCenter(col, row);
  return {
    id,
    name,
    state: seat ? CharacterState.SIT_IDLE : CharacterState.IDLE,
    dir: seat ? seat.facingDir : Dir.DOWN,
    x: center.x,
    y: center.y,
    tileCol: col,
    tileRow: row,
    path: [],
    moveProgress: 0,
    palette,
    frame: 0,
    frameTimer: 0,
    wanderTimer: rand(1.0, 3.0),
    isActive: false,
    seatId: seat?.uid ?? null,
    currentTool: null,
    bubble: null,
    bubbleQueue: [],
    activityTimer: 0,
    // Staggered so the idle floor comes alive gradually, never in lockstep.
    restTimer: rand(1.5, 6),
    offDuty: false,
    task: null,
    taskQueue: [],
  };
}

export function showBubble(
  ch: Character,
  icon: string,
  duration: number = BUBBLE_DURATION
): void {
  // Dedupe consecutive identical icons so dense event streams stay readable.
  const last =
    ch.bubbleQueue.length > 0
      ? ch.bubbleQueue[ch.bubbleQueue.length - 1]
      : ch.bubble;
  if (last && last.icon === icon) return;
  const bubble = { icon, timer: 0, duration };
  if (!ch.bubble) {
    ch.bubble = bubble;
  } else {
    ch.bubbleQueue.push(bubble);
    if (ch.bubbleQueue.length > MAX_BUBBLE_BACKLOG) {
      ch.bubbleQueue.splice(0, ch.bubbleQueue.length - MAX_BUBBLE_BACKLOG);
    }
  }
}

function updateBubble(ch: Character, dt: number): void {
  if (ch.bubble) {
    ch.bubble.timer += dt;
    if (ch.bubble.timer >= ch.bubble.duration) {
      ch.bubble = ch.bubbleQueue.shift() ?? null;
    }
  } else if (ch.bubbleQueue.length > 0) {
    ch.bubble = ch.bubbleQueue.shift()!;
  }
}

export interface TaskSpec {
  kind: "order" | "chat";
  standCol: number;
  standRow: number;
  standDir: Direction;
  returnCol: number;
  returnRow: number;
  actDuration: number;
  bubbleIcon: string;
  bubbleDuration: number;
}

export function enqueueTask(ch: Character, spec: TaskSpec): void {
  const task: CharacterTask = { phase: "go", actTimer: 0, ...spec };
  ch.taskQueue.push(task);
  if (ch.taskQueue.length > MAX_TASK_BACKLOG) {
    ch.taskQueue.splice(0, ch.taskQueue.length - MAX_TASK_BACKLOG);
  }
}

export function enqueueOrderTask(
  ch: Character,
  standCol: number,
  standRow: number,
  standDir: Direction,
  returnCol: number,
  returnRow: number,
  bubbleIcon: string
): void {
  enqueueTask(ch, {
    kind: "order",
    standCol,
    standRow,
    standDir,
    returnCol,
    returnRow,
    actDuration: ORDER_ACT_DURATION,
    bubbleIcon,
    bubbleDuration: ORDER_BUBBLE_DURATION,
  });
}

/** Advance the walk-cycle movement one step; returns true on arrival. */
function stepWalk(ch: Character, dt: number): boolean {
  if (ch.frameTimer >= WALK_FRAME_DURATION) {
    ch.frameTimer -= WALK_FRAME_DURATION;
    ch.frame = (ch.frame + 1) % 4;
  }

  if (ch.path.length === 0) {
    const center = tileCenter(ch.tileCol, ch.tileRow);
    ch.x = center.x;
    ch.y = center.y;
    ch.frame = 0;
    ch.frameTimer = 0;
    return true;
  }

  const next = ch.path[0];
  ch.dir = dirBetween(ch.tileCol, ch.tileRow, next.col, next.row);
  ch.moveProgress += (WALK_SPEED / TILE_SIZE) * dt;

  const from = tileCenter(ch.tileCol, ch.tileRow);
  const to = tileCenter(next.col, next.row);
  const t = Math.min(ch.moveProgress, 1);
  ch.x = from.x + (to.x - from.x) * t;
  ch.y = from.y + (to.y - from.y) * t;

  if (ch.moveProgress >= 1) {
    ch.tileCol = next.col;
    ch.tileRow = next.row;
    ch.x = to.x;
    ch.y = to.y;
    ch.path.shift();
    ch.moveProgress = 0;
  }
  return false;
}

function startWalkTo(
  ch: Character,
  col: number,
  row: number,
  tiles: number[],
  cols: number,
  rows: number
): boolean {
  if (ch.tileCol === col && ch.tileRow === row) return false;
  const path = findPath(ch.tileCol, ch.tileRow, col, row, tiles, cols, rows);
  if (path.length === 0) return false;
  ch.path = path;
  ch.moveProgress = 0;
  ch.state = CharacterState.WALK;
  ch.frame = 0;
  ch.frameTimer = 0;
  return true;
}

function finishTaskLeg(ch: Character, task: CharacterTask): void {
  if (task.phase === "go") {
    task.phase = "act";
    task.actTimer = task.actDuration;
    ch.state = CharacterState.ACT;
    ch.dir = task.standDir;
    ch.frame = 0;
    ch.frameTimer = 0;
    showBubble(ch, task.bubbleIcon, task.bubbleDuration);
  } else {
    ch.task = null;
    ch.state = CharacterState.IDLE;
    ch.frame = 0;
    ch.frameTimer = 0;
    ch.wanderTimer = rand(0.5, 1.5);
  }
}

/** Runs the goto -> act -> return errand machine. */
function updateTask(
  ch: Character,
  dt: number,
  tiles: number[],
  cols: number,
  rows: number
): void {
  if (!ch.task) {
    ch.task = ch.taskQueue.shift() ?? null;
    if (ch.task) {
      ch.task.phase = "go";
      ch.state = CharacterState.IDLE;
      ch.path = [];
      ch.moveProgress = 0;
    }
  }
  const task = ch.task;
  if (!task) return;

  if (task.phase === "act") {
    if (ch.frameTimer >= ACTIVITY_FRAME_DURATION) {
      ch.frameTimer -= ACTIVITY_FRAME_DURATION;
      ch.frame = (ch.frame + 1) % 2;
    }
    task.actTimer -= dt;
    if (task.actTimer <= 0) {
      task.phase = "back";
      ch.state = CharacterState.IDLE;
      ch.frame = 0;
      ch.frameTimer = 0;
    }
    return;
  }

  const target =
    task.phase === "go"
      ? { col: task.standCol, row: task.standRow }
      : { col: task.returnCol, row: task.returnRow };

  if (ch.state !== CharacterState.WALK) {
    if (ch.tileCol === target.col && ch.tileRow === target.row) {
      finishTaskLeg(ch, task);
      return;
    }
    if (!startWalkTo(ch, target.col, target.row, tiles, cols, rows)) {
      // Unreachable — abandon the errand gracefully.
      ch.task = null;
      ch.state = CharacterState.IDLE;
      ch.wanderTimer = rand(0.5, 1.5);
    }
    return;
  }

  if (stepWalk(ch, dt)) {
    ch.state = CharacterState.IDLE;
    finishTaskLeg(ch, task);
  }
}

function wanderTarget(
  tiles: number[],
  cols: number,
  rows: number
): { col: number; row: number } | null {
  // Seatless agents linger around the lounge / meeting area instead of
  // drifting across the whole floor.
  const lounge: Array<{ col: number; row: number }> = [];
  const anywhere: Array<{ col: number; row: number }> = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (tiles[r * cols + c] === TileType.FLOOR) {
        anywhere.push({ col: c, row: r });
        if (c >= LOUNGE.col0 && c <= LOUNGE.col1 && r >= LOUNGE.row0 && r <= LOUNGE.row1) {
          lounge.push({ col: c, row: r });
        }
      }
    }
  }
  const pool = lounge.length > 0 ? lounge : anywhere;
  if (pool.length === 0) return null;
  return pool[Math.floor(Math.random() * pool.length)];
}

function strollTarget(
  ch: Character,
  tiles: number[],
  cols: number,
  rows: number
): { col: number; row: number } | null {
  // Seated agents on a break prefer the aisle and its neighbouring rows.
  const candidates: Array<{ col: number; row: number }> = [];
  for (let r = 1; r < rows - 1; r++) {
    for (let c = 1; c < cols - 1; c++) {
      if (tiles[r * cols + c] !== TileType.FLOOR) continue;
      if (c === ch.tileCol && r === ch.tileRow) continue;
      const aisleBias = Math.abs(r - 6) <= 1 ? 2 : 1;
      for (let i = 0; i < aisleBias; i++) candidates.push({ col: c, row: r });
    }
  }
  if (candidates.length === 0) return null;
  return candidates[Math.floor(Math.random() * candidates.length)];
}

/**
 * Pick an idle break for a seated agent: POI visit (coffee/water/board),
 * a guest sit on a free lounge chair, or a simple stroll down the aisle.
 */
function startBreak(
  ch: Character,
  tiles: number[],
  cols: number,
  rows: number,
  seats: Map<string, Seat>,
  pois: PointOfInterest[]
): boolean {
  const roll = Math.random();

  if (roll < 0.45) {
    const casual = pois.filter((poi) => poi.type !== POIType.RISK);
    if (casual.length > 0) {
      const poi = casual[Math.floor(Math.random() * casual.length)];
      if (startWalkTo(ch, poi.col, poi.row, tiles, cols, rows)) {
        (ch as unknown as Record<string, string>)._targetPOI = poi.type;
        (ch as unknown as Record<string, number>)._targetDir = poi.facingDir;
        return true;
      }
    }
  } else if (roll < 0.72) {
    const freeChairs = [...seats.values()].filter(
      (seat) => !seat.assigned && seat.uid !== ch.seatId
    );
    if (freeChairs.length > 0) {
      const chair = freeChairs[Math.floor(Math.random() * freeChairs.length)];
      if (startWalkTo(ch, chair.seatCol, chair.seatRow, tiles, cols, rows)) {
        // Face the meeting table while guest-sitting, if there is one.
        const table = pois.find((poi) => poi.type === POIType.MEETING);
        const facing = table
          ? dirBetween(chair.seatCol, chair.seatRow, table.col, table.row)
          : chair.facingDir;
        (ch as unknown as Record<string, number>)._guestSit = facing;
        return true;
      }
    }
  } else {
    const target = strollTarget(ch, tiles, cols, rows);
    if (target && startWalkTo(ch, target.col, target.row, tiles, cols, rows)) {
      return true;
    }
  }
  return false;
}

export function updateCharacter(
  ch: Character,
  dt: number,
  tiles: number[],
  cols: number,
  rows: number,
  seats: Map<string, Seat>,
  pois: PointOfInterest[]
): void {
  ch.frameTimer += dt;
  updateBubble(ch, dt);

  // Scripted errands (orders to the risk desk, water-cooler chats) come first.
  if (ch.task || ch.taskQueue.length > 0) {
    updateTask(ch, dt, tiles, cols, rows);
    return;
  }

  switch (ch.state) {
    case CharacterState.SIT_IDLE: {
      ch.frame = 0;
      if (ch.isActive) {
        ch.state = CharacterState.TYPE;
        ch.frame = 0;
        ch.frameTimer = 0;
        break;
      }
      // Idle life rhythm: sit for a while, then either a paperwork typing
      // bout (~45%) or a break away from the desk.
      ch.restTimer -= dt;
      if (ch.restTimer <= 0) {
        if (Math.random() < 0.5) {
          ch.state = CharacterState.TYPE;
          ch.frame = 0;
          ch.frameTimer = 0;
          ch.restTimer = rand(PAPERWORK_MIN, PAPERWORK_MAX);
        } else if (!startBreak(ch, tiles, cols, rows, seats, pois)) {
          ch.restTimer = rand(6, 12);
        }
      }
      break;
    }

    case CharacterState.RELAX: {
      // Guest-sitting on a lounge chair; head back to the desk afterwards.
      ch.frame = 0;
      ch.activityTimer -= dt;
      if (ch.activityTimer <= 0) {
        ch.state = CharacterState.IDLE;
        ch.frame = 0;
        ch.frameTimer = 0;
        ch.wanderTimer = rand(0.5, 1.5);
      }
      break;
    }

    case CharacterState.TYPE: {
      if (ch.frameTimer >= TYPE_FRAME_DURATION) {
        ch.frameTimer -= TYPE_FRAME_DURATION;
        ch.frame = (ch.frame + 1) % 2;
      }
      if (!ch.isActive) {
        // After hours, wrap up the current bout quickly, then rest longer.
        if (ch.offDuty) ch.restTimer = Math.min(ch.restTimer, 1.2);
        ch.restTimer -= dt;
        if (ch.restTimer <= 0) {
          ch.state = CharacterState.SIT_IDLE;
          ch.frame = 0;
          ch.frameTimer = 0;
          ch.restTimer = ch.offDuty
            ? rand(OFF_DUTY_REST_MIN, OFF_DUTY_REST_MAX)
            : rand(SIT_REST_MIN, SIT_REST_MAX);
          ch.offDuty = false;
        }
      }
      break;
    }

    case CharacterState.COFFEE:
    case CharacterState.BOARD:
    case CharacterState.MEETING: {
      if (ch.frameTimer >= ACTIVITY_FRAME_DURATION) {
        ch.frameTimer -= ACTIVITY_FRAME_DURATION;
        ch.frame = (ch.frame + 1) % 2;
      }
      ch.activityTimer -= dt;
      if (ch.activityTimer <= 0) {
        ch.state = CharacterState.IDLE;
        ch.frame = 0;
        ch.frameTimer = 0;
        ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
      }
      break;
    }

    case CharacterState.IDLE: {
      // Gentle breathing while standing.
      if (ch.frameTimer >= IDLE_FRAME_DURATION) {
        ch.frameTimer -= IDLE_FRAME_DURATION;
        ch.frame = (ch.frame + 1) % 2;
      }

      // Seated agents return to their desk — to work while the run is live,
      // or to sit between breaks when idle.
      if (ch.seatId) {
        const seat = seats.get(ch.seatId);
        if (seat) {
          if (ch.tileCol === seat.seatCol && ch.tileRow === seat.seatRow) {
            ch.state = ch.isActive ? CharacterState.TYPE : CharacterState.SIT_IDLE;
            ch.dir = seat.facingDir;
            ch.frame = 0;
            ch.frameTimer = 0;
            if (!ch.isActive) {
              ch.restTimer = ch.offDuty
                ? rand(OFF_DUTY_REST_MIN, OFF_DUTY_REST_MAX)
                : rand(SIT_REST_MIN, SIT_REST_MAX + 4);
              ch.offDuty = false;
            }
          } else if (!startWalkTo(ch, seat.seatCol, seat.seatRow, tiles, cols, rows)) {
            ch.state = ch.isActive ? CharacterState.TYPE : CharacterState.SIT_IDLE;
            ch.dir = seat.facingDir;
          }
          break;
        }
      }

      // Seatless agents wander around the lounge and visit POIs.
      ch.wanderTimer -= dt;
      if (ch.wanderTimer <= 0) {
        const casualPOIs = pois.filter((poi) => poi.type !== POIType.RISK);
        const visitPOI = casualPOIs.length > 0 && Math.random() < 0.4;

        if (visitPOI) {
          const poi = casualPOIs[Math.floor(Math.random() * casualPOIs.length)];
          if (
            startWalkTo(ch, poi.col, poi.row, tiles, cols, rows)
          ) {
            (ch as unknown as Record<string, string>)._targetPOI = poi.type;
            (ch as unknown as Record<string, number>)._targetDir = poi.facingDir;
          } else {
            ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
          }
        } else {
          const target = wanderTarget(tiles, cols, rows);
          if (target) {
            startWalkTo(ch, target.col, target.row, tiles, cols, rows);
          }
          ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
        }
      }
      break;
    }

    case CharacterState.WALK: {
      if (!stepWalk(ch, dt)) break;

      // Arrived.
      if (ch.seatId) {
        const seat = seats.get(ch.seatId);
        if (seat && ch.tileCol === seat.seatCol && ch.tileRow === seat.seatRow) {
          ch.state = ch.isActive ? CharacterState.TYPE : CharacterState.SIT_IDLE;
          ch.dir = seat.facingDir;
          if (!ch.isActive) {
            ch.restTimer = ch.offDuty
              ? rand(OFF_DUTY_REST_MIN, OFF_DUTY_REST_MAX)
              : rand(SIT_REST_MIN, SIT_REST_MAX + 4);
            ch.offDuty = false;
          }
          break;
        }
      }

      const guestSit = (ch as unknown as Record<string, number>)._guestSit;
      if (guestSit !== undefined) {
        delete (ch as unknown as Record<string, number>)._guestSit;
        ch.state = CharacterState.RELAX;
        ch.dir = guestSit as Direction;
        ch.activityTimer = rand(GUEST_SIT_MIN, GUEST_SIT_MAX);
        break;
      }

      const targetPOI = (ch as unknown as Record<string, string>)._targetPOI;
      const targetDir = (ch as unknown as Record<string, number>)._targetDir;
      if (targetPOI) {
        delete (ch as unknown as Record<string, string>)._targetPOI;
        delete (ch as unknown as Record<string, number>)._targetDir;
        switch (targetPOI) {
          case POIType.COFFEE:
            ch.state = CharacterState.COFFEE;
            showBubble(ch, "coffee");
            break;
          case POIType.BOARD:
            ch.state = CharacterState.BOARD;
            showBubble(ch, "board");
            break;
          case POIType.MEETING:
            ch.state = CharacterState.MEETING;
            showBubble(ch, "think");
            break;
          default:
            ch.state = CharacterState.IDLE;
        }
        if (targetDir !== undefined) {
          ch.dir = targetDir as Direction;
        }
        ch.activityTimer = rand(ACTIVITY_DURATION_MIN, ACTIVITY_DURATION_MAX);
      } else {
        ch.state = CharacterState.IDLE;
        ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
      }
      break;
    }
  }
}

// ---------------------------------------------------------------------------
// Sprite sheet mapping
// Sheet: 8 cols x 24 rows of 32x32 frames; each character owns a 6-row block.
//   block+0 DOWN, block+1 UP, block+2 RIGHT, block+3 LEFT
//     (col 0-1 idle breathing, col 2-5 walk cycle)
//   block+4 SIT     (col 0-1 UP, col 2-3 DOWN, col 4-5 RIGHT, col 6-7 LEFT)
//   block+5 PRESENT (same column scheme as SIT)
// ---------------------------------------------------------------------------

export const SPRITE_SIZE = 32;
export const CHARACTER_DRAW_SIZE = 28;

const BLOCK_ROWS = 6;
const ROW_DOWN = 0;
const ROW_UP = 1;
const ROW_RIGHT = 2;
const ROW_LEFT = 3;
const ROW_SIT = 4;
const ROW_PRESENT = 5;

function dirRow(dir: Direction): number {
  switch (dir) {
    case Dir.UP:
      return ROW_UP;
    case Dir.RIGHT:
      return ROW_RIGHT;
    case Dir.LEFT:
      return ROW_LEFT;
    default:
      return ROW_DOWN;
  }
}

/** Column base for directional poses inside the SIT / PRESENT rows. */
function poseCol(dir: Direction): number {
  switch (dir) {
    case Dir.UP:
      return 0;
    case Dir.DOWN:
      return 2;
    case Dir.RIGHT:
      return 4;
    default:
      return 6; // LEFT
  }
}

export interface SpriteFrame {
  col: number;
  row: number;
  flipH: boolean;
}

export function getSpriteFrame(ch: Character): SpriteFrame {
  const block = (ch.palette % 4) * BLOCK_ROWS;

  switch (ch.state) {
    case CharacterState.WALK:
      return { col: 2 + (ch.frame % 4), row: block + dirRow(ch.dir), flipH: false };
    case CharacterState.TYPE:
      return { col: poseCol(ch.dir) + (ch.frame % 2), row: block + ROW_SIT, flipH: false };
    case CharacterState.SIT_IDLE:
    case CharacterState.RELAX:
      return { col: poseCol(ch.dir), row: block + ROW_SIT, flipH: false };
    case CharacterState.ACT:
    case CharacterState.BOARD:
    case CharacterState.MEETING:
      return { col: poseCol(ch.dir) + (ch.frame % 2), row: block + ROW_PRESENT, flipH: false };
    case CharacterState.COFFEE:
    case CharacterState.IDLE:
    default:
      return { col: ch.frame % 2, row: block + dirRow(ch.dir), flipH: false };
  }
}
