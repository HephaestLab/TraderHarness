import { useEffect, useRef, useCallback } from "react";
import { startGameLoop } from "../engine/gameLoop";
import { renderFrame } from "../engine/renderer";
import { update, type OfficeState } from "../engine/officeState";

interface Props {
  state: OfficeState;
  furnitureImages: Map<string, HTMLImageElement>;
  characterSheet: HTMLImageElement | null;
  showGrid: boolean;
  onTileClick?: (col: number, row: number) => void;
}

export function OfficeCanvas({
  state,
  furnitureImages,
  characterSheet,
  showGrid,
  onTileClick,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const isPanning = useRef(false);
  const lastMouse = useRef({ x: 0, y: 0 });

  const isEmbed = new URLSearchParams(window.location.search).has("embed");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resizeCanvas = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
        const s = stateRef.current;
        const zoomX = (parent.clientWidth - 24) / (s.cols * 16);
        const zoomY = (parent.clientHeight - 24) / (s.rows * 16);
        const fittedZoom = Math.max(1, Math.floor(Math.min(zoomX, zoomY) * 10) / 10);
        s.zoom = isEmbed ? fittedZoom : Math.min(s.zoom, fittedZoom);
      }
    };
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    const stopLoop = startGameLoop(canvas, {
      update: (dt) => {
        update(stateRef.current, dt);
      },
      render: (ctx) => {
        const s = stateRef.current;
        renderFrame(
          ctx,
          canvas.width,
          canvas.height,
          s.tiles,
          s.cols,
          s.rows,
          s.furniture,
          [...s.characters.values()],
          s.zoom,
          s.panX,
          s.panY,
          furnitureImages,
          characterSheet,
          showGrid,
          s.runContext,
          s.showSparklines
        );
      },
    });

    return () => {
      stopLoop();
      window.removeEventListener("resize", resizeCanvas);
    };
  }, [furnitureImages, characterSheet, showGrid]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.5 : 0.5;
    stateRef.current.zoom = Math.max(1, Math.min(8, stateRef.current.zoom + delta));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      isPanning.current = true;
      lastMouse.current = { x: e.clientX, y: e.clientY };
    }
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning.current) {
      const dx = e.clientX - lastMouse.current.x;
      const dy = e.clientY - lastMouse.current.y;
      stateRef.current.panX += dx;
      stateRef.current.panY += dy;
      lastMouse.current = { x: e.clientX, y: e.clientY };
    }
  }, []);

  const handleMouseUp = useCallback(() => {
    isPanning.current = false;
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!onTileClick) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const s = stateRef.current;
      const tileSize = s.zoom * 16;
      const mapW = s.cols * tileSize;
      const mapH = s.rows * tileSize;
      const offsetX = Math.floor((canvas.width - mapW) / 2) + Math.round(s.panX);
      const offsetY = Math.floor((canvas.height - mapH) / 2) + Math.round(s.panY);
      const mx = e.clientX - rect.left - offsetX;
      const my = e.clientY - rect.top - offsetY;
      const col = Math.floor(mx / tileSize);
      const row = Math.floor(my / tileSize);
      if (col >= 0 && col < s.cols && row >= 0 && row < s.rows) {
        onTileClick(col, row);
      }
    },
    [onTileClick]
  );

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", display: "block", cursor: "crosshair" }}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onClick={handleClick}
    />
  );
}
