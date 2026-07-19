import {
  TILE_SIZE,
  TileType,
  type Character,
  type PlacedFurniture,
} from "../types";
import {
  getSpriteFrame,
  SPRITE_SIZE,
  CHARACTER_DRAW_SIZE,
} from "./characters";
import type { RunContext } from "./officeState";

const GRID_LINE_COLOR = "rgba(255,255,255,0.05)";

interface ZDrawable {
  zY: number;
  draw: (ctx: CanvasRenderingContext2D) => void;
}

// ---------------------------------------------------------------------------
// Deterministic hashing for floor / wall detail
// ---------------------------------------------------------------------------

function hash2(x: number, y: number, s: number): number {
  let h = (x * 374761393 + y * 668265263 + s * 1013904223) | 0;
  h = (h ^ (h >> 13)) * 1274126177;
  return (h ^ (h >> 16)) >>> 0;
}

// ---------------------------------------------------------------------------
// Baked tile layer (floor planks, walls, zone tints, rug) rendered once per
// layout at 16px-per-tile resolution, then blitted with nearest-neighbor.
// ---------------------------------------------------------------------------

let tileLayer: HTMLCanvasElement | null = null;
let tileLayerKey = "";

function tilesChecksum(tiles: number[]): number {
  let h = tiles.length | 0;
  for (let i = 0; i < tiles.length; i++) {
    h = (h * 31 + tiles[i]) | 0;
  }
  return h;
}

function buildTileLayer(tiles: number[], cols: number, rows: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = cols * TILE_SIZE;
  canvas.height = rows * TILE_SIZE;
  const g = canvas.getContext("2d")!;

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const tile = tiles[r * cols + c];
      if (tile === TileType.VOID) continue;
      const bx = c * TILE_SIZE;
      const by = r * TILE_SIZE;
      if (tile === TileType.WALL) {
        drawWallTile(g, bx, by, c, r);
      } else {
        drawFloorTile(g, bx, by, c, r);
      }
    }
  }

  // Zone tints (kept subtle so the wood grain still shows through).
  const zones = [
    { col: 1.35, row: 1.45, width: 15.3, height: 4.25, color: "rgba(30,80,88,.16)" },
    { col: 1.35, row: 7.3, width: 8.1, height: 4.35, color: "rgba(26,86,72,.18)" },
    { col: 9.75, row: 7.3, width: 6.9, height: 4.35, color: "rgba(70,42,86,.18)" },
  ];
  for (const z of zones) {
    g.fillStyle = z.color;
    g.fillRect(z.col * TILE_SIZE, z.row * TILE_SIZE, z.width * TILE_SIZE, z.height * TILE_SIZE);
    g.strokeStyle = "rgba(255,255,255,.06)";
    g.lineWidth = 1;
    g.strokeRect(z.col * TILE_SIZE + 0.5, z.row * TILE_SIZE + 0.5, z.width * TILE_SIZE - 1, z.height * TILE_SIZE - 1);
  }

  drawRug(g);
  return canvas;
}

