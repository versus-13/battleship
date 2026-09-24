/** Fallback AI without the net: hunt/target with parity — a port of HuntTargetAgent from agents.py. */
import { Board, CELLS, N, SHIP_SIZES, colOf, idxOf, rowOf } from "../engine/rules";

export function heuristicScores(board: Board): Float32Array {
  const p = new Float32Array(CELLS);
  const openHits: number[] = [];
  for (let i = 0; i < CELLS; i++) if (board.hit[i] && !board.sunk[i]) openHits.push(i);
  if (openHits.length) {
    const set = new Set(openHits);
    for (const h of openHits) {
      const r = rowOf(h), c = colOf(h);
      for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
        const rr = r + dr, cc = c + dc;
        if (rr < 0 || rr >= N || cc < 0 || cc >= N) continue;
        const idx = idxOf(rr, cc);
        if (board.known[idx]) continue;
        p[idx] += 1;
        const or = r - dr, oc = c - dc;
        if (or >= 0 && or < N && oc >= 0 && oc < N && set.has(idxOf(or, oc))) p[idx] += 10;
      }
    }
    return p;
  }
  const stride = Math.min(...SHIP_SIZES.filter((s) => board.alive[s] > 0));
  for (let i = 0; i < CELLS; i++)
    if (!board.known[i]) p[i] = (rowOf(i) + colOf(i)) % stride === 0 ? 1 : 0.01;
  return p;
}
