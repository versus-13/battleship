/** WebSocket client of a human-vs-human match with reconnect. The server is the source of truth. */
import { ensureIdentity } from "./client";

export type CellState = "miss" | "hit" | "sunk";

export interface StateMsg {
  t: "state";
  match_id: string;
  code: string | null;
  phase: "waiting" | "placing" | "playing" | "finished" | "abandoned";
  you: { placed: boolean; ships?: number[][]; hits?: number[]; revealed?: number[]; reconnect_left_s: number };
  enemy: { placed: boolean; cells: Record<string, CellState>; alive: Record<string, number> | null };
  your_turn: boolean;
  /** reconnect_deadline_ts: the opponent is reconnecting until then; null — online or out of budget */
  opponent: { name: string | null; tag: string; connected: boolean; placed: boolean; reconnect_deadline_ts: number | null } | null;
  deadline_ts: number | null;
  move_s: number;
  /** moves in a row made by the server for us when the timer ran out; idle_limit of them — a loss */
  auto_streak: number;
  idle_limit: number;
  /** the opponent left early: the race is won, we may finish clearing the board */
  solo: boolean;
  winner: string | null;
  you_won: boolean | null;
  end_reason: string | null;
  enemy_ships: number[][] | null;
}

export interface ShotMsg {
  t: "shot_result" | "opponent_shot";
  cell: number; result: 0 | 1 | 2; sunk_cells: number[]; revealed: number[];
  your_turn: boolean; alive: Record<string, number>; deadline_ts?: number | null;
  /** the server shot for the shooter: the move timer ran out */
  auto: boolean; auto_streak: number;
}

export type ServerMsg =
  | StateMsg | ShotMsg
  | { t: "opponent_joined"; name: string | null; tag: string }
  | { t: "opponent_ready" } | { t: "opponent_left"; grace_s: number; reconnect_deadline_ts: number | null } | { t: "opponent_back" }
  | { t: "placed" } | { t: "start"; your_turn: boolean; deadline_ts: number }
  | { t: "game_over"; winner: string | null; you_won: boolean | null; reason: string; enemy_ships: number[][] | null;
      solo: boolean; n_shots?: number; cleared?: boolean }
  | { t: "error"; code: string; msg?: string } | { t: "pong" };

/**
 * restarting — the server closed with 1012 (an update): it saves the matches and restores them
 * on start, so we keep reconnecting and say so; gone — 4004, the match does not exist (any more).
 */
export type WsStatus = "connecting" | "open" | "closed" | "restarting" | "gone";

const RETRY_MAX_MS = 4000;

export class MatchSocket {
  private ws: WebSocket | null = null;
  private closed = false;
  private attempt = 0;
  private restarting = false;
  status: WsStatus = "connecting";

  constructor(
    private matchId: string,
    private onMessage: (m: ServerMsg) => void,
    private onStatus: (s: WsStatus) => void,
  ) {
    void this.connect();
  }

  private async connect() {
    if (this.closed) return;
    const { secret } = await ensureIdentity();
    if (this.closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/matches/${this.matchId}`);
    this.ws = ws;
    if (!this.restarting) this.setStatus("connecting");
    ws.onopen = () => {
      this.restarting = false;
      this.attempt = 0;
      ws.send(JSON.stringify({ t: "hello", token: secret }));
      this.setStatus("open");
    };
    ws.onmessage = (ev) => {
      try { this.onMessage(JSON.parse(ev.data)); } catch (e) { console.warn("плохое сообщение", e); }
    };
    ws.onclose = (ev) => {
      if (this.ws !== ws || this.closed) return;
      if (ev.code === 4004) { this.setStatus("gone"); return; }
      if (ev.code === 1012) this.restarting = true;      // while the server is down attempts fail with 1006
      this.setStatus(this.restarting ? "restarting" : "closed");
      if (ev.code === 4003 || ev.code === 4000) return;
      const delay = Math.min(RETRY_MAX_MS, 500 * 2 ** this.attempt++);
      setTimeout(() => void this.connect(), delay);
    };
  }

  private setStatus(s: WsStatus) { this.status = s; this.onStatus(s); }

  send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  close() {
    this.closed = true;
    if (this.ws) { this.ws.onclose = null; this.ws.onmessage = null; this.ws.close(); }
  }
}