function drawFloorTile(g: CanvasRenderingContext2D, bx: number, by: number, c: number, r: number) {
  const v = (hash2(c, r, 1) % 7) - 3; // -3..3
  const base = { r: 46 + v * 2, g: 35 + v * 2, b: 24 + v };
  g.fillStyle = `rgb(${base.r},${base.g},${base.b})`;
  g.fillRect(bx, by, TILE_SIZE, TILE_SIZE);

  // Horizontal planks, 4px tall, staggered joints every other plank row.
  for (let p = 0; p < 4; p++) {
    const shade = ((hash2(c, r * 4 + p, 2) % 5) - 2) * 2;
    g.fillStyle = `rgba(${base.r + shade},${base.g + shade},${base.b + shade},1)`;
    g.fillRect(bx, by + p * 4, TILE_SIZE, 4);
    // seam + top highlight
    g.fillStyle = "rgba(9,6,3,0.5)";
    g.fillRect(bx, by + p * 4, TILE_SIZE, 1);
    g.fillStyle = "rgba(255,214,160,0.05)";
    g.fillRect(bx, by + p * 4 + 1, TILE_SIZE, 1);
    // plank joint
    const globalPlank = r * 4 + p;
    if ((c + globalPlank) % 2 === 0) {
      g.fillStyle = "rgba(9,6,3,0.55)";
      g.fillRect(bx, by + p * 4, 1, 4);
    }
  }

  // Grain streak
  if (hash2(c, r, 3) % 4 === 0) {
    const gy = by + 2 + (hash2(c, r, 4) % 12);
    const gx = bx + (hash2(c, r, 5) % 8);
    g.fillStyle = "rgba(18,12,7,0.4)";
    g.fillRect(gx, gy, 4 + (hash2(c, r, 6) % 5), 1);
  }
  // Knot
  if (hash2(c, r, 7) % 11 === 0) {
    const kx = bx + 3 + (hash2(c, r, 8) % 10);
    const ky = by + 3 + (hash2(c, r, 9) % 10);
    g.fillStyle = "rgba(22,14,8,0.65)";
    g.fillRect(kx, ky, 3, 2);
    g.fillStyle = "rgba(10,6,3,0.8)";
    g.fillRect(kx + 1, ky, 1, 1);
  }
}

function drawWallTile(g: CanvasRenderingContext2D, bx: number, by: number, c: number, r: number) {
  const v = (hash2(c, r, 11) % 5) - 2;
  g.fillStyle = `rgb(${37 + v},${28 + v},${50 + v})`;
  g.fillRect(bx, by, TILE_SIZE, TILE_SIZE);

  // Lighter top cap with a highlight line (catches the "ceiling" light).
  g.fillStyle = `rgb(${58 + v},${44 + v},${78 + v})`;
  g.fillRect(bx, by, TILE_SIZE, 4);
  g.fillStyle = "rgba(255,255,255,0.07)";
  g.fillRect(bx, by + 4, TILE_SIZE, 1);

  // Vertical panel seams give the flat wall a pixel-panel rhythm.
  g.fillStyle = "rgba(0,0,0,0.22)";
  g.fillRect(bx, by, 1, TILE_SIZE);
  if (c % 2 === 0) {
    g.fillStyle = "rgba(255,255,255,0.03)";
    g.fillRect(bx + 8, by + 6, 1, 7);
  }

  // Baseboard (踢脚线) along the bottom of every wall tile.
  g.fillStyle = "rgba(15,10,22,1)";
  g.fillRect(bx, by + 13, TILE_SIZE, 3);
  g.fillStyle = "rgba(255,255,255,0.05)";
  g.fillRect(bx, by + 13, TILE_SIZE, 1);
}

function drawRug(g: CanvasRenderingContext2D) {
  // Dark rug anchoring the strategy meeting area (round table + sofa).
  const x = 1.5 * TILE_SIZE;
  const y = 7.5 * TILE_SIZE;
  const w = 5 * TILE_SIZE;
  const h = 3 * TILE_SIZE;
  const rad = 7;

  g.fillStyle = "#262c40";
  g.beginPath();
  g.roundRect(x, y, w, h, rad);
  g.fill();
  g.strokeStyle = "#171b2a";
  g.lineWidth = 2;
  g.stroke();

  // Inner dotted border motif.
  g.fillStyle = "rgba(98,110,150,0.8)";
  for (let i = x + 6; i < x + w - 6; i += 4) {
    g.fillRect(i, y + 4, 2, 1);
    g.fillRect(i, y + h - 5, 2, 1);
  }
  for (let i = y + 6; i < y + h - 6; i += 4) {
    g.fillRect(x + 4, i, 1, 2);
    g.fillRect(x + w - 5, i, 1, 2);
  }
  // Corner diamonds.
  g.fillStyle = "rgba(120,132,176,0.9)";
  const corners: Array<[number, number]> = [
    [x + 7, y + 7],
    [x + w - 8, y + 7],
    [x + 7, y + h - 8],
    [x + w - 8, y + h - 8],
  ];
  for (const [cx, cy] of corners) {
    g.fillRect(cx, cy - 1, 1, 3);
    g.fillRect(cx - 1, cy, 3, 1);
  }
}

