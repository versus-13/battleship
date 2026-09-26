import { beforeEach, describe, expect, it, vi } from "vitest";

const postGames = vi.fn();
vi.mock("../src/api/client", () => {
  class ApiError extends Error { constructor(public status: number, public code: string, public body: unknown) { super(code); } }
  return { ApiError, api: { postGames: (p: unknown) => postGames(p) }, ensureIdentity: vi.fn() };
});

const { Board } = await import("../src/engine/rules");
const { ApiError } = await import("../src/api/client");
const { flushOutbox, sendLogs } = await import("../src/game/telemetry");

const SHIPS = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]];
const logs = (id: string) => ({
  clientGameId: id, modelVersion: "int8-x", myBoard: new Board(SHIPS), foeBoard: new Board(SHIPS),
  myShots: [0], foeShots: [], myThinkMs: [900], foeThinkMs: [], startedAt: 1_800_000_000,
  placement: "random" as const, winner: null,
});

beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
  postGames.mockReset();
});

const outbox = () => JSON.parse(localStorage.getItem("bs.outbox") ?? "[]").map((p: { client_game_id: string }) => p.client_game_id);

describe("telemetry outbox", () => {
  it("keeps a log the server did not get and sends it later", async () => {
    postGames.mockRejectedValueOnce(new TypeError("Failed to fetch"));     // the server is being updated
    await sendLogs(logs("g1"));
    expect(outbox()).toEqual(["g1"]);
    postGames.mockResolvedValue({ accepted: [1], rejected: [] });
    await flushOutbox();
    expect(outbox()).toEqual([]);
    expect(postGames).toHaveBeenCalledTimes(2);
  });

  it("does not retry a payload the server rejected", async () => {
    postGames.mockRejectedValueOnce(new ApiError(422, "bad", null));
    await sendLogs(logs("g2"));
    expect(outbox()).toEqual([]);
  });

  it("a successful send also flushes what is waiting; a 5xx stops the flush", async () => {
    postGames.mockRejectedValueOnce(new ApiError(502, "bad_gateway", null));
    await sendLogs(logs("g3"));
    postGames.mockRejectedValueOnce(new ApiError(503, "unavailable", null));
    await sendLogs(logs("g4"));
    expect(outbox()).toEqual(["g3", "g4"]);
    postGames.mockResolvedValue({ accepted: [1], rejected: [] });
    await sendLogs(logs("g5"));
    await vi.waitFor(() => expect(outbox()).toEqual([]));
  });
});
