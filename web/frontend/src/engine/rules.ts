/**
 * Battleship rules — a port of model/battleship/game.py.
 * Cells are indices 0..99, idx = r*10 + c. Equivalence with Python is
 * verified by the test on web/fixtures/engine.json.
 */
export const N = 10;
export const CELLS = N * N;
export const FLEET: ReadonlyArray<readonly [size: number, count: number]> = [[4, 1], [3, 2], [2, 3], [1, 4]];
export const SHIP_SIZES = [4, 3, 2, 1] as const;
export const N_SHIPS = FLEET.reduce((a, [, c]) => a + c, 0);
export const TOTAL_CELLS = FLEET.reduce((a, [s, c]) => a + s * c, 0);
export const LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К"] as const;

export const MISS = 0, HIT = 1, SUNK = 2;
export type ShotResult = typeof MISS | typeof HIT | typeof SUNK;
export const EXTRA_TURN_ON_HIT = true;

export type Ships = number[][];

export const rowOf = (idx: number) => Math.floor(idx / N);
export const colOf = (idx: number) => idx % N;
export const idxOf = (r: number, c: number) => r * N + c;
export const labelOf = (idx: number) => `${LETTERS[colOf(idx)]}${rowOf(idx) + 1}`;

export class PlacementError extends Error {}
export class IllegalShot extends Error {}

export function neighbours(idx: number): number[] {
  const r = rowOf(idx), c = colOf(idx);
  const out: number[] = [];
  for (let rr = Math.max(0, r - 1); rr < Math.min(N, r + 2); rr++)
    for (let cc = Math.max(0, c - 1); cc < Math.min(N, c + 2); cc++) out.push(idxOf(rr, cc));
  return out;
}

export function shipCells(r: number, c: number, size: number, horizontal: boolean): number[] {
  const out: number[] = [];
  for (let i = 0; i < size; i++) out.push(horizontal ? idxOf(r, c + i) : idxOf(r + i, c));
  return out;
}

/** Canonical form of the placement or PlacementError. */
export function validatePlacement(ships: Ships): Ships {
  if (ships.length !== N_SHIPS) throw new PlacementError(`кораблей ${ships.length}, ожидается ${N_SHIPS}`);
  const canon: number[][] = [];
  const seen = new Set<number>();
  for (const raw of ships) {
    const cells = raw.map((x) => Number(x)).sort((a, b) => a - b);
    if (!cells.length || cells.some((x) => !Number.isInteger(x) || x < 0 || x >= CELLS))
      throw new PlacementError("клетка вне поля");
    if (new Set(cells).size !== cells.length) throw new PlacementError("повтор клетки внутри корабля");
    const rows = cells.map(rowOf), cols = cells.map(colOf);
    const straightH = new Set(rows).size === 1 && cols.every((c, i) => c === cols[0] + i);
    const straightV = new Set(cols).size === 1 && rows.every((r, i) => r === rows[0] + i);
    if (!straightH && !straightV) throw new PlacementError("корабль не на прямой");
    if (cells.some((x) => seen.has(x))) throw new PlacementError("корабли пересекаются");
    cells.forEach((x) => seen.add(x));
    canon.push(cells);
  }
  const counts = new Map<number, number>();
  canon.forEach((s) => counts.set(s.length, (counts.get(s.length) ?? 0) + 1));
  const expected = new Map(FLEET.map(([s, c]) => [s, c]));
  if (counts.size !== expected.size || [...expected].some(([s, c]) => counts.get(s) !== c))
    throw new PlacementError("неверный состав флота");
  for (let i = 0; i < canon.length; i++)
    for (let j = i + 1; j < canon.length; j++)
      for (const a of canon[i])
        for (const b of canon[j])
          if (Math.abs(rowOf(a) - rowOf(b)) <= 1 && Math.abs(colOf(a) - colOf(b)) <= 1)
            throw new PlacementError("корабли соприкасаются");
  canon.sort((a, b) => b.length - a.length || a[0] - b[0]);
  return canon;
}

export function isValidPlacement(ships: Ships): boolean {
  try { validatePlacement(ships); return true; } catch { return false; }
}

/** Can a ship occupy the cells given the occupancy grid (not counting itself). */
export function fits(occupied: Uint8Array, cells: number[]): boolean {
  for (const x of cells) {
    if (x < 0 || x >= CELLS) return false;
    for (const nb of neighbours(x)) if (occupied[nb]) return false;
  }
  return true;
}

export type Rng = () => number; // [0, 1)

