/** Human-vs-human match: the server is the referee, this only renders and sends commands. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { displayName } from "../api/client";
import { MatchSocket, type ServerMsg, type StateMsg, type WsStatus } from "../api/ws";
import { Board, shipsView, type CellView, type ShipView } from "../components/Board";
import { FleetCounter } from "../components/FleetCounter";
import { GameOver } from "../components/GameOver";
import { Header } from "../components/Header";
import { Journal, type JournalEntry } from "../components/Journal";
import { FLEET, TOTAL_CELLS, randomPlacement, type Ships } from "../engine/rules";
import type { PlacementMode } from "../game/telemetry";
import { useI18n } from "../i18n";
import { Placement } from "./Placement";

interface View {
  phase: StateMsg["phase"];
  code: string | null;
  myShips: Ships | null;
  hitsOnMe: Set<number>;
  revealedOnMe: Set<number>;
  enemyCells: Map<number, "miss" | "hit" | "sunk">;
  enemyAlive: Record<number, number>;
  sunkEnemyShips: number[][];
  enemyShips: Ships | null;
  yourTurn: boolean;
  opponent: StateMsg["opponent"];
  opponentLeft: boolean;
  deadline: number | null;
  youWon: boolean | null;
  reason: string | null;
  journal: JournalEntry[];
  lastFoeShot: number | null;
  /** server error code, translated at render */
  error: string | null;
}

const initialAlive = () => Object.fromEntries(FLEET.map(([s, c]) => [s, c]));

function fromState(m: StateMsg, prev?: View): View {
  const enemyCells = new Map<number, "miss" | "hit" | "sunk">();
  for (const [k, v] of Object.entries(m.enemy.cells)) enemyCells.set(Number(k), v);
  const alive = m.enemy.alive ? Object.fromEntries(Object.entries(m.enemy.alive).map(([k, v]) => [Number(k), v])) : initialAlive();
  return {
    phase: m.phase, code: m.code,
    myShips: m.you.ships ?? null,
    hitsOnMe: new Set(m.you.hits ?? []), revealedOnMe: new Set(m.you.revealed ?? []),
    enemyCells, enemyAlive: alive,
    sunkEnemyShips: groupSunk(enemyCells),
    enemyShips: m.enemy_ships, yourTurn: m.your_turn, opponent: m.opponent,
    opponentLeft: m.opponent ? !m.opponent.connected : false,
    deadline: m.deadline_ts, youWon: m.you_won, reason: m.end_reason,
    journal: prev?.journal ?? [], lastFoeShot: prev?.lastFoeShot ?? null, error: null,
  };
}

/** Sunk cells of the enemy board → groups (4-connected components). */
function groupSunk(cells: Map<number, string>): number[][] {
  const sunk = new Set([...cells].filter(([, v]) => v === "sunk").map(([k]) => k));
  const groups: number[][] = [];
  const seen = new Set<number>();
  for (const start of sunk) {
    if (seen.has(start)) continue;
    const g: number[] = [];
    const stack = [start];
    while (stack.length) {
      const x = stack.pop()!;
      if (seen.has(x)) continue;
      seen.add(x); g.push(x);
      for (const nb of [x - 1, x + 1, x - 10, x + 10]) {
        if (nb < 0 || nb >= 100) continue;
        if (Math.abs((nb % 10) - (x % 10)) > 1) continue;
        if (sunk.has(nb) && !seen.has(nb)) stack.push(nb);
      }
    }
    groups.push(g.sort((a, b) => a - b));
  }
  return groups;
}

