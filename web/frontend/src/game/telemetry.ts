/** Log of a human-vs-model game: placement + shots; the unit is one attacker against one board. */
import { api, ensureIdentity } from "../api/client";
import type { Board } from "../engine/rules";

export const CLIENT_VERSION = "web-0.1.0";

export type PlacementMode = "random" | "manual";

export interface H2MLogs {
  clientGameId: string;
  modelVersion: string;
  myBoard: Board;      // my board — the model shoots at it
  foeBoard: Board;     // the model's board — I shoot at it
  myShots: number[];
  foeShots: number[];
  myThinkMs: number[];   // from the moment the turn became available until the click
  foeThinkMs: number[];  // model inference latency
  startedAt: number;     // unix seconds
  placement: PlacementMode;
  winner: "you" | "foe" | null;
}

/** Environment without personal data: platform, screen, touch, placement mode, model backend. */
export function clientInfo(placement: PlacementMode, modelBackend: string) {
  return {
    platform: typeof navigator !== "undefined" ? navigator.platform : "",
    screen: typeof window !== "undefined" ? [window.innerWidth, window.innerHeight] : [0, 0],
    touch: typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches,
    placement,
    model_backend: modelBackend,
  };
}

export function buildPayload(l: H2MLogs) {
  const finished = l.winner !== null;
  return {
    client_game_id: l.clientGameId,
    mode: "h2m",
    client: "web",
    client_version: CLIENT_VERSION,
    client_info: clientInfo(l.placement, l.modelVersion),
    logs: [
      {
        attacker: { kind: "player" }, defender: { kind: "model_board" },
        ships: l.foeBoard.ships, shots: l.myShots, think_ms: l.myThinkMs, started_at: l.startedAt,
        fleet_cleared: l.foeBoard.done, won: finished ? l.winner === "you" : null,
      },
      {
        attacker: { kind: "model", version: l.modelVersion }, defender: { kind: "player" },
        ships: l.myBoard.ships, shots: l.foeShots, think_ms: l.foeThinkMs, started_at: l.startedAt,
        fleet_cleared: l.myBoard.done, won: finished ? l.winner === "foe" : null,
      },
    ],
  };
}

export async function sendLogs(l: H2MLogs): Promise<void> {
  if (l.myShots.length + l.foeShots.length === 0) return;
  try { await api.postGames(buildPayload(l)); } catch (e) { console.warn("телеметрия не отправлена", e); }
}

/** On leaving the page: fetch with keepalive survives closing the tab (sendBeacon cannot set headers). */
export function sendLogsOnUnload(l: H2MLogs) {
  if (l.myShots.length + l.foeShots.length === 0) return;
  const id = ensureIdentity();
  void id.then((identity) => {
    fetch("/api/games", {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${identity.secret}` },
      body: JSON.stringify(buildPayload(l)),
    }).catch(() => undefined);
  });
}