/** Greedy sequential placement — the same algorithm as random_placement in game.py. */
export function randomPlacement(rng: Rng = Math.random): Ships {
  for (;;) {
    const occupied = new Uint8Array(CELLS);
    const ships: Ships = [];
    let ok = true;
    outer: for (const [size, count] of FLEET) {
      for (let k = 0; k < count; k++) {
        let placed = false;
        for (let t = 0; t < 300; t++) {
          const horizontal = rng() < 0.5 || size === 1;
          let r: number, c: number;
          if (horizontal) { r = Math.floor(rng() * N); c = Math.floor(rng() * (N - size + 1)); }
          else { r = Math.floor(rng() * (N - size + 1)); c = Math.floor(rng() * N); }
          const cells = shipCells(r, c, size, horizontal);
          if (fits(occupied, cells)) {
            cells.forEach((x) => (occupied[x] = 1));
            ships.push(cells);
            placed = true;
            break;
          }
        }
        if (!placed) { ok = false; break outer; }
      }
    }
    if (ok) return ships;
  }
}

export interface ShotOutcome {
  result: ShotResult;
  sunkCells: number[];
  revealed: number[];   // auto-revealed perimeter (new cells only)
}

/** One board under fire — a mirror of Game from game.py. */
export class Board {
  readonly ships: Ships;
  readonly grid = new Int8Array(CELLS);          // 0 — water, otherwise ship number 1..10
  readonly known = new Uint8Array(CELLS);
  readonly hit = new Uint8Array(CELLS);
  readonly sunk = new Uint8Array(CELLS);
  readonly hitsPerShip: number[];
  readonly alive: Record<number, number> = {};
  nShots = 0;

  constructor(ships: Ships) {
    this.ships = ships.map((s) => [...s]);
    this.ships.forEach((cells, i) => cells.forEach((x) => (this.grid[x] = i + 1)));
    this.hitsPerShip = new Array(this.ships.length + 1).fill(0);
    for (const [s, c] of FLEET) this.alive[s] = c;
  }

  get done(): boolean {
    return SHIP_SIZES.every((s) => this.alive[s] === 0);
  }

  shoot(idx: number): ShotOutcome {
    if (idx < 0 || idx >= CELLS) throw new IllegalShot(`клетка ${idx} вне поля`);
    if (this.known[idx]) throw new IllegalShot(`клетка ${idx} уже открыта`);
    this.nShots++;
    this.known[idx] = 1;
    const sid = this.grid[idx];
    if (sid === 0) return { result: MISS, sunkCells: [], revealed: [] };
    this.hit[idx] = 1;
    this.hitsPerShip[sid]++;
    const cells = this.ships[sid - 1];
    if (this.hitsPerShip[sid] < cells.length) return { result: HIT, sunkCells: [], revealed: [] };
    this.alive[cells.length]--;
    const revealed: number[] = [];
    cells.forEach((x) => (this.sunk[x] = 1));
    for (const x of cells)
      for (const nb of neighbours(x))
        if (!this.known[nb]) { this.known[nb] = 1; revealed.push(nb); }
    return { result: SUNK, sunkCells: [...cells].sort((a, b) => a - b), revealed: revealed.sort((a, b) => a - b) };
  }

  /** Apply an external referee's result (H2H): mark the cell by an already known outcome. */
  applyKnown(idx: number, state: "miss" | "hit" | "sunk") {
    this.known[idx] = 1;
    if (state !== "miss") this.hit[idx] = 1;
    if (state === "sunk") this.sunk[idx] = 1;
  }

  /**
   * Observation for the net: (8,10,10) float32 in game.py channel order —
   * 0 unknown, 1 known&!hit, 2 hit&!sunk, 3 sunk, 4..7 fraction of alive ships of size 4,3,2,1.
   */
  observation(): Float32Array {
    const obs = new Float32Array(8 * CELLS);
    for (let i = 0; i < CELLS; i++) {
      const k = this.known[i], h = this.hit[i], z = this.sunk[i];
      obs[i] = k ? 0 : 1;
      obs[CELLS + i] = k && !h ? 1 : 0;
      obs[2 * CELLS + i] = h && !z ? 1 : 0;
      obs[3 * CELLS + i] = z ? 1 : 0;
    }
    const init = new Map(FLEET.map(([s, c]) => [s, c]));
    SHIP_SIZES.forEach((s, j) => {
      const v = this.alive[s] / init.get(s)!;
      obs.fill(v, (4 + j) * CELLS, (5 + j) * CELLS);
    });
    return obs;
  }
}

export function replay(ships: Ships, shots: number[]): Board {
  const b = new Board(ships);
  for (const s of shots) b.shoot(s);
  return b;
}