// ---------------------------------------------------------------------------
// Procedural 16x16 pixel icons (no emoji — platform independent)
// ---------------------------------------------------------------------------

const ICON_OUTLINE = "#17131f";

interface IconArt {
  palette: Record<string, string>;
  rows: string[];
}

const ICON_ART: Record<string, IconArt> = {
  buy: {
    palette: { G: "#43c580" },
    rows: [
      "................",
      ".......GG.......",
      "......GGGG......",
      ".....GGGGGG.....",
      "....GGGGGGGG....",
      "...GGGGGGGGGG...",
      "..GGGGGGGGGGGG..",
      ".....GGGG.......",
      ".....GGGG.......",
      ".....GGGG.......",
      ".....GGGG.......",
      ".....GGGG.......",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  sell: {
    palette: { R: "#e06060" },
    rows: [
      "................",
      "................",
      "................",
      "................",
      ".....RRRR.......",
      ".....RRRR.......",
      ".....RRRR.......",
      ".....RRRR.......",
      ".....RRRR.......",
      "..RRRRRRRRRRRR..",
      "...RRRRRRRRRR...",
      "....RRRRRRRR....",
      ".....RRRRRR.....",
      "......RRRR......",
      ".......RR.......",
      "................",
    ],
  },
  think: {
    palette: { g: "#a8b8cc" },
    rows: [
      "................",
      "................",
      "....ggggggg.....",
      "..ggggggggggg...",
      ".ggggggggggggg..",
      ".ggggggggggggg..",
      "..ggggggggggg...",
      "....ggggggg.....",
      "................",
      "...gg...........",
      "..gg............",
      "................",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  coffee: {
    palette: { B: "#c98f4e", l: "#7a4a24", w: "#c8d2dc" },
    rows: [
      "................",
      "....w...w.......",
      ".....w...w......",
      "....w...w.......",
      "................",
      "..llllllll......",
      "..BBBBBBBB..BB..",
      "..BBBBBBBB.B..B.",
      "..BBBBBBBB.B..B.",
      "..BBBBBBBB..BB..",
      "..BBBBBBBB......",
      "...BBBBBB.......",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  board: {
    palette: { b: "#58a6d9" },
    rows: [
      "................",
      "................",
      "............bb..",
      "............bb..",
      "........bb..bb..",
      "........bb..bb..",
      "....bb..bb..bb..",
      "....bb..bb..bb..",
      "....bb..bb..bb..",
      ".bb..bb..bb..bb.",
      ".bb..bb..bb..bb.",
      ".bbbbbbbbbbbbbb.",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  rocket: {
    palette: { v: "#a78bfa", w: "#eef4fb", f: "#f0883e" },
    rows: [
      "................",
      ".......vv.......",
      "......vvvv......",
      ".....vvwwvv.....",
      ".....vvwwvv.....",
      "....vvvvvvvv....",
      "....vvvvvvvv....",
      "...vvvvvvvvvv...",
      "...vvvvvvvvvv...",
      "..vv.vvvvvv.vv..",
      "......vvvv......",
      ".......ff.......",
      "......ffff......",
      ".....ffffff.....",
      "................",
      "................",
    ],
  },
  check: {
    palette: { G: "#4ecb71" },
    rows: [
      "................",
      "................",
      ".............GG.",
      "............GGG.",
      "...........GGG..",
      "..G.......GGG...",
      "..GGG....GGG....",
      "...GGG..GGG.....",
      "....GGGGGG......",
      ".....GGGG.......",
      "................",
      "................",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  bell: {
    palette: { y: "#e3b341", d: "#8a6a1e" },
    rows: [
      "................",
      ".......yy.......",
      "......yyyy......",
      ".....yyyyyy.....",
      ".....yyyyyy.....",
      "....yyyyyyyy....",
      "....yyyyyyyy....",
      "...yyyyyyyyyy...",
      "...yyyyyyyyyy...",
      "..yyyyyyyyyyyy..",
      "..yyyyyyyyyyyy..",
      ".yyyyyyyyyyyyyy.",
      ".......dd.......",
      "......dddd......",
      "................",
      "................",
    ],
  },
  globe: {
    palette: { b: "#5aa9e6", w: "#bfe0f5" },
    rows: [
      "................",
      "................",
      ".....bbbbbb.....",
      "...bbbwwbbbbb...",
      "..bbbwwbbbbbbb..",
      "..bbwwbbbbbbbb..",
      ".wwwwwwwwwwwwww.",
      ".wwwwwwwwwwwwww.",
      "..bbwwbbbbbbbb..",
      "..bbbwwbbbbbbb..",
      "...bbbwwbbbbb...",
      ".....bbbbbb.....",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  code: {
    palette: { c: "#63e0be" },
    rows: [
      "................",
      "................",
      "....cc.....cc...",
      "...cc.......cc..",
      "..cc....c....cc.",
      "...cc..c....cc..",
      "....ccc....cc...",
      "......c.........",
      ".....c..........",
      "................",
      "................",
      "................",
      "................",
      "................",
      "................",
      "................",
    ],
  },
  warn: {
    palette: { y: "#e0a03c", d: "#4a3208" },
    rows: [
      "................",
      ".......yy.......",
      "......yyyy......",
      "......yyyy......",
      ".....yyddyy.....",
      ".....yyddyy.....",
      "....yyyddyyy....",
      "....yyyddyyy....",
      "...yyyyddyyyy...",
      "...yyyyddyyyy...",
      "..yyyyyyyyyyyy..",
      "..yyyyyddyyyyy..",
      ".yyyyyyyyyyyyyy.",
      ".yyyyyyyyyyyyyy.",
      "................",
      "................",
    ],
  },
};

let iconCache: Map<string, HTMLCanvasElement> | null = null;

function buildIcon(art: IconArt): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 16;
  const g = canvas.getContext("2d")!;
  const filled: boolean[][] = [];
  for (let y = 0; y < 16; y++) {
    filled.push(new Array(16).fill(false));
    const row = art.rows[y] ?? "";
    for (let x = 0; x < 16; x++) {
      const ch = row[x] ?? ".";
      const color = art.palette[ch];
      if (color) {
        g.fillStyle = color;
        g.fillRect(x, y, 1, 1);
        filled[y][x] = true;
      }
    }
  }
  // 1px dark outline around the silhouette.
  g.fillStyle = ICON_OUTLINE;
  for (let y = 0; y < 16; y++) {
    for (let x = 0; x < 16; x++) {
      if (filled[y][x]) continue;
      const near =
        (x > 0 && filled[y][x - 1]) ||
        (x < 15 && filled[y][x + 1]) ||
        (y > 0 && filled[y - 1][x]) ||
        (y < 15 && filled[y + 1][x]);
      if (near) g.fillRect(x, y, 1, 1);
    }
  }
  return canvas;
}

function getIcon(name: string): HTMLCanvasElement | null {
  if (!iconCache) {
    iconCache = new Map();
    for (const [key, art] of Object.entries(ICON_ART)) {
      iconCache.set(key, buildIcon(art));
    }
  }
  return iconCache.get(name) ?? iconCache.get("think") ?? null;
}

// ---------------------------------------------------------------------------
// Sparklines
// ---------------------------------------------------------------------------

function sparkPoints(
  series: Array<[string, number]> | undefined
): number[] | null {
  if (!series || series.length < 2) return null;
  return series.map(([, v]) => v);
}

function drawSparkline(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  points: number[],
  color: string,
  lineWidth: number,
  glow: number
): void {
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  ctx.save();
  if (glow > 0) {
    ctx.shadowColor = color;
    ctx.shadowBlur = glow;
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineJoin = "round";
  ctx.beginPath();
  points.forEach((v, i) => {
    const px = x + (i / (points.length - 1)) * w;
    const py = y + h - ((v - min) / span) * h;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Pixel bubble plaque
// ---------------------------------------------------------------------------

function drawBubblePlaque(
  ctx: CanvasRenderingContext2D,
  cx: number,
  topY: number,
  size: number,
  iconName: string,
  zoom: number,
  alpha: number
): void {
  const border = Math.max(1, Math.round(zoom * 0.7));
  const corner = Math.max(1, Math.round(zoom * 0.7));
  const tailW = Math.max(2, Math.round(zoom * 1.4));
  const tailH = Math.max(2, Math.round(zoom * 1.2));
  const x = Math.round(cx - size / 2);
  const y = Math.round(topY);

  ctx.save();
  ctx.globalAlpha = alpha;

  // Border with pixel-cut corners (three stacked rects).
  ctx.fillStyle = "#1c1724";
  ctx.fillRect(x + corner, y, size - corner * 2, size);
  ctx.fillRect(x, y + corner, size, size - corner * 2);
  // Tail.
  ctx.fillRect(cx - Math.floor(tailW / 2), y + size - 1, tailW, tailH);

  // Face.
  ctx.fillStyle = "#f2f5f9";
  ctx.fillRect(x + border + Math.max(0, corner - border), y + border, size - border * 2 - Math.max(0, corner - border) * 2, size - border * 2);
  ctx.fillRect(x + border, y + corner, size - border * 2, size - corner * 2);
  ctx.fillRect(cx - Math.floor(tailW / 2) + 1, y + size - 1, Math.max(1, tailW - 2), Math.max(1, tailH - 2));

  // Icon.
  const icon = getIcon(iconName);
  if (icon) {
    const pad = border + Math.max(1, Math.round(zoom * 0.6));
    const iw = size - pad * 2;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(icon, 0, 0, 16, 16, x + pad, y + pad, iw, iw);
  }
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------------

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
  showGrid: boolean,
  runContext: RunContext | null = null,
  showSparklines = true
): { offsetX: number; offsetY: number } {
  ctx.clearRect(0, 0, canvasWidth, canvasHeight);
  ctx.fillStyle = "#080b10";
  ctx.fillRect(0, 0, canvasWidth, canvasHeight);
  ctx.imageSmoothingEnabled = false;

  const s = TILE_SIZE * zoom;
  const mapW = cols * s;
  const mapH = rows * s;
  const offsetX = Math.floor((canvasWidth - mapW) / 2) + Math.round(panX);
  const offsetY = Math.floor((canvasHeight - mapH) / 2) + Math.round(panY);

  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.75)";
  ctx.shadowBlur = Math.max(18, s * 0.8);
  ctx.fillStyle = "#101018";
  ctx.fillRect(offsetX, offsetY, mapW, mapH);
  ctx.restore();

  // Baked tile layer (rebuilt only when the layout actually changes).
  const layerKey = `${cols}x${rows}:${tilesChecksum(tiles)}`;
  if (!tileLayer || tileLayerKey !== layerKey) {
    tileLayer = buildTileLayer(tiles, cols, rows);
    tileLayerKey = layerKey;
  }
  ctx.drawImage(tileLayer, offsetX, offsetY, mapW, mapH);

  // Zone labels (runtime so they stay crisp at any zoom).
  const zoneLabels = [
    { label: "研究工位", col: 1.35, row: 1.45 },
    { label: "策略会议室", col: 1.35, row: 7.3 },
    { label: "风控与执行", col: 9.75, row: 7.3 },
  ];
  ctx.fillStyle = "rgba(225,236,246,.34)";
  ctx.font = `bold ${Math.max(7, Math.round(zoom * 2.6))}px "Microsoft YaHei", sans-serif`;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  for (const z of zoneLabels) {
    ctx.fillText(z.label, offsetX + z.col * s + zoom * 3, offsetY + z.row * s + zoom * 2);
  }

  const glow = ctx.createRadialGradient(
    offsetX + mapW * 0.48,
    offsetY + mapH * 0.38,
    0,
    offsetX + mapW * 0.48,
    offsetY + mapH * 0.38,
    mapW * 0.55,
  );
  glow.addColorStop(0, "rgba(255,192,105,.05)");
  glow.addColorStop(1, "rgba(5,8,12,.20)");
  ctx.fillStyle = glow;
  ctx.fillRect(offsetX, offsetY, mapW, mapH);

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

  for (const f of furniture) {
    const img = furnitureImages.get(f.type);
    if (!img || !img.complete || img.naturalWidth === 0) continue;
    const fx = offsetX + f.col * s;
    const fy = offsetY + f.row * s;
    const fw = img.naturalWidth * zoom;
    const fh = img.naturalHeight * zoom;
    const zY = f.type.includes("Chair")
      ? f.row * TILE_SIZE + 4
      : f.row * TILE_SIZE + img.naturalHeight;

    if (f.mirrored) {
      drawables.push({
        zY,
        draw: (c) => {
          c.save();
          c.shadowColor = "rgba(0,0,0,.45)";
          c.shadowBlur = zoom * 2;
          c.shadowOffsetY = zoom * 1.5;
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
          c.save();
          c.shadowColor = "rgba(0,0,0,.45)";
          c.shadowBlur = zoom * 2;
          c.shadowOffsetY = zoom * 1.5;
          c.drawImage(img, fx, fy, fw, fh);
          c.restore();
        },
      });
    }
  }

  // Characters (32x32 frames from the regenerated spritesheet)
  if (characterSheet) {
    for (const ch of characters) {
      const frame = getSpriteFrame(ch);
      const drawSize = CHARACTER_DRAW_SIZE * zoom;
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
  } else {
    const palettes = [
      ["#f2c49b", "#315c78", "#d9a441"],
      ["#d7a47e", "#6b4f84", "#58a486"],
      ["#8f5f43", "#9d493f", "#d4c55d"],
      ["#f0c6a5", "#3f6c5a", "#b5637a"],
    ];
    for (const ch of characters) {
      const drawSize = CHARACTER_DRAW_SIZE * zoom;
      const drawX = Math.round(offsetX + ch.x * zoom - drawSize / 2);
      const drawY = Math.round(offsetY + ch.y * zoom - drawSize + s / 2);
      const zY = ch.y + TILE_SIZE / 2;
      const [skin, jacket, accent] = palettes[ch.palette % palettes.length];
      drawables.push({
        zY,
        draw: (c) => {
          const unit = Math.max(2, Math.round(zoom * 2));
          c.fillStyle = "rgba(0,0,0,0.22)";
          c.fillRect(drawX + unit * 3, drawY + unit * 13, unit * 10, unit * 2);
          c.fillStyle = accent;
          c.fillRect(drawX + unit * 4, drawY + unit, unit * 8, unit * 4);
          c.fillStyle = skin;
          c.fillRect(drawX + unit * 5, drawY + unit * 4, unit * 6, unit * 5);
          c.fillStyle = jacket;
          c.fillRect(drawX + unit * 3, drawY + unit * 9, unit * 10, unit * 5);
          c.fillStyle = "#24303a";
          c.fillRect(drawX + unit * 4, drawY + unit * 14, unit * 3, unit * 2);
          c.fillRect(drawX + unit * 9, drawY + unit * 14, unit * 3, unit * 2);
        },
      });
    }
  }

  drawables.sort((a, b) => a.zY - b.zY);
  for (const d of drawables) {
    d.draw(ctx);
  }

  const runActive =
    runContext !== null &&
    runContext.status !== "idle" &&
    runContext.agents.length > 0;

  // Live equity screen on the Wall-Graph (north wall).
  if (runActive && runContext) {
    const graph = furniture.find((f) => f.type === "Wall-Graph");
    if (graph) {
      const gx = offsetX + graph.col * s;
      const gy = offsetY + graph.row * s;
      const sx = gx + 3 * zoom;
      const sy = gy + 3 * zoom;
      const sw = 32 * zoom - 6 * zoom;
      const sh = 20 * zoom - 7 * zoom;
      ctx.fillStyle = "rgba(6,10,16,0.94)";
      ctx.fillRect(sx, sy, sw, sh);
      ctx.fillStyle = "rgba(120,160,200,0.10)";
      ctx.fillRect(sx, sy + sh / 3, sw, Math.max(1, zoom * 0.3));
      ctx.fillRect(sx, sy + (sh * 2) / 3, sw, Math.max(1, zoom * 0.3));

      // Shared scale across agents keeps the comparison honest.
      let min = Infinity;
      let max = -Infinity;
      const seriesList: Array<{ color: string; points: number[] }> = [];
      for (const agent of runContext.agents) {
        const points = sparkPoints(runContext.equity[agent.id]);
        if (!points) continue;
        seriesList.push({ color: agent.color, points });
        for (const v of points) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
      if (seriesList.length > 0 && min < Infinity) {
        const span = max - min || 1;
        const lw = Math.max(1, zoom * 0.5);
        for (const series of seriesList) {
          const normalized = series.points.map(
            (v) => ((v - min) / span) * 100 + 1000
          );
          drawSparkline(
            ctx,
            sx + zoom,
            sy + zoom * 0.8,
            sw - zoom * 2,
            sh - zoom * 1.6,
            normalized,
            series.color,
            lw,
            zoom * 1.6
          );
        }
      }
      // Screen sheen.
      const sheen = ctx.createLinearGradient(sx, sy, sx, sy + sh);
      sheen.addColorStop(0, "rgba(160,200,240,0.10)");
      sheen.addColorStop(0.4, "rgba(160,200,240,0.02)");
      sheen.addColorStop(1, "rgba(0,0,0,0.10)");
      ctx.fillStyle = sheen;
      ctx.fillRect(sx, sy, sw, sh);
    }
  }

  // Overlay pass: name tags + sparklines + action bubbles.
  for (const ch of characters) {
    const drawSize = CHARACTER_DRAW_SIZE * zoom;
    const drawX = Math.round(offsetX + ch.x * zoom - drawSize / 2);
    const drawY = Math.round(offsetY + ch.y * zoom - drawSize + s / 2);
    const centerX = drawX + drawSize / 2;

    // Name tag
    const fontSize = Math.max(8, Math.round(zoom * 3.2));
    ctx.font = `bold ${fontSize}px "Courier New", monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const nameY = drawY + drawSize + 2;
    ctx.fillStyle = "rgba(6,10,15,0.82)";
    const nameWidth = ctx.measureText(ch.name).width;
    ctx.fillRect(centerX - nameWidth / 2 - 4, nameY - 2, nameWidth + 8, fontSize + 4);
    ctx.fillStyle = ch.isActive ? "#63e8ad" : "#e9f0f5";
    ctx.fillText(ch.name, centerX, nameY);

    // Mini equity sparkline above the name tag.
    if (showSparklines && runActive && runContext) {
      const agent = runContext.agents.find((a) => a.id === ch.id);
      const points = agent ? sparkPoints(runContext.equity[agent.id]) : null;
      if (agent && points) {
        const sw = Math.max(18, zoom * 10);
        const sh = Math.max(5, zoom * 3);
        const sx = centerX - sw / 2;
        const sy = nameY - sh - 4;
        ctx.fillStyle = "rgba(6,10,15,0.78)";
        ctx.fillRect(sx - 2, sy - 2, sw + 4, sh + 4);
        ctx.fillStyle = "rgba(255,255,255,0.08)";
        ctx.fillRect(sx - 2, sy - 2, sw + 4, 1);
        drawSparkline(ctx, sx, sy, sw, sh, points, agent.color, Math.max(1, zoom * 0.4), 0);
      }
    }

    // Action bubble (queue head) as a pixel plaque with a crisp icon.
    if (ch.bubble) {
      const bubbleProgress = Math.min(ch.bubble.timer / 0.15, 1);
      const bubbleFade = ch.bubble.timer > ch.bubble.duration - 0.4
        ? (ch.bubble.duration - ch.bubble.timer) / 0.4
        : 1;
      const bubbleScale = bubbleProgress * bubbleFade;
      if (bubbleScale > 0) {
        const plaqueSize = Math.round(zoom * 7 * bubbleScale);
        if (plaqueSize >= 8) {
          const bubbleY = drawY - plaqueSize - Math.max(2, zoom * 1.4);
          drawBubblePlaque(ctx, centerX, bubbleY, plaqueSize, ch.bubble.icon, zoom, bubbleFade);
        }
      }
    }
  }

  // Ticker strip across the top of the map.
  if (runActive && runContext) {
    const barH = Math.max(13, Math.round(zoom * 6));
    ctx.fillStyle = "rgba(7,10,15,0.88)";
    ctx.fillRect(offsetX, offsetY, mapW, barH);
    ctx.fillStyle = "rgba(255,255,255,0.09)";
    ctx.fillRect(offsetX, offsetY + barH - 1, mapW, 1);

    const fontSize = Math.max(7, Math.round(zoom * 2.7));
    ctx.font = `bold ${fontSize}px "Courier New", "Microsoft YaHei", monospace`;
    ctx.textBaseline = "middle";
    const textY = offsetY + barH / 2 + 0.5;
    const pad = zoom * 2;

    // Status dot.
    const statusColor =
      runContext.status === "running"
        ? "#43c580"
        : runContext.status === "done"
          ? "#58a6d9"
          : runContext.status === "failed"
            ? "#e06060"
            : "#e0a03c";
    ctx.fillStyle = statusColor;
    const dotR = Math.max(1.5, zoom * 0.9);
    ctx.beginPath();
    ctx.arc(offsetX + pad + dotR, textY, dotR, 0, Math.PI * 2);
    ctx.fill();

    ctx.textAlign = "left";
    ctx.fillStyle = "#d7e3ee";
    const dateText = runContext.date ?? "--------";
    const dayText = runContext.totalDays > 0
      ? `第 ${runContext.dayIndex + 1}/${runContext.totalDays} 天`
      : "";
    ctx.fillText(`${dateText} · ${dayText}`, offsetX + pad + dotR * 2 + zoom, textY);

    // Right-aligned per-agent returns.
    ctx.textAlign = "right";
    let rightX = offsetX + mapW - pad;
    for (let i = runContext.agents.length - 1; i >= 0; i--) {
      const agent = runContext.agents[i];
      const points = sparkPoints(runContext.equity[agent.id]);
      let pct: number | null = null;
      if (points && points.length >= 2) {
        const first = points[0];
        const last = points[points.length - 1];
        if (first !== 0) pct = ((last - first) / first) * 100;
      }
      const text = pct === null
        ? agent.name
        : `${agent.name} ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
      ctx.fillStyle = pct !== null && pct < 0 ? "#e06060" : agent.color;
      ctx.fillText(text, rightX, textY);
      rightX -= ctx.measureText(text).width + zoom * 3;
    }
  }

  return { offsetX, offsetY };
}
