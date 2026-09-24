/** Manual placement: move, rotate, conflict detection. */
import { CELLS, N, colOf, idxOf, rowOf, type Ships } from "../engine/rules";
import { shipGeometry } from "../components/Board";

export function moveShip(ships: Ships, index: number, dr: number, dc: number): Ships {
  const cells = ships[index];
  const moved = cells.map((x) => {
    const r = rowOf(x) + dr, c = colOf(x) + dc;
    return r < 0 || r >= N || c < 0 || c >= N ? -1 : idxOf(r, c);
  });
  if (moved.includes(-1)) return ships;
  return ships.map((s, i) => (i === index ? moved : s));
}

export function rotateShip(ships: Ships, index: number): Ships {
  const g = shipGeometry(ships[index]);
  if (g.size === 1) return ships;
  let row = g.row, col = g.col;
  const horizontal = !g.horizontal;
  if (horizontal && col + g.size > N) col = N - g.size;
  if (!horizontal && row + g.size > N) row = N - g.size;
  const cells: number[] = [];
  for (let i = 0; i < g.size; i++) cells.push(horizontal ? idxOf(row, col + i) : idxOf(row + i, col));
  return ships.map((s, i) => (i === index ? cells : s));
}

/** Indices of ships that overlap or touch others. */
export function conflicts(ships: Ships): Set<number> {
  const owner = new Int8Array(CELLS).fill(-1);
  const bad = new Set<number>();
  ships.forEach((cells, i) => cells.forEach((x) => {
    if (owner[x] >= 0) { bad.add(i); bad.add(owner[x]); }
    owner[x] = i;
  }));
  ships.forEach((cells, i) => {
    for (const x of cells) {
      const r = rowOf(x), c = colOf(x);
      for (let rr = Math.max(0, r - 1); rr < Math.min(N, r + 2); rr++)
        for (let cc = Math.max(0, c - 1); cc < Math.min(N, c + 2); cc++) {
          const o = owner[idxOf(rr, cc)];
          if (o >= 0 && o !== i) { bad.add(i); bad.add(o); }
        }
    }
  });
  return bad;
}
