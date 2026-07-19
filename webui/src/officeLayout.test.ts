import { describe, expect, it } from "vitest";
import {
  createDefaultOfficeLayout,
  FOOTPRINTS,
} from "@office/layout/defaultLayout";
import { findPath } from "@office/layout/pathfinding";
import { TileType, type PlacedFurniture } from "@office/types";

const RESEARCH_DESK_CHAIR_PAIRS = ["d1/c1", "d2/c2", "d3/c3", "d4/c4"];

function footprintBox(item: PlacedFurniture) {
  // Non-blocking items (chairs use [0, 0]) still occupy at least their own
  // tile visually, so overlap detection treats every item as >= 1x1.
  const [w, h] = FOOTPRINTS[item.type] ?? [0, 0];
  const width = Math.max(w, 1);
  const height = Math.max(h, 1);
  return { col0: item.col, row0: item.row, col1: item.col + width - 1, row1: item.row + height - 1 };
}

function boxesOverlap(
  a: { col0: number; row0: number; col1: number; row1: number },
  b: { col0: number; row0: number; col1: number; row1: number }
) {
  return a.col0 <= b.col1 && b.col0 <= a.col1 && a.row0 <= b.row1 && b.row0 <= a.row1;
}

describe("default pixel office layout (4-agent floor)", () => {
  it("defines a footprint for every furniture type placed in the layout", () => {
    const layout = createDefaultOfficeLayout();
    const types = new Set(layout.furniture.map((item) => item.type));
    for (const type of types) {
      expect(FOOTPRINTS).toHaveProperty(type);
    }
  });

  it("provides at least 4 research desk+chair pairs with adjacent, walkable seats", () => {
    const layout = createDefaultOfficeLayout();
    let pairCount = 0;
    for (const pair of RESEARCH_DESK_CHAIR_PAIRS) {
      const [deskUid, chairUid] = pair.split("/");
      const desk = layout.furniture.find((item) => item.uid === deskUid);
      const chair = layout.furniture.find((item) => item.uid === chairUid);
      expect(desk).toBeDefined();
      expect(chair).toBeDefined();
      if (!desk || !chair) continue;

      // Chair sits directly below-right of its desk, matching the seat
      // convention used by buildSeats()/updateCharacter() (facing UP).
      expect(chair.col).toBe(desk.col + 1);
      expect(chair.row).toBe(desk.row + 2);

      expect(layout.tiles[desk.row * layout.cols + desk.col]).toBe(TileType.BLOCKED);
      expect(layout.tiles[chair.row * layout.cols + chair.col]).toBe(TileType.FLOOR);
      pairCount += 1;
    }
    expect(pairCount).toBeGreaterThanOrEqual(4);
  });

  it("keeps every research seat reachable from the central aisle via pathfinding", () => {
    const layout = createDefaultOfficeLayout();
    const aisleRow = 6;
    const startCol = 1;
    expect(layout.tiles[aisleRow * layout.cols + startCol]).toBe(TileType.FLOOR);

    for (const chairUid of ["c1", "c2", "c3", "c4"]) {
      const chair = layout.furniture.find((item) => item.uid === chairUid)!;
      const path = findPath(startCol, aisleRow, chair.col, chair.row, layout.tiles, layout.cols, layout.rows);
      expect(path.length).toBeGreaterThan(0);
      expect(path[path.length - 1]).toEqual({ col: chair.col, row: chair.row });
    }
  });

  it("leaves a continuous central aisle across the full width", () => {
    const layout = createDefaultOfficeLayout();
    const aisleRow = 6;
    for (let col = 1; col < layout.cols - 1; col += 1) {
      expect(layout.tiles[aisleRow * layout.cols + col]).toBe(TileType.FLOOR);
    }
  });

  it("has a strategy meeting room area (round table) and a risk/execution desk area", () => {
    const layout = createDefaultOfficeLayout();
    const table = layout.furniture.find((item) => item.type === "Big-Round-Table");
    const riskDesk = layout.furniture.find((item) => item.type === "Boss-Desk");
    expect(table).toBeDefined();
    expect(riskDesk).toBeDefined();
    // Meeting room sits west of the aisle midpoint, risk desk sits east of it.
    expect(table!.col).toBeLessThan(layout.cols / 2);
    expect(riskDesk!.col).toBeGreaterThanOrEqual(layout.cols / 2);
  });

  it("has no overlapping furniture footprints", () => {
    const layout = createDefaultOfficeLayout();
    const boxes = layout.furniture.map(footprintBox);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(boxesOverlap(boxes[i], boxes[j])).toBe(false);
      }
    }
  });

  it("keeps every placed furniture anchor within the interior (non-wall) bounds", () => {
    const layout = createDefaultOfficeLayout();
    for (const item of layout.furniture) {
      const [w, h] = FOOTPRINTS[item.type] ?? [0, 0];
      expect(item.col).toBeGreaterThanOrEqual(1);
      expect(item.row).toBeGreaterThanOrEqual(1);
      expect(item.col + Math.max(w, 1) - 1).toBeLessThanOrEqual(layout.cols - 2);
      expect(item.row + Math.max(h, 1) - 1).toBeLessThanOrEqual(layout.rows - 2);
    }
  });

  it("keeps furniture anchors unique", () => {
    const layout = createDefaultOfficeLayout();
    const anchors = layout.furniture.map((item) => `${item.col},${item.row}`);
    expect(new Set(anchors).size).toBe(anchors.length);
  });
});