export function MatchOnline() {
  const { id } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [view, setView] = useState<View | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const [ships, setShips] = useState<Ships>(() => randomPlacement());
  const [mode, setMode] = useState<PlacementMode>("random");
  const [placing, setPlacing] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);
  const sock = useRef<MatchSocket | null>(null);
  const shipsRef = useRef(ships);
  shipsRef.current = ships;

  useEffect(() => {
    if (!id) return;
    const s = new MatchSocket(id, onMessage, setWsStatus);
    sock.current = s;
    const tick = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => { s.close(); clearInterval(tick); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function onMessage(m: ServerMsg) {
    setView((v) => {
      switch (m.t) {
        case "state": return fromState(m, v ?? undefined);
        case "placed": setPlacing(false); return v && { ...v, myShips: shipsRef.current };
        case "opponent_joined": return v && { ...v, phase: "placing", opponent: { name: m.name, tag: m.tag, connected: true, placed: false } };
        case "opponent_ready": return v && { ...v, opponent: v.opponent && { ...v.opponent, placed: true } };
        case "opponent_left": return v && { ...v, opponentLeft: true };
        case "opponent_back": return v && { ...v, opponentLeft: false };
        case "start": return v && { ...v, phase: "playing", yourTurn: m.your_turn, deadline: m.deadline_ts };
        case "shot_result": {
          if (!v) return v;
          const enemyCells = new Map(v.enemyCells);
          enemyCells.set(m.cell, m.result === 0 ? "miss" : m.result === 1 ? "hit" : "sunk");
          m.sunk_cells.forEach((c) => enemyCells.set(c, "sunk"));
          m.revealed.forEach((c) => enemyCells.set(c, "miss"));
          return {
            ...v, enemyCells, sunkEnemyShips: m.result === 2 ? [...v.sunkEnemyShips, m.sunk_cells] : v.sunkEnemyShips,
            enemyAlive: Object.fromEntries(Object.entries(m.alive).map(([k, x]) => [Number(k), x])),
            yourTurn: m.your_turn, deadline: m.deadline_ts ?? v.deadline,
            journal: [...v.journal, { who: "you", cell: m.cell, result: m.result }],
          };
        }
        case "opponent_shot": {
          if (!v) return v;
          const hitsOnMe = new Set(v.hitsOnMe), revealedOnMe = new Set(v.revealedOnMe);
          if (m.result > 0) hitsOnMe.add(m.cell); else revealedOnMe.add(m.cell);
          m.revealed.forEach((c) => revealedOnMe.add(c));
          return {
            ...v, hitsOnMe, revealedOnMe, yourTurn: m.your_turn, deadline: m.deadline_ts ?? v.deadline, lastFoeShot: m.cell,
            journal: [...v.journal, { who: "foe", cell: m.cell, result: m.result }],
          };
        }
        case "game_over": return v && { ...v, phase: m.winner ? "finished" : "abandoned", youWon: m.you_won, reason: m.reason, enemyShips: m.enemy_ships, yourTurn: false, deadline: null };
        case "error": setPlacing(false); return v && { ...v, error: m.code };
        default: return v;
      }
    });
  }

  const foeName = view?.opponent ? displayName(view.opponent.name, view.opponent.tag) : t.journal.foe;
  const myCells = useMemo<CellView[]>(() => {
    const out: CellView[] = Array(100).fill("unknown");
    if (!view) return out;
    view.revealedOnMe.forEach((c) => (out[c] = "miss"));
    view.hitsOnMe.forEach((c) => (out[c] = "hit"));
    return out;
  }, [view]);
  const foeCells = useMemo<CellView[]>(() => {
    const out: CellView[] = Array(100).fill("unknown");
    view?.enemyCells.forEach((v, k) => (out[k] = v));
    return out;
  }, [view]);

  if (!id) return null;
  const errorText = view?.error ? t.errors[view.error] ?? view.error : null;
  const over = view?.phase === "finished" || view?.phase === "abandoned";
  const secondsLeft = view?.deadline ? Math.max(0, Math.round(view.deadline - now)) : null;

  const header = <Header subtitle={view?.opponent ? t.online.vs(foeName) : t.online.h2h} />;

  if (!view) {
    return <div className="page">{header}<p className="hint">{wsStatus === "closed" ? t.online.noConnection : t.online.connecting}</p></div>;
  }

  if (view.phase === "waiting") {
    const link = `${location.origin}/room/${view.code}`;
    return (
      <div className="page">{header}
        <section className="home__col">
          <span className="status">{t.status.waiting}</span>
          <span className="muted">{t.online.sendLink}</span>
          <span className="code">{view.code}</span>
          <div className="link-row">
            <input className="field" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="btn btn--small" onClick={() => void navigator.clipboard?.writeText(link)}>{t.btn.copy}</button>
          </div>
          <div>
            <button type="button" className="btn btn--secondary" onClick={() => { sock.current?.send({ t: "leave" }); navigate("/"); }}>{t.btn.cancel}</button>
          </div>
        </section>
      </div>
    );
  }

  if (view.phase === "placing" && !view.myShips) {
    return (
      <div className="page">{header}
        <Placement ships={ships} onChange={(s, m) => { setShips(s); setMode(m); }} busy={placing}
          onConfirm={() => { setPlacing(true); sock.current?.send({ t: "place", ships, mode }); }}
          status={t.placement.status} statusHint={secondsLeft !== null ? t.online.placementHint(secondsLeft, !!view.opponent?.placed) : undefined}
          extra={view.error && <span className="error">{errorText}</span>} />
      </div>
    );
  }

  const myAlive = TOTAL_CELLS - view.hitsOnMe.size;
  const foeSunk = 10 - Object.values(view.enemyAlive).reduce((a, v) => a + v, 0);
  const myShipViews: ShipView[] = shipsView(view.myShips ?? ships).map((v) => (v.cells.every((c) => view.hitsOnMe.has(c)) ? { ...v, tone: "sunk" } : v));
  const foeShipViews: ShipView[] = view.enemyShips
    ? shipsView(view.enemyShips).map((v) => (v.cells.every((c) => view.enemyCells.get(c) === "sunk") ? { ...v, tone: "sunk" } : v))
    : view.sunkEnemyShips.map((cells) => ({ cells, tone: "sunk" }));

  const waitingOpponent = view.phase === "placing";
  const status = over ? (view.youWon === null ? t.status.aborted : view.youWon ? t.status.win : t.status.loss)
    : waitingOpponent ? t.status.waiting : view.yourTurn ? t.status.yourTurn : t.online.foeTurn;
  const hint = over ? t.status.over
    : view.opponentLeft ? t.online.foeLeft
    : waitingOpponent ? t.online.foePlacing
    : view.yourTurn ? (secondsLeft !== null ? t.online.shootTimer(secondsLeft) : t.status.shoot) : t.online.aiming;

  return (
    <div className="page">{header}
      <section className="battle">
        <Board caption={t.board.mine} counter={t.board.afloat(myAlive, TOTAL_CELLS)} cells={myCells} ships={myShipViews} aim={view.lastFoeShot} ariaHidden />
        <Board caption={t.board.enemy} counter={t.board.sunk(foeSunk, 10)} cells={foeCells} ships={foeShipViews}
          interactive disabled={!view.yourTurn || over || wsStatus !== "open"} dim={waitingOpponent}
          onShoot={(i) => sock.current?.send({ t: "shoot", cell: i })} />
        <aside className="panel">
          <div className="panel__status">
            <span className="status">{status}</span>
            <span className="muted">{hint}</span>
            {view.error && <span className="error">{errorText}</span>}
            {wsStatus !== "open" && <span className="error">{t.online.reconnecting}</span>}
          </div>
          <div className="divider" />
          <FleetCounter alive={view.enemyAlive} />
          <div className="divider" />
          <div className="panel__buttons">
            <button type="button" className="btn btn--block" onClick={() => navigate("/")}>{t.btn.home}</button>
            <button type="button" className="btn btn--secondary btn--block" disabled={over} onClick={() => sock.current?.send({ t: "leave" })}>{t.btn.surrender}</button>
          </div>
        </aside>
      </section>
      <Journal entries={view.journal} foeName={foeName} hint={t.journal.hint} />
      {over && (
        <GameOver title={view.youWon === null ? t.status.aborted : view.youWon ? t.status.winTitle : t.status.loss}
          text={t.online.reason(view.reason ?? "", view.youWon)}
          primary={t.btn.home} onPrimary={() => navigate("/")} />
      )}
    </div>
  );
}
