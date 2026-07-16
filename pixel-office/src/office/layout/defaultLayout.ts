import { TileType, type OfficeLayout } from "../types";

export function createDefaultOfficeLayout(): OfficeLayout {
  return {
    version: 1,
    cols: 14,
    rows: 11,
    tiles: [
      TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.FLOOR,TileType.WALL,
      TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,TileType.WALL,
    ],
    furniture: [
      { uid: "d1", type: "Desk-2", col: 3, row: 2 },
      { uid: "d2", type: "Desk-2", col: 6, row: 2 },
      { uid: "d3", type: "Desk-2", col: 9, row: 2 },
      { uid: "c1", type: "Chair-2", col: 4, row: 4 },
      { uid: "p1", type: "Small-Plant", col: 1, row: 1 },
      { uid: "p2", type: "Small-Plant", col: 12, row: 1 },
      { uid: "rt", type: "Big-Round-Table", col: 3, row: 6 },
      { uid: "bd", type: "Boss-Desk", col: 9, row: 6 },
      { uid: "bc", type: "Boss-Chair", col: 9, row: 5 },
      { uid: "pr", type: "Big-Office-Printer", col: 1, row: 4 },
      { uid: "c2", type: "Chair-2", col: 5, row: 7 },
      { uid: "wd", type: "Water-Dispenser", col: 11, row: 4 },
      { uid: "fc1", type: "Filing-Cabinet-Small", col: 2, row: 3 },
      { uid: "fc2", type: "Filing-Cabinet-Small", col: 5, row: 3 },
      { uid: "fc3", type: "Filing-Cabinet-Small", col: 8, row: 3 },
      { uid: "bn", type: "Bin", col: 8, row: 7 },
    ],
  };
}
