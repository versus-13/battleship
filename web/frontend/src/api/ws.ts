/** WebSocket client of a human-vs-human match with reconnect. The server is the source of truth. */
import { ensureIdentity } from "./client";

export type CellState = "miss" | "hit" | "sunk";

export interface StateMsg {
  t: "state";
  match_id: string;
  code: string | null;
  phase: "waiting" | "placing" | "playing" | "finished" | "abandoned";
  you: { placed: boolean; ships?: number[][]; hits?: number[]; revealed?: number[] };
  enemy: { placed: boolean; cells: Record<string, CellState>; alive: Record<string, number> | null };
  your_turn: boolean;
  opponent: { name: string | null; tag: string; connected: boolean; placed: boolean } | null;
  deadline_ts: number | null;
  winner: string | null;
  you_won: boolean | null;
  end_reason: string | null;
  enemy_ships: number[][] | null;
}

export interface ShotMsg {
  t: "shot_result" | "opponent_shot";
  cell: number; result: 0 | 1 | 2; sunk_cells: number[]; revealed: number[];
  your_turn: boolean; alive: Record<string, number>; deadline_ts?: number;
}

export type ServerMsg =
  | StateMsg | ShotMsg
  | { t: "opponent_joined"; name: string | null; tag: string }
  | { t: "opponent_ready" } | { t: "opponent_left"; grace_s: number } | { t: "opponent_back" }
  | { t: "placed" } | { t: "start"; your_turn: boolean; deadline_ts: number }
  | { t: "game_over"; winner: string | null; you_won: boolean | null; reason: string; enemy_ships: number[][] | null }
  | { t: "error"; code: string; msg?: string } | { t: "pong" };

export type WsStatus = "connecting" | "open" | "closed";

export class MatchSocket {
  private ws: WebSocket | null = null;
  private closed = false;
  private attempt = 0;
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
    this.setStatus("connecting");
    ws.onopen = () => {
      this.attempt = 0;
      ws.send(JSON.stringify({ t: "hello", token: secret }));
      this.setStatus("open");
    };
    ws.onmessage = (ev) => {
      try { this.onMessage(JSON.parse(ev.data)); } catch (e) { console.warn("плохое сообщение", e); }
    };
    ws.onclose = (ev) => {
      if (this.ws !== ws || this.closed) return;
      this.setStatus("closed");
      if (ev.code === 4003 || ev.code === 4004 || ev.code === 4000) return;
      const delay = Math.min(8000, 500 * 2 ** this.attempt++);
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
