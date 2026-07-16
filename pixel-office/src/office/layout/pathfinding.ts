import { TileType } from "../types";

interface Node {
  col: number;
  row: number;
}

export function findPath(
  startCol: number,
  startRow: number,
  endCol: number,
  endRow: number,
  tiles: number[],
  cols: number,
  rows: number
): Node[] {
  if (startCol === endCol && startRow === endRow) return [];

  const key = (c: number, r: number) => `${c},${r}`;
  const isWalkable = (c: number, r: number) => {
    if (c < 0 || c >= cols || r < 0 || r >= rows) return false;
    return tiles[r * cols + c] === TileType.FLOOR;
  };

  const queue: Node[] = [{ col: startCol, row: startRow }];
  const visited = new Set<string>([key(startCol, startRow)]);
  const parent = new Map<string, string>();

  const dirs = [
    [0, -1],
    [0, 1],
    [-1, 0],
    [1, 0],
  ];

  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current.col === endCol && current.row === endRow) {
      const path: Node[] = [];
      let k = key(endCol, endRow);
      while (k !== key(startCol, startRow)) {
        const [c, r] = k.split(",").map(Number);
        path.unshift({ col: c, row: r });
        k = parent.get(k)!;
      }
      return path;
    }

    for (const [dc, dr] of dirs) {
      const nc = current.col + dc;
      const nr = current.row + dr;
      const nk = key(nc, nr);
      if (!visited.has(nk) && isWalkable(nc, nr)) {
        visited.add(nk);
        parent.set(nk, key(current.col, current.row));
        queue.push({ col: nc, row: nr });
      }
    }
  }

  return [];
}
