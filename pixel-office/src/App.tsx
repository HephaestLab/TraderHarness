import { useState, useEffect, useRef, useCallback } from "react";
import { OfficeCanvas } from "./office/components/OfficeCanvas";
import {
  createDefaultState,
  loadLayout,
  saveLayout,
  addAgent,
  rebuildSeats,
  handleBacktestEvent,
  UndoStack,
  type OfficeState,
} from "./office/engine/officeState";
import { TileType, EditTool } from "./office/types";
import "./App.css";

const FURNITURE_CATALOG = [
  { type: "Desk", label: "Desk", category: "Work" },
  { type: "Desk-2", label: "Desk 2", category: "Work" },
  { type: "Boss-Desk", label: "Boss Desk", category: "Work" },
  { type: "Big-Round-Table", label: "Round Table", category: "Work" },
  { type: "Small-Table", label: "Small Table", category: "Work" },
  { type: "Chair", label: "Chair", category: "Seating" },
  { type: "Chair-2", label: "Chair 2", category: "Seating" },
  { type: "Boss-Chair", label: "Boss Chair", category: "Seating" },
  { type: "Big-Sofa", label: "Sofa (L)", category: "Seating" },
  { type: "Small-Sofa", label: "Sofa (S)", category: "Seating" },
  { type: "Bookshelf", label: "Bookshelf", category: "Storage" },
  { type: "Tall-Bookshelf", label: "Tall Bookshelf", category: "Storage" },
  { type: "Filing-Cabinet-Tall", label: "Cabinet Tall", category: "Storage" },
  { type: "Filing-Cabinet-Small", label: "Cabinet Small", category: "Storage" },
  { type: "Wide-Filing-Cabinet", label: "Cabinet Wide", category: "Storage" },
  { type: "Coffee-Machine", label: "Coffee Machine", category: "Appliance" },
  { type: "Vending-Machine", label: "Vending Machine", category: "Appliance" },
  { type: "Water-Dispenser", label: "Water Dispenser", category: "Appliance" },
  { type: "Big-Office-Printer", label: "Printer (L)", category: "Appliance" },
  { type: "Printer", label: "Printer", category: "Appliance" },
  { type: "Big-Plant", label: "Plant (L)", category: "Decor" },
  { type: "Small-Plant", label: "Plant (S)", category: "Decor" },
  { type: "Board", label: "Whiteboard", category: "Decor" },
  { type: "Wall-Graph", label: "Wall Graph", category: "Decor" },
  { type: "Wall-Note", label: "Wall Note", category: "Decor" },
  { type: "Wall-Note-2", label: "Wall Note 2", category: "Decor" },
  { type: "Wall-Clock", label: "Wall Clock", category: "Decor" },
  { type: "Bin", label: "Bin", category: "Decor" },
  { type: "Books", label: "Books", category: "Decor" },
  { type: "Folders", label: "Folders", category: "Decor" },
  { type: "Folders-2", label: "Folders 2", category: "Decor" },
  { type: "Papers", label: "Papers", category: "Decor" },
];

