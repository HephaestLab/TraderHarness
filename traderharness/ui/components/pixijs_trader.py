"""Canvas 2D pixel-art trader desk-pet scene.

Top-down room with a character that walks between stations and performs
actions based on backtest state. Pure Canvas 2D rendering with BFS pathfinding.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components

ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "pixel-art"


def _load_b64(filename: str) -> str:
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


_SCENE_JS = r"""
<div id="pet-wrap" style="width:100%;height:__HEIGHT__px;overflow:hidden;border:2px solid #533483;
  border-radius:6px;position:relative;background:#1a1a2e;">
  <canvas id="pet-canvas" style="width:100%;height:100%;display:block;image-rendering:pixelated;"></canvas>
</div>
<script>
(function() {
  const wrap = document.getElementById('pet-wrap');
  const canvas = document.getElementById('pet-canvas');
  const ctx = canvas.getContext('2d');
  const W = wrap.clientWidth;
  const H = __HEIGHT__;
  canvas.width = W;
  canvas.height = H;
  ctx.imageSmoothingEnabled = false;

  const STATE = '__STATE__';

  // --- Asset loading ---
  const bgImg = new Image();
  bgImg.src = 'data:image/png;base64,' + document.getElementById('_room_b64').textContent;

  const charImg = new Image();
  charImg.src = 'data:image/png;base64,' + document.getElementById('_char_b64').textContent;

  const bubImg = new Image();
  bubImg.src = 'data:image/png;base64,' + document.getElementById('_bub_b64').textContent;

  // --- Grid & Scene Config ---
  // The spritesheet is 1024x1024 with 8 cols x 7 rows => each cell ~128x146
  // But character sprites are designed as 32x32 logical cells
  // Actual: 1024/8 = 128px per cell in the image
  const CHAR_COLS = 8;
  const CHAR_ROWS = 7;
  let charFrameW = 0;
  let charFrameH = 0;

  // Scene grid (logical 30x20 tiles, each tile = W/30 pixels on screen)
  const GRID_COLS = 30;
  const GRID_ROWS = 20;
  const TILE_W = W / GRID_COLS;
  const TILE_H = H / GRID_ROWS;

  // Station positions (grid coords) — mapped to the room layout
  const STATIONS = {
    desk:       { col: 7,  row: 10, action: 'sit_type',    dir: 'up' },
    coffee:     { col: 19, row: 8,  action: 'stand_coffee', dir: 'left' },
    whiteboard: { col: 4,  row: 3,  action: 'stand_write',  dir: 'up' },
    sofa:       { col: 23, row: 14, action: 'lie_sofa',     dir: 'left' },
    server:     { col: 27, row: 6,  action: 'stand_server', dir: 'up' },
    bookshelf:  { col: 14, row: 16, action: 'stand_read',   dir: 'down' },
    window:     { col: 20, row: 2,  action: 'stand_idle',   dir: 'up' },
    center:     { col: 15, row: 11, action: 'stand_idle',   dir: 'down' },
  };

  // Walkable area (simple rectangle minus furniture footprints)
  // 1 = walkable, 0 = blocked
  const walkGrid = [];
  for (let r = 0; r < GRID_ROWS; r++) {
    walkGrid[r] = [];
    for (let c = 0; c < GRID_COLS; c++) {
      // Walls: top 1 row, bottom 1 row, left 1 col, right 1 col
      if (r < 2 || r > 18 || c < 2 || c > 28) {
        walkGrid[r][c] = 0;
      } else {
        walkGrid[r][c] = 1;
      }
    }
  }
  // Block furniture areas
  function blockRect(c1, r1, c2, r2) {
    for (let r = r1; r <= r2; r++)
      for (let c = c1; c <= c2; c++)
        if (r >= 0 && r < GRID_ROWS && c >= 0 && c < GRID_COLS)
          walkGrid[r][c] = 0;
  }
  blockRect(3, 6, 10, 9);   // desk area
  blockRect(18, 6, 21, 9);  // coffee station
  blockRect(2, 2, 6, 4);    // whiteboard
  blockRect(22, 12, 26, 16);// sofa
  blockRect(26, 3, 29, 9);  // server rack
  blockRect(11, 15, 18, 18);// bookshelf
  // Ensure station tiles are walkable
  Object.values(STATIONS).forEach(s => { walkGrid[s.row][s.col] = 1; });

  // --- BFS Pathfinding ---
  function findPath(startCol, startRow, endCol, endRow) {
    if (startCol === endCol && startRow === endRow) return [];
    const visited = new Set();
    const queue = [[{ col: startCol, row: startRow, path: [] }]];
    visited.add(startRow * GRID_COLS + startCol);

    const dirs = [[0,-1],[0,1],[-1,0],[1,0]];
    let front = [{ col: startCol, row: startRow, path: [] }];

    while (front.length > 0) {
      const next = [];
      for (const node of front) {
        for (const [dc, dr] of dirs) {
          const nc = node.col + dc;
          const nr = node.row + dr;
          const key = nr * GRID_COLS + nc;
          if (nc < 0 || nc >= GRID_COLS || nr < 0 || nr >= GRID_ROWS) continue;
          if (visited.has(key)) continue;
          if (walkGrid[nr][nc] === 0) continue;
          visited.add(key);
          const newPath = [...node.path, { col: nc, row: nr }];
          if (nc === endCol && nr === endRow) return newPath;
          next.push({ col: nc, row: nr, path: newPath });
        }
      }
      front = next;
    }
    return null; // no path
  }

  // --- Character State ---
  const character = {
    x: STATIONS.center.col * TILE_W + TILE_W / 2,
    y: STATIONS.center.row * TILE_H + TILE_H / 2,
    col: STATIONS.center.col,
    row: STATIONS.center.row,
    state: 'idle',    // idle, walking, action
    dir: 'down',      // up, down, left, right
    action: 'stand_idle',
    frame: 0,
    frameTimer: 0,
    path: [],
    pathIdx: 0,
    moveProgress: 0,
    targetStation: null,
    bubble: null,
    bubbleTimer: 0,
  };

  const WALK_SPEED = 2.5; // tiles per second
  const ANIM_SPEED = 0.15; // seconds per frame

  // --- Sprite row/col mapping ---
  // Row 0: walk_down(4) + walk_up(4)
  // Row 1: walk_left(4) + walk_right(4)
  // Row 2: sit_type(4) + sit_think(4)
  // Row 3: stand_coffee(4) + stand_write(4)
  // Row 4: lie_sofa(4) + stand_read(4)
  // Row 5: celebrate(4) + frustrated(4)
  // Row 6: stand_idle(2) + stand_window(2) + stand_server(4)

  function getSpriteFrame(action, dir, frame) {
    let row = 0, col = 0;
    if (action === 'walk') {
      if (dir === 'down')  { row = 0; col = frame % 4; }
      else if (dir === 'up') { row = 0; col = 4 + (frame % 4); }
      else if (dir === 'left') { row = 1; col = frame % 4; }
      else { row = 1; col = 4 + (frame % 4); }
    } else if (action === 'sit_type') {
      row = 2; col = frame % 4;
    } else if (action === 'sit_think') {
      row = 2; col = 4 + (frame % 4);
    } else if (action === 'stand_coffee') {
      row = 3; col = frame % 4;
    } else if (action === 'stand_write') {
      row = 3; col = 4 + (frame % 4);
    } else if (action === 'lie_sofa') {
      row = 4; col = frame % 4;
    } else if (action === 'stand_read') {
      row = 4; col = 4 + (frame % 4);
    } else if (action === 'celebrate') {
      row = 5; col = frame % 4;
    } else if (action === 'frustrated') {
      row = 5; col = 4 + (frame % 4);
    } else if (action === 'stand_server') {
      row = 6; col = 4 + (frame % 4);
    } else {
      // stand_idle
      row = 6; col = frame % 2;
    }
    return { row, col };
  }

  // --- Bubble sprite mapping ---
  // Row 0: speech, thought, !, music, zzz, heart, $, down-arrow
  function getBubbleCol(type) {
    const map = { thought: 1, alert: 2, music: 3, sleep: 4, heart: 5, profit: 6, loss: 7, coffee: 1 };
    return map[type] || 0;
  }

  // --- State → behavior mapping ---
  function getTargetStation(agentState) {
    switch (agentState) {
      case 'analyzing': return 'desk';
      case 'trading':   return 'desk';
      case 'waiting':   return Math.random() > 0.5 ? 'coffee' : 'window';
      case 'excited':   return 'center';
      case 'stressed':  return 'desk';
      case 'sleeping':  return 'sofa';
      case 'execute_code': return 'server';
      default:          return null; // idle wander
    }
  }

  function getActionForState(agentState, stationAction) {
    if (agentState === 'trading') return 'sit_type';
    if (agentState === 'analyzing') return 'sit_think';
    if (agentState === 'excited') return 'celebrate';
    if (agentState === 'stressed') return 'frustrated';
    if (agentState === 'sleeping') return 'lie_sofa';
    return stationAction;
  }

  function getBubbleForState(agentState) {
    switch (agentState) {
      case 'analyzing': return 'thought';
      case 'trading':   return 'alert';
      case 'excited':   return 'profit';
      case 'stressed':  return 'loss';
      case 'sleeping':  return 'sleep';
      case 'waiting':   return 'coffee';
      default:          return null;
    }
  }

  // --- Walk to station ---
  function walkTo(stationId) {
    const station = STATIONS[stationId];
    if (!station) return;
    const path = findPath(character.col, character.row, station.col, station.row);
    if (path && path.length > 0) {
      character.state = 'walking';
      character.path = path;
      character.pathIdx = 0;
      character.moveProgress = 0;
      character.targetStation = stationId;
    } else {
      // Can't reach, just teleport
      character.col = station.col;
      character.row = station.row;
      character.x = station.col * TILE_W + TILE_W / 2;
      character.y = station.row * TILE_H + TILE_H / 2;
      arriveAtStation(stationId);
    }
  }

  function arriveAtStation(stationId) {
    const station = STATIONS[stationId];
    character.state = 'action';
    character.dir = station.dir;
    character.action = getActionForState(STATE, station.action);
    character.frame = 0;
    character.frameTimer = 0;
    const bubble = getBubbleForState(STATE);
    if (bubble) {
      character.bubble = bubble;
      character.bubbleTimer = 6; // show for 6 seconds
    }
  }

  // --- Idle wander logic ---
  const IDLE_STATIONS = ['coffee', 'bookshelf', 'window', 'center', 'desk'];
  let wanderTimer = 2 + Math.random() * 3;
  let initialMove = true;

  // --- Game Loop ---
  let lastTime = performance.now();
  let loaded = 0;
  const totalAssets = 3;

  function onAssetLoad() {
    loaded++;
    if (loaded >= totalAssets) {
      charFrameW = charImg.width / CHAR_COLS;
      charFrameH = charImg.height / CHAR_ROWS;

      // Start: walk to target based on state
      const targetId = getTargetStation(STATE);
      if (targetId) {
        walkTo(targetId);
      } else {
        character.state = 'action';
        character.action = 'stand_idle';
      }

      requestAnimationFrame(gameLoop);
    }
  }

  bgImg.onload = onAssetLoad;
  charImg.onload = onAssetLoad;
  bubImg.onload = onAssetLoad;

  function gameLoop(now) {
    const dt = Math.min((now - lastTime) / 1000, 0.1);
    lastTime = now;

    update(dt);
    render();
    requestAnimationFrame(gameLoop);
  }

  function update(dt) {
    character.frameTimer += dt;
    const animSpeed = character.state === 'walking' ? 0.12 :
                      (character.action === 'sit_type' ? 0.2 : 0.3);

    if (character.frameTimer >= animSpeed) {
      character.frameTimer = 0;
      character.frame++;
    }

    // Bubble timer
    if (character.bubbleTimer > 0) {
      character.bubbleTimer -= dt;
      if (character.bubbleTimer <= 0) character.bubble = null;
    }

    if (character.state === 'walking') {
      updateWalking(dt);
    } else if (character.state === 'idle' || (character.state === 'action' && STATE === 'idle')) {
      wanderTimer -= dt;
      if (wanderTimer <= 0) {
        const randStation = IDLE_STATIONS[Math.floor(Math.random() * IDLE_STATIONS.length)];
        walkTo(randStation);
        wanderTimer = 5 + Math.random() * 8;
      }
    }
  }

  function updateWalking(dt) {
    if (character.pathIdx >= character.path.length) {
      // Arrived
      if (character.targetStation) {
        arriveAtStation(character.targetStation);
      } else {
        character.state = 'action';
        character.action = 'stand_idle';
      }
      return;
    }

    const target = character.path[character.pathIdx];
    const targetX = target.col * TILE_W + TILE_W / 2;
    const targetY = target.row * TILE_H + TILE_H / 2;

    // Direction
    const dx = targetX - character.x;
    const dy = targetY - character.y;
    if (Math.abs(dx) > Math.abs(dy)) {
      character.dir = dx > 0 ? 'right' : 'left';
    } else {
      character.dir = dy > 0 ? 'down' : 'up';
    }

    character.moveProgress += WALK_SPEED * dt;
    if (character.moveProgress >= 1) {
      character.x = targetX;
      character.y = targetY;
      character.col = target.col;
      character.row = target.row;
      character.pathIdx++;
      character.moveProgress = 0;
    } else {
      const prevX = character.col * TILE_W + TILE_W / 2;
      const prevY = character.row * TILE_H + TILE_H / 2;
      character.x = prevX + (targetX - prevX) * character.moveProgress;
      character.y = prevY + (targetY - prevY) * character.moveProgress;
    }
  }

  function render() {
    ctx.clearRect(0, 0, W, H);

    // Background
    if (bgImg.complete) {
      ctx.drawImage(bgImg, 0, 0, W, H);
    }

    // Character
    if (charImg.complete && charFrameW > 0) {
      const spriteAction = character.state === 'walking' ? 'walk' : character.action;
      const { row, col } = getSpriteFrame(spriteAction, character.dir, character.frame);

      const sx = col * charFrameW;
      const sy = row * charFrameH;

      // Draw character scaled to about 4 tiles tall for visibility
      const drawH = TILE_H * 4.2;
      const drawW = (charFrameW / charFrameH) * drawH;

      ctx.drawImage(
        charImg,
        sx, sy, charFrameW, charFrameH,
        character.x - drawW / 2,
        character.y - drawH * 0.75,
        drawW, drawH
      );
    }

    // Bubble
    if (character.bubble && bubImg.complete) {
      const bubCol = getBubbleCol(character.bubble);
      const bubSize = bubImg.width / 8; // 8 cols in bubble sheet
      const sx = bubCol * bubSize;
      const sy = 0;
      const drawSize = TILE_W * 2;
      const bobY = Math.sin(performance.now() * 0.003) * 2;

      ctx.drawImage(
        bubImg,
        sx, sy, bubSize, bubSize,
        character.x - drawSize / 2,
        character.y - TILE_H * 4.8 + bobY,
        drawSize, drawSize
      );
    }

    // HUD
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(4, H - 22, 130, 18);
    ctx.fillStyle = getStateColor(STATE);
    ctx.font = '10px "Press Start 2P", monospace';
    ctx.fillText(getStateLabel(STATE), 8, H - 9);
  }

  function getStateColor(s) {
    const colors = {
      idle: '#7a7a9e', analyzing: '#00d2d3', trading: '#f9ca24',
      excited: '#10b981', stressed: '#e94560', waiting: '#7a7a9e', sleeping: '#7ec8e3',
      execute_code: '#f9ca24'
    };
    return colors[s] || '#7a7a9e';
  }
  function getStateLabel(s) {
    const labels = {
      idle: 'STANDBY', analyzing: 'ANALYZING', trading: 'TRADING',
      excited: 'PROFIT!', stressed: 'DRAWDOWN', waiting: 'WAITING',
      sleeping: 'ZZZ', execute_code: 'CODING'
    };
    return labels[s] || 'STANDBY';
  }
})();
</script>
"""


def render_trader_scene(state: str = "idle", height: int = 320) -> None:
    """Render the desk-pet trading room scene.

    States: idle, analyzing, trading, excited, stressed, waiting, sleeping, execute_code
    """
    room_b64 = _load_b64("scene_room.png")
    char_b64 = _load_b64("trader_char_clean.png")
    bub_b64 = _load_b64("ui_bubbles_clean.png")

    if not room_b64 or not char_b64:
        components.html(
            f'<div style="width:100%;height:{height}px;background:#1a1a2e;'
            f'border:2px solid #533483;display:flex;align-items:center;justify-content:center;'
            f'font-family:monospace;color:#7a7a9e;font-size:12px;">'
            f'Assets not found (need scene_room.png + trader_char_clean.png)</div>',
            height=height,
        )
        return

    js_html = _SCENE_JS.replace("__HEIGHT__", str(height)).replace("__STATE__", state)

    data_elements = (
        f'<script id="_room_b64" type="text/plain">{room_b64}</script>'
        f'<script id="_char_b64" type="text/plain">{char_b64}</script>'
        f'<script id="_bub_b64" type="text/plain">{bub_b64}</script>'
    )

    components.html(data_elements + js_html, height=height + 6, scrolling=False)


# Backward compat
def render_trader_animation(state: str = "idle", height: int = 320) -> None:
    render_trader_scene(state, height)
