import { describe, expect, it } from "vitest";
import { Board } from "../src/engine/rules";
import { buildPayload } from "../src/game/telemetry";

const SHIPS = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]];

describe("h2m telemetry", () => {
  it("logs contain shots, think times, start and environment", () => {
    const my = new Board(SHIPS), foe = new Board(SHIPS);
    foe.shoot(0); foe.shoot(1); my.shoot(99);
    const p = buildPayload({
      clientGameId: "g", modelVersion: "int8-x", myBoard: my, foeBoard: foe,
      myShots: [0, 1], foeShots: [99], myThinkMs: [1200, 800], foeThinkMs: [7],
      startedAt: 1_800_000_000, placement: "manual", winner: null,
    });
    expect(p.logs[0].shots).toEqual([0, 1]);
    expect(p.logs[0].think_ms).toEqual([1200, 800]);
    expect(p.logs[1].think_ms).toEqual([7]);
    expect(p.logs[0].won).toBeNull();
    expect(p.logs[0].fleet_cleared).toBe(false);
    expect(p.client_info.placement).toBe("manual");
    expect(p.client_info.model_backend).toBe("int8-x");
    expect(p.logs[0].started_at).toBe(1_800_000_000);
  });
});
