import { TileType, type OfficeLayout, type PlacedFurniture } from "../types";

/**
 * Footprint (in tiles) that each furniture type blocks for pathfinding.
 * Every furniture type used in the default layout (and by the editor's
 * FURNITURE catalog in webui/src/components/OfficeFloor.tsx) has an entry
 * here — chairs intentionally use [0, 0] since a character must be able to
 * walk onto the chair tile to sit down.
 */
export const FOOTPRINTS: Record<string, [number, number]> = {
  "Desk-2": [2, 2],
  "Chair-2": [0, 0],
  "Small-Plant": [1, 1],
  "Big-Round-Table": [2, 2],
  "Boss-Desk": [2, 2],
  "Boss-Chair": [0, 0],
  "Big-Office-Printer": [1, 2],
  "Water-Dispenser": [1, 2],
  "Filing-Cabinet-Small": [1, 1],
  "Bin": [1, 1],
  "Wall-Graph": [2, 1],
  "Board": [2, 1],
  "Coffee-Machine": [1, 1],
  "Big-Filing-Cabinet": [1, 2],
  "Filing-Cabinet-Tall": [1, 2],
  "Bookshelf": [2, 2],
  "Small-Sofa": [2, 2],
  "Small-Table": [1, 1],
};

/**
 * Four-agent trading floor:
 *  - Row 1: wall-mounted board/graph + storage along the north wall.
 *  - Rows 3-5: four research workstations (desk + chair pairs), one per agent.
 *  - Row 6: a continuous central aisle spanning the full width.
 *  - Rows 7-11 west half: strategy meeting room (round table + bookshelf + sofa).
 *  - Rows 7-11 east half: risk & execution desk (boss desk/chair + hardware).
 */
export function createDefaultOfficeLayout(): OfficeLayout {
  const cols = 18;
  const rows = 13;
  const furniture: PlacedFurniture[] = [
    // North wall
    { uid: "board", type: "Board", col: 2, row: 1 },
    { uid: "graph", type: "Wall-Graph", col: 8, row: 1 },
    { uid: "cabinet", type: "Big-Filing-Cabinet", col: 14, row: 1 },
    { uid: "servertall", type: "Filing-Cabinet-Tall", col: 16, row: 1 },

    // Research workstations — one desk+chair pair per agent
    { uid: "d1", type: "Desk-2", col: 2, row: 3 },
    { uid: "d2", type: "Desk-2", col: 6, row: 3 },
    { uid: "d3", type: "Desk-2", col: 10, row: 3 },
    { uid: "d4", type: "Desk-2", col: 14, row: 3 },
    { uid: "c1", type: "Chair-2", col: 3, row: 5 },
    { uid: "c2", type: "Chair-2", col: 7, row: 5 },
    { uid: "c3", type: "Chair-2", col: 11, row: 5 },
    { uid: "c4", type: "Chair-2", col: 15, row: 5 },
    { uid: "p1", type: "Small-Plant", col: 1, row: 3 },
    { uid: "p2", type: "Small-Plant", col: 16, row: 5 },

    // Central aisle stays clear at row 6 (see officeLayout.test.ts)

    // Strategy meeting room (west)
    { uid: "books", type: "Bookshelf", col: 1, row: 7 },
    { uid: "rt", type: "Big-Round-Table", col: 3, row: 8 },
    { uid: "mc1", type: "Chair-2", col: 3, row: 10 },
    { uid: "mc2", type: "Chair-2", col: 5, row: 9, mirrored: true },
    { uid: "mc3", type: "Chair-2", col: 2, row: 9 },
    { uid: "sofa", type: "Small-Sofa", col: 1, row: 10 },
    { uid: "table", type: "Small-Table", col: 3, row: 11 },

    // Risk & execution desk (east)
    { uid: "coffee", type: "Coffee-Machine", col: 10, row: 8 },
    { uid: "p3", type: "Small-Plant", col: 10, row: 10 },
    { uid: "bd", type: "Boss-Desk", col: 11, row: 8 },
    { uid: "bc", type: "Boss-Chair", col: 12, row: 10 },
    { uid: "wd", type: "Water-Dispenser", col: 14, row: 8 },
    { uid: "pr", type: "Big-Office-Printer", col: 15, row: 8 },
    { uid: "fc", type: "Filing-Cabinet-Small", col: 16, row: 8 },
    { uid: "bn", type: "Bin", col: 16, row: 10 },
  ];
  const tiles: number[] = Array.from({ length: cols * rows }, (_, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    return col === 0 || row === 0 || col === cols - 1 || row === rows - 1
      ? TileType.WALL
      : TileType.FLOOR;
  });
  for (const item of furniture) {
    const [width, height] = FOOTPRINTS[item.type] ?? [0, 0];
    for (let row = item.row; row < item.row + height; row += 1) {
      for (let col = item.col; col < item.col + width; col += 1) {
        if (row > 0 && row < rows - 1 && col > 0 && col < cols - 1) {
          tiles[row * cols + col] = TileType.BLOCKED;
        }
      }
    }
  }
  return {
    version: 1,
    cols,
    rows,
    tiles,
    furniture,
  };
}
