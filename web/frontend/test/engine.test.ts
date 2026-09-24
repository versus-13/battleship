import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { Board, PlacementError, isValidPlacement, randomPlacement, replay, validatePlacement } from "../src/engine/rules";

const fx = JSON.parse(readFileSync(new URL("../../fixtures/engine.json", import.meta.url), "utf8"));

function maskHex(m: Uint8Array): string {
  let bits = "";
  for (const v of m) bits += v ? "1" : "0";
  return BigInt("0b" + bits).toString(16).padStart(25, "0");
}

describe("the engine is equivalent to game.py", () => {
  it("replays 200 games from the fixtures", () => {
    for (const g of fx.games) {
      const board = new Board(validatePlacement(g.ships));
      for (const step of g.steps) {
        const out = board.shoot(step.s);
        expect(out.result).toBe(step.r);
        expect(maskHex(board.known)).toBe(step.k);
        expect(maskHex(board.hit)).toBe(step.h);
        expect(maskHex(board.sunk)).toBe(step.z);
        expect(fx.rules.ship_sizes.map((s: number) => board.alive[s])).toEqual(step.a);
      }
      expect(board.nShots).toBe(g.n_shots);
      expect(board.done).toBe(g.done);
    }
  });

  it("the observation is consistent with the masks", () => {
    const g = fx.games[0];
    const board = new Board(g.ships);
    for (const step of g.steps.slice(0, 30)) board.shoot(step.s);
    const obs = board.observation();
    for (let i = 0; i < 100; i++) {
      expect(obs[i] + obs[100 + i] + obs[200 + i] + obs[300 + i]).toBe(1);
      expect(obs[i]).toBe(board.known[i] ? 0 : 1);
    }
    expect(obs[400]).toBe(board.alive[4] / 1);
    expect(obs[700]).toBe(board.alive[1] / 4);
  });

  it("invalid placements are rejected", () => {
    for (const bad of fx.invalid_placements) expect(() => validatePlacement(bad.ships), bad.why).toThrow(PlacementError);
    expect(validatePlacement(fx.valid_placement).map((s: number[]) => s.length)).toEqual([4, 3, 3, 2, 2, 2, 1, 1, 1, 1]);
  });

  it("random placement is valid", () => {
    for (let i = 0; i < 200; i++) expect(isValidPlacement(randomPlacement())).toBe(true);
  });

  it("a shot at an auto-revealed cell is an error", () => {
    expect(() => replay(fx.valid_placement, [70, 60])).toThrow();
  });
});
