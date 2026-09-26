/** Log of a human-vs-model game: placement + shots; the unit is one attacker against one board. */
import { ApiError, api, ensureIdentity } from "../api/client";
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

/*
 * Outbox: a log that could not be sent (the server is being updated, no network) waits in
 * localStorage and is sent again later. Resending is safe: the server drops duplicates
 * by (client_game_id, attacker) and answers "duplicate".
 */
type Payload = ReturnType<typeof buildPayload>;
const OUTBOX = "bs.outbox";
const OUTBOX_MAX = 20;

function readOutbox(): Payload[] {
  try { return JSON.parse(localStorage.getItem(OUTBOX) ?? "[]"); } catch { return []; }
}

function writeOutbox(items: Payload[]) {
  try {
    if (items.length) localStorage.setItem(OUTBOX, JSON.stringify(items.slice(-OUTBOX_MAX)));
    else localStorage.removeItem(OUTBOX);
  } catch { /* private mode: the log is lost, as before */ }
}

function enqueue(p: Payload) {
  writeOutbox([...readOutbox().filter((x) => x.client_game_id !== p.client_game_id), p]);
}

/** Worth retrying: the server was unreachable or failing, not a rejected payload. */
function retryable(e: unknown) {
  return !(e instanceof ApiError) || e.status >= 500 || e.status === 429;
}

let flushing = false;

export async function flushOutbox(): Promise<void> {
  if (flushing) return;
  flushing = true;
  try {
    for (const p of readOutbox()) {
      try { await api.postGames(p); } catch (e) { if (retryable(e)) return; }
      writeOutbox(readOutbox().filter((x) => x.client_game_id !== p.client_game_id));
    }
  } finally { flushing = false; }
}

export async function sendLogs(l: H2MLogs): Promise<void> {
  if (l.myShots.length + l.foeShots.length === 0) return;
  const payload = buildPayload(l);
  try {
    await api.postGames(payload);
    void flushOutbox();
  } catch (e) {
    console.warn("телеметрия не отправлена", e);
    if (retryable(e)) enqueue(payload);
  }
}

/**
 * On leaving the page: fetch with keepalive survives closing the tab (sendBeacon cannot set headers).
 * Whether it arrived is unknown, so the log also goes to the outbox; the next visit resends it.
 */
export function sendLogsOnUnload(l: H2MLogs) {
  if (l.myShots.length + l.foeShots.length === 0) return;
  const payload = buildPayload(l);
  enqueue(payload);
  const id = ensureIdentity();
  void id.then((identity) => {
    fetch("/api/games", {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${identity.secret}` },
      body: JSON.stringify(payload),
    }).catch(() => undefined);
  });
}
