import {
  type Character,
  type Direction,
  type Seat,
  type PointOfInterest,
  CharacterState,
  Direction as Dir,
  TILE_SIZE,
  TileType,
} from "../types";
import { findPath } from "../layout/pathfinding";

const WALK_SPEED = 48;
const WALK_FRAME_DURATION = 0.18;
const TYPE_FRAME_DURATION = 0.5;
const ACTIVITY_FRAME_DURATION = 0.6;
const WANDER_PAUSE_MIN = 2.0;
const WANDER_PAUSE_MAX = 5.0;
const ACTIVITY_DURATION_MIN = 3.0;
const ACTIVITY_DURATION_MAX = 6.0;
const BUBBLE_DURATION = 2.5;

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
    state: CharacterState.IDLE,
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
    activityTimer: 0,
  };
}

export function showBubble(ch: Character, icon: string): void {
  ch.bubble = { icon, timer: 0, duration: BUBBLE_DURATION };
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

  // Update bubble timer
  if (ch.bubble) {
    ch.bubble.timer += dt;
    if (ch.bubble.timer >= ch.bubble.duration) {
      ch.bubble = null;
    }
  }

  switch (ch.state) {
    case CharacterState.TYPE: {
      if (ch.frameTimer >= TYPE_FRAME_DURATION) {
        ch.frameTimer -= TYPE_FRAME_DURATION;
        ch.frame = (ch.frame + 1) % 2;
      }
      if (!ch.isActive) {
        ch.state = CharacterState.IDLE;
        ch.frame = 0;
        ch.frameTimer = 0;
        ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
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
      ch.frame = 0;
      // Active agent → go back to seat and type
      if (ch.isActive && ch.seatId) {
        const seat = seats.get(ch.seatId);
        if (seat) {
          const path = findPath(
            ch.tileCol, ch.tileRow,
            seat.seatCol, seat.seatRow,
            tiles, cols, rows
          );
          if (path.length > 0) {
            ch.path = path;
            ch.moveProgress = 0;
            ch.state = CharacterState.WALK;
          } else {
            ch.state = CharacterState.TYPE;
            ch.dir = seat.facingDir;
          }
        }
        break;
      }

      ch.wanderTimer -= dt;
      if (ch.wanderTimer <= 0) {
        // 40% chance to visit a POI, 60% random wander
        const visitPOI = pois.length > 0 && Math.random() < 0.4;

        if (visitPOI) {
          const poi = pois[Math.floor(Math.random() * pois.length)];
          const path = findPath(
            ch.tileCol, ch.tileRow,
            poi.col, poi.row,
            tiles, cols, rows
          );
          if (path.length > 0) {
            ch.path = path;
            ch.moveProgress = 0;
            ch.state = CharacterState.WALK;
            ch.frame = 0;
            ch.frameTimer = 0;
            // Store destination POI type for arrival behavior
            (ch as unknown as Record<string, string>)._targetPOI = poi.type;
            (ch as unknown as Record<string, number>)._targetDir = poi.facingDir;
          } else {
            ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
          }
        } else {
          const walkable: Array<{ col: number; row: number }> = [];
          for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
              if (tiles[r * cols + c] === TileType.FLOOR) {
                walkable.push({ col: c, row: r });
              }
            }
          }
          if (walkable.length > 0) {
            const target = walkable[Math.floor(Math.random() * walkable.length)];
            const path = findPath(
              ch.tileCol, ch.tileRow,
              target.col, target.row,
              tiles, cols, rows
            );
            if (path.length > 0) {
              ch.path = path;
              ch.moveProgress = 0;
              ch.state = CharacterState.WALK;
              ch.frame = 0;
              ch.frameTimer = 0;
            }
          }
          ch.wanderTimer = rand(WANDER_PAUSE_MIN, WANDER_PAUSE_MAX);
        }
      }
      break;
    }

    case CharacterState.WALK: {
      if (ch.frameTimer >= WALK_FRAME_DURATION) {
        ch.frameTimer -= WALK_FRAME_DURATION;
        ch.frame = (ch.frame + 1) % 6;
      }

      if (ch.path.length === 0) {
        const center = tileCenter(ch.tileCol, ch.tileRow);
        ch.x = center.x;
        ch.y = center.y;

        // Check if arrived at seat (active typing)
        if (ch.isActive && ch.seatId) {
          const seat = seats.get(ch.seatId);
          if (seat && ch.tileCol === seat.seatCol && ch.tileRow === seat.seatRow) {
            ch.state = CharacterState.TYPE;
            ch.dir = seat.facingDir;
          } else {
            ch.state = CharacterState.IDLE;
          }
        } else {
          // Check if arrived at POI
          const targetPOI = (ch as unknown as Record<string, string>)._targetPOI;
          const targetDir = (ch as unknown as Record<string, number>)._targetDir;
          if (targetPOI) {
            delete (ch as unknown as Record<string, string>)._targetPOI;
            delete (ch as unknown as Record<string, number>)._targetDir;
            switch (targetPOI) {
              case "coffee":
                ch.state = CharacterState.COFFEE;
                showBubble(ch, "☕");
                break;
              case "board":
                ch.state = CharacterState.BOARD;
                showBubble(ch, "📊");
                break;
              case "meeting":
                ch.state = CharacterState.MEETING;
                showBubble(ch, "💬");
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
        }
        ch.frame = 0;
        ch.frameTimer = 0;
        break;
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
      break;
    }
  }
}

export interface SpriteFrame {
  col: number;
  row: number;
  flipH: boolean;
}

export function getSpriteFrame(ch: Character): SpriteFrame {
  const row = ch.palette % 4;

  const dirBase: Record<Direction, number> = {
    [Dir.DOWN]: 0,
    [Dir.LEFT]: 18,
    [Dir.UP]: 12,
    [Dir.RIGHT]: 6,
  };

  const base = dirBase[ch.dir];

  switch (ch.state) {
    case CharacterState.WALK: {
      const walkFrame = ch.frame % 6;
      return { col: base + walkFrame, row, flipH: false };
    }
    case CharacterState.TYPE:
    case CharacterState.COFFEE:
    case CharacterState.BOARD:
    case CharacterState.MEETING:
      return { col: base + (ch.frame % 2) * 2, row, flipH: false };
    case CharacterState.IDLE:
    default:
      return { col: base, row, flipH: false };
  }
}
