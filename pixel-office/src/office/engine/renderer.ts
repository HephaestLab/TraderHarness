import {
  TILE_SIZE,
  TileType,
  type Character,
  type PlacedFurniture,
} from "../types";
import { getSpriteFrame } from "./characters";

const FLOOR_COLOR = "#5c4a3a";
const FLOOR_ALT_COLOR = "#574636";
const WALL_COLOR = "#2e2218";
const WALL_TOP_COLOR = "#3d2f22";
const GRID_LINE_COLOR = "rgba(255,255,255,0.05)";

interface ZDrawable {
  zY: number;
  draw: (ctx: CanvasRenderingContext2D) => void;
}

export function renderFrame(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
  tiles: number[],
  cols: number,
  rows: number,
  furniture: PlacedFurniture[],
  characters: Character[],
  zoom: number,
  panX: number,
  panY: number,
  furnitureImages: Map<string, HTMLImageElement>,
  characterSheet: HTMLImageElement | null,
  showGrid: boolean
): { offsetX: number; offsetY: number } {
  ctx.clearRect(0, 0, canvasWidth, canvasHeight);

  const s = TILE_SIZE * zoom;
  const mapW = cols * s;
  const mapH = rows * s;
  const offsetX = Math.floor((canvasWidth - mapW) / 2) + Math.round(panX);
  const offsetY = Math.floor((canvasHeight - mapH) / 2) + Math.round(panY);

  // Draw tiles
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const tile = tiles[r * cols + c];
      if (tile === TileType.VOID) continue;
      const x = offsetX + c * s;
      const y = offsetY + r * s;
      if (tile === TileType.WALL) {
        ctx.fillStyle = WALL_COLOR;
        ctx.fillRect(x, y, s, s);
        ctx.fillStyle = WALL_TOP_COLOR;
        ctx.fillRect(x, y, s, Math.max(2, s * 0.3));
      } else {
        ctx.fillStyle = (r + c) % 2 === 0 ? FLOOR_COLOR : FLOOR_ALT_COLOR;
        ctx.fillRect(x, y, s, s);
      }
    }
  }

  // Grid overlay
  if (showGrid) {
    ctx.strokeStyle = GRID_LINE_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 0; c <= cols; c++) {
      const x = offsetX + c * s + 0.5;
      ctx.moveTo(x, offsetY);
      ctx.lineTo(x, offsetY + rows * s);
    }
    for (let r = 0; r <= rows; r++) {
      const y = offsetY + r * s + 0.5;
      ctx.moveTo(offsetX, y);
      ctx.lineTo(offsetX + cols * s, y);
    }
    ctx.stroke();
  }

  // Z-sorted drawables (furniture + characters)
  const drawables: ZDrawable[] = [];

  // Furniture
  for (const f of furniture) {
    const img = furnitureImages.get(f.type);
    if (!img || !img.complete || img.naturalWidth === 0) continue;
    const fx = offsetX + f.col * s;
    const fy = offsetY + f.row * s;
    const fw = img.naturalWidth * zoom;
    const fh = img.naturalHeight * zoom;
    const zY = f.row * TILE_SIZE + img.naturalHeight;

    if (f.mirrored) {
      drawables.push({
        zY,
        draw: (c) => {
          c.save();
          c.translate(fx + fw, fy);
          c.scale(-1, 1);
          c.drawImage(img, 0, 0, fw, fh);
          c.restore();
        },
      });
    } else {
      drawables.push({
        zY,
        draw: (c) => {
          c.drawImage(img, fx, fy, fw, fh);
        },
      });
    }
  }

  // Characters (32x32 frames from pre-composited spritesheet)
  const SPRITE_SIZE = 32;
  if (characterSheet) {
    for (const ch of characters) {
      const frame = getSpriteFrame(ch);
      const drawSize = SPRITE_SIZE * zoom;
      const drawX = Math.round(offsetX + ch.x * zoom - drawSize / 2);
      const drawY = Math.round(offsetY + ch.y * zoom - drawSize + s / 2);
      const zY = ch.y + TILE_SIZE / 2;

      const srcX = frame.col * SPRITE_SIZE;
      const srcY = frame.row * SPRITE_SIZE;

      if (frame.flipH) {
        drawables.push({
          zY,
          draw: (c) => {
            c.save();
            c.translate(drawX + drawSize, drawY);
            c.scale(-1, 1);
            c.drawImage(characterSheet, srcX, srcY, SPRITE_SIZE, SPRITE_SIZE, 0, 0, drawSize, drawSize);
            c.restore();
          },
        });
      } else {
        drawables.push({
          zY,
          draw: (c) => {
            c.drawImage(characterSheet, srcX, srcY, SPRITE_SIZE, SPRITE_SIZE, drawX, drawY, drawSize, drawSize);
          },
        });
      }
    }
  }

  drawables.sort((a, b) => a.zY - b.zY);
  for (const d of drawables) {
    d.draw(ctx);
  }

  // Overlay pass: name tags + action bubbles (drawn on top of everything)
  for (const ch of characters) {
    const drawSize = SPRITE_SIZE * zoom;
    const drawX = Math.round(offsetX + ch.x * zoom - drawSize / 2);
    const drawY = Math.round(offsetY + ch.y * zoom - drawSize + s / 2);
    const centerX = drawX + drawSize / 2;

    // Name tag
    const fontSize = Math.max(8, Math.round(zoom * 3.5));
    ctx.font = `bold ${fontSize}px "Courier New", monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const nameY = drawY + drawSize + 2;
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    const nameWidth = ctx.measureText(ch.name).width;
    ctx.fillRect(centerX - nameWidth / 2 - 2, nameY - 1, nameWidth + 4, fontSize + 2);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(ch.name, centerX, nameY);

    // Action bubble
    if (ch.bubble) {
      const bubbleProgress = Math.min(ch.bubble.timer / 0.2, 1);
      const bubbleFade = ch.bubble.timer > ch.bubble.duration - 0.5
        ? (ch.bubble.duration - ch.bubble.timer) / 0.5
        : 1;
      const bubbleScale = bubbleProgress * bubbleFade;
      if (bubbleScale > 0) {
        const bubbleSize = Math.round(zoom * 5 * bubbleScale);
        const bubbleX = centerX;
        const bubbleY = drawY - bubbleSize - 2;

        ctx.globalAlpha = bubbleFade;
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.beginPath();
        ctx.arc(bubbleX, bubbleY, bubbleSize * 0.6, 0, Math.PI * 2);
        ctx.fill();

        ctx.font = `${Math.round(bubbleSize * 0.8)}px serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#000000";
        ctx.fillText(ch.bubble.icon, bubbleX, bubbleY);
        ctx.globalAlpha = 1;
      }
    }
  }

  return { offsetX, offsetY };
}