function App() {
  const isEmbed = new URLSearchParams(window.location.search).has("embed");

  const [state] = useState<OfficeState>(() => {
    const saved = localStorage.getItem("pixel-office-layout");
    if (saved) {
      try {
        const s = loadLayout(JSON.parse(saved));
        return s;
      } catch {
        /* ignore */
      }
    }
    return createDefaultState();
  });

  const [editTool, setEditTool] = useState<EditTool>(EditTool.SELECT);
  const [selectedFurniture, setSelectedFurniture] = useState<string>("Desk");
  const [showGrid, setShowGrid] = useState(true);
  const [furnitureImages, setFurnitureImages] = useState<Map<string, HTMLImageElement>>(new Map());
  const [characterSheet, setCharacterSheet] = useState<HTMLImageElement | null>(null);
  const [, forceRender] = useState(0);

  const stateRef = useRef(state);
  stateRef.current = state;
  const undoStack = useRef(new UndoStack());

  // Load assets
  useEffect(() => {
    const imgs = new Map<string, HTMLImageElement>();
    let loaded = 0;
    const types = FURNITURE_CATALOG.map((f) => f.type);
    const total = types.length;

    for (const name of types) {
      const img = new Image();
      img.src = `./assets/furniture/${name}.png`;
      img.onload = () => {
        imgs.set(name, img);
        loaded++;
        if (loaded === total) setFurnitureImages(new Map(imgs));
      };
      img.onerror = () => {
        loaded++;
        if (loaded === total) setFurnitureImages(new Map(imgs));
      };
    }

    const sheet = new Image();
    sheet.src = "./assets/characters/characters.png";
    sheet.onload = () => setCharacterSheet(sheet);
  }, []);

  // Add agents — embed mode listens for postMessage to add dynamically
  useEffect(() => {
    if (state.characters.size === 0) {
      if (isEmbed) {
        addAgent(state, "agent_0", "Trader", 0);
      } else {
        addAgent(state, "agent_0", "Trend Trader", 0);
        addAgent(state, "agent_1", "Value Investor", 1);
        addAgent(state, "agent_2", "News Hawk", 2);
      }
      forceRender((n) => n + 1);
    }
    undoStack.current.push(state);
  }, [state, isEmbed]);

  // Listen for postMessage events from parent (Streamlit iframe)
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "backtest_event") {
        handleBacktestEvent(stateRef.current, e.data.event);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          undoStack.current.redo(stateRef.current);
        } else {
          undoStack.current.undo(stateRef.current);
        }
        rebuildSeats(stateRef.current);
        forceRender((n) => n + 1);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const pushUndo = useCallback(() => {
    undoStack.current.push(stateRef.current);
  }, []);

  const handleTileClick = useCallback(
    (col: number, row: number) => {
      const s = stateRef.current;
      const idx = row * s.cols + col;

      switch (editTool) {
        case EditTool.FLOOR_PAINT:
          s.tiles[idx] = TileType.FLOOR;
          pushUndo();
          break;
        case EditTool.WALL_PAINT:
          s.tiles[idx] = TileType.WALL;
          pushUndo();
          break;
        case EditTool.ERASE:
          s.tiles[idx] = TileType.VOID;
          s.furniture = s.furniture.filter((f) => !(f.col === col && f.row === row));
          rebuildSeats(s);
          pushUndo();
          break;
        case EditTool.FURNITURE_PLACE: {
          const existing = s.furniture.find((f) => f.col === col && f.row === row);
          if (!existing && s.tiles[idx] !== TileType.WALL) {
            const uid = `f_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
            s.furniture.push({ uid, type: selectedFurniture, col, row });
            rebuildSeats(s);
            pushUndo();
          }
          break;
        }
        case EditTool.SELECT:
          break;
      }
      forceRender((n) => n + 1);
    },
    [editTool, selectedFurniture, pushUndo]
  );

  const handleSave = () => {
    const layout = saveLayout(state);
    const json = JSON.stringify(layout);
    localStorage.setItem("pixel-office-layout", json);
    // Also download as file for easy extraction
    const blob = new Blob([json], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "office-layout.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const handleReset = () => {
    localStorage.removeItem("pixel-office-layout");
    window.location.reload();
  };

  const handleResize = (dCols: number, dRows: number) => {
    const s = stateRef.current;
    const newCols = Math.max(6, Math.min(32, s.cols + dCols));
    const newRows = Math.max(6, Math.min(32, s.rows + dRows));
    if (newCols === s.cols && newRows === s.rows) return;

    const newTiles: number[] = [];
    for (let r = 0; r < newRows; r++) {
      for (let c = 0; c < newCols; c++) {
        if (r < s.rows && c < s.cols) {
          newTiles.push(s.tiles[r * s.cols + c]);
        } else if (r === 0 || r === newRows - 1 || c === 0 || c === newCols - 1) {
          newTiles.push(TileType.WALL);
        } else {
          newTiles.push(TileType.FLOOR);
        }
      }
    }
    s.cols = newCols;
    s.rows = newRows;
    s.tiles = newTiles;
    s.furniture = s.furniture.filter((f) => f.col < newCols && f.row < newRows);
    rebuildSeats(s);
    pushUndo();
    forceRender((n) => n + 1);
  };

  return (
    <div className="app">
      {!isEmbed && <div className="toolbar">
        <div className="tool-group">
          <button
            className={editTool === EditTool.SELECT ? "active" : ""}
            onClick={() => setEditTool(EditTool.SELECT)}
            title="Select (S)"
          >
            ◎
          </button>
          <button
            className={editTool === EditTool.FLOOR_PAINT ? "active" : ""}
            onClick={() => setEditTool(EditTool.FLOOR_PAINT)}
            title="Paint Floor (F)"
          >
            ▦
          </button>
          <button
            className={editTool === EditTool.WALL_PAINT ? "active" : ""}
            onClick={() => setEditTool(EditTool.WALL_PAINT)}
            title="Paint Wall (W)"
          >
            ▬
          </button>
          <button
            className={editTool === EditTool.FURNITURE_PLACE ? "active" : ""}
            onClick={() => setEditTool(EditTool.FURNITURE_PLACE)}
            title="Place Furniture (P)"
          >
            ⊞
          </button>
          <button
            className={editTool === EditTool.ERASE ? "active" : ""}
            onClick={() => setEditTool(EditTool.ERASE)}
            title="Erase (E)"
          >
            ✕
          </button>
        </div>

        <div className="tool-group">
          <label>
            <input
              type="checkbox"
              checked={showGrid}
              onChange={(e) => setShowGrid(e.target.checked)}
            />
            Grid
          </label>
        </div>

        <div className="tool-group">
          <button onClick={() => handleResize(-1, 0)} title="Shrink width">−W</button>
          <button onClick={() => handleResize(1, 0)} title="Expand width">+W</button>
          <button onClick={() => handleResize(0, -1)} title="Shrink height">−H</button>
          <button onClick={() => handleResize(0, 1)} title="Expand height">+H</button>
          <span className="size-label">{state.cols}×{state.rows}</span>
        </div>

        <div className="tool-group right">
          <button onClick={() => { undoStack.current.undo(stateRef.current); rebuildSeats(stateRef.current); forceRender(n => n+1); }} title="Undo (Ctrl+Z)">↩</button>
          <button onClick={() => { undoStack.current.redo(stateRef.current); rebuildSeats(stateRef.current); forceRender(n => n+1); }} title="Redo (Ctrl+Shift+Z)">↪</button>
          <button onClick={handleSave} title="Save Layout">Save</button>
          <button onClick={handleReset} title="Reset to Default">Reset</button>
        </div>
      </div>}

      {!isEmbed && editTool === EditTool.FURNITURE_PLACE && (
        <div className="furniture-panel">
          {FURNITURE_CATALOG.map((f) => (
            <button
              key={f.type}
              className={`furniture-item ${selectedFurniture === f.type ? "active" : ""}`}
              onClick={() => setSelectedFurniture(f.type)}
              title={f.label}
            >
              <img
                src={`./assets/furniture/${f.type}.png`}
                alt={f.label}
                style={{ imageRendering: "pixelated" }}
              />
              <span>{f.label}</span>
            </button>
          ))}
        </div>
      )}

      <div className="canvas-container">
        <OfficeCanvas
          state={state}
          furnitureImages={furnitureImages}
          characterSheet={characterSheet}
          showGrid={showGrid}
          onTileClick={handleTileClick}
        />
      </div>
    </div>
  );
}

export default App;
