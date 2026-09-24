/**
 * A human-vs-model game entirely on the client. Both boards are here; the model
 * shoots at the player's board, the player at the model's. Rule: hit — shoot again.
 */
import type { Agent } from "../ai/agent";
import { Board, EXTRA_TURN_ON_HIT, randomPlacement, type Ships } from "../engine/rules";
import type { JournalEntry } from "../components/Journal";
import { sendLogs, sendLogsOnUnload, type H2MLogs, type PlacementMode } from "./telemetry";

export type Winner = "you" | "foe" | null;

export interface LocalMatchSnapshot {
  myBoard: Board;
  foeBoard: Board;
  yourTurn: boolean;
  thinking: boolean;
  winner: Winner;
  reason: "fleet_sunk" | "surrender" | null;
  journal: JournalEntry[];
  lastFoeShot: number | null;
  sunkFoeShips: number[][];
  version: number;
}

const AI_DELAY_MS = 650;

export class LocalMatch {
  private snap: LocalMatchSnapshot;
  private listeners = new Set<() => void>();
  private myShots: number[] = [];
  private foeShots: number[] = [];
  private myThinkMs: number[] = [];
  private foeThinkMs: number[] = [];
  private turnSince = performance.now();
  private readonly startedAt = Date.now() / 1000;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private sent = false;
  readonly clientGameId = crypto.randomUUID();
  private onUnload = () => this.flushOnUnload();

  constructor(myShips: Ships, private agent: Agent, private placement: PlacementMode, foeShips: Ships = randomPlacement()) {
    const yourTurn = Math.random() < 0.5;
    this.snap = {
      myBoard: new Board(myShips), foeBoard: new Board(foeShips),
      yourTurn, thinking: false, winner: null, reason: null, journal: [],
      lastFoeShot: null, sunkFoeShips: [], version: 0,
    };
  }

  /** Side effects separately from the constructor: React StrictMode mounts twice. */
  start() {
    window.addEventListener("pagehide", this.onUnload);
    if (!this.snap.winner && !this.snap.yourTurn && this.timer === null) this.scheduleAi();
  }

  stop() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    window.removeEventListener("pagehide", this.onUnload);
    if (!this.snap.winner) this.flushOnUnload();
  }

  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  getSnapshot = () => this.snap;

  private emit(patch: Partial<LocalMatchSnapshot>) {
    this.snap = { ...this.snap, ...patch, version: this.snap.version + 1 };
    this.listeners.forEach((fn) => fn());
  }

  private logs(): H2MLogs {
    return {
      clientGameId: this.clientGameId, modelVersion: this.agent.label.replace(/^model:/, ""),
      myBoard: this.snap.myBoard, foeBoard: this.snap.foeBoard,
      myShots: this.myShots, foeShots: this.foeShots,
      myThinkMs: this.myThinkMs, foeThinkMs: this.foeThinkMs,
      startedAt: this.startedAt, placement: this.placement, winner: this.snap.winner,
    };
  }

  shoot(idx: number) {
    const s = this.snap;
    if (s.winner || !s.yourTurn || s.thinking || s.foeBoard.known[idx]) return;
    const out = s.foeBoard.shoot(idx);
    this.myShots.push(idx);
    this.myThinkMs.push(Math.round(performance.now() - this.turnSince));
    this.turnSince = performance.now();
    const journal = [...s.journal, { who: "you" as const, cell: idx, result: out.result }];
    const sunkFoeShips = out.result === 2 ? [...s.sunkFoeShips, out.sunkCells] : s.sunkFoeShips;
    if (s.foeBoard.done) {
      this.emit({ journal, sunkFoeShips, yourTurn: false, winner: "you", reason: "fleet_sunk" });
      this.finish();
      return;
    }
    const yourTurn = EXTRA_TURN_ON_HIT && out.result > 0;
    this.emit({ journal, sunkFoeShips, yourTurn });
    if (!yourTurn) this.scheduleAi();
  }

  private scheduleAi() {
    this.emit({ thinking: true });
    this.timer = setTimeout(() => void this.aiMove(), AI_DELAY_MS);
  }

  private async aiMove() {
    this.timer = null;
    const s = this.snap;
    if (s.winner || this.sent) return;
    let idx: number;
    const t0 = performance.now();
    try {
      idx = await this.agent.choose(s.myBoard);
    } catch (e) {
      console.error("ход модели не удался", e);
      idx = firstUnknown(s.myBoard);
    }
    const out = s.myBoard.shoot(idx);
    this.foeShots.push(idx);
    this.foeThinkMs.push(Math.round(performance.now() - t0));
    const journal = [...this.snap.journal, { who: "foe" as const, cell: idx, result: out.result }];
    if (s.myBoard.done) {
      this.emit({ journal, lastFoeShot: idx, thinking: false, yourTurn: false, winner: "foe", reason: "fleet_sunk" });
      this.finish();
      return;
    }
    const again = EXTRA_TURN_ON_HIT && out.result > 0;
    if (!again) this.turnSince = performance.now();
    this.emit({ journal, lastFoeShot: idx, thinking: again, yourTurn: !again });
    if (again) this.timer = setTimeout(() => void this.aiMove(), AI_DELAY_MS);
  }

  surrender() {
    if (this.snap.winner) return;
    if (this.timer) clearTimeout(this.timer);
    this.emit({ winner: "foe", reason: "surrender", yourTurn: false, thinking: false });
    this.finish();
  }

  private finish() {
    window.removeEventListener("pagehide", this.onUnload);
    if (this.sent) return;
    this.sent = true;
    void sendLogs(this.logs());
  }

  private flushOnUnload() {
    if (this.sent || this.myShots.length + this.foeShots.length === 0) return;
    this.sent = true;
    sendLogsOnUnload(this.logs());
  }
}

function firstUnknown(b: Board): number {
  for (let i = 0; i < b.known.length; i++) if (!b.known[i]) return i;
  throw new Error("нет свободных клеток");
}
