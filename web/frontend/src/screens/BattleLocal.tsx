/** Human-vs-model battle screen. */
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import type { Agent } from "../ai/agent";
import { Board, shipsView, type CellView, type ShipView } from "../components/Board";
import { FleetCounter } from "../components/FleetCounter";
import { GameOver } from "../components/GameOver";
import { Journal } from "../components/Journal";
import { Board as Engine, TOTAL_CELLS, type Ships } from "../engine/rules";
import { LocalMatch } from "../game/localMatch";
import type { PlacementMode } from "../game/telemetry";
import { useI18n } from "../i18n";

export function cellViews(b: Engine): CellView[] {
  const out: CellView[] = [];
  for (let i = 0; i < 100; i++) out.push(!b.known[i] ? "unknown" : b.sunk[i] ? "sunk" : b.hit[i] ? "hit" : "miss");
  return out;
}

export function BattleLocal({ ships, placement, agent, onNewGame }: { ships: Ships; placement: PlacementMode; agent: Agent; onNewGame: () => void }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [match, setMatch] = useState(() => new LocalMatch(ships, agent, placement));
  useEffect(() => { match.start(); return () => match.stop(); }, [match]);
  const s = useSyncExternalStore(match.subscribe, match.getSnapshot);

  const myCells = useMemo(() => cellViews(s.myBoard), [s.version, s.myBoard]);
  const foeCells = useMemo(() => cellViews(s.foeBoard), [s.version, s.foeBoard]);
  const foeShips: ShipView[] = s.winner
    ? shipsView(s.foeBoard.ships).map((v) => (s.foeBoard.sunk[v.cells[0]] ? { ...v, tone: "sunk" } : v))
    : s.sunkFoeShips.map((cells) => ({ cells, tone: "sunk" }));

  const myAlive = TOTAL_CELLS - s.myBoard.hit.reduce((a, v) => a + v, 0);
  const foeSunk = 10 - Object.values(s.foeBoard.alive).reduce((a, v) => a + v, 0);

  const status = s.winner ? (s.winner === "you" ? t.status.win : t.status.loss) : s.yourTurn ? t.status.yourTurn : t.local.modelTurn;
  const hint = s.winner ? t.status.over : s.yourTurn ? t.status.shoot : t.local.thinking;

  const restart = () => setMatch(new LocalMatch(ships, agent, placement));

  return (
    <>
      <section className="battle">
        <Board caption={t.board.mine} counter={t.board.afloat(myAlive, TOTAL_CELLS)} cells={myCells}
          ships={shipsView(s.myBoard.ships).map((v) => (s.myBoard.sunk[v.cells[0]] ? { ...v, tone: "sunk" } : v))}
          aim={s.lastFoeShot} ariaHidden />
        <Board caption={t.board.enemy} counter={t.board.sunk(foeSunk, 10)} cells={foeCells} ships={foeShips}
          interactive disabled={!s.yourTurn || !!s.winner || s.thinking} onShoot={(i) => match.shoot(i)} />
        <aside className="panel">
          <div className="panel__status">
            <span className="status">{status}</span>
            <span className="muted">{hint}</span>
          </div>
          <div className="divider" />
          <FleetCounter alive={s.foeBoard.alive} />
          <div className="divider" />
          <div className="panel__buttons">
            <button type="button" className="btn btn--block" onClick={onNewGame}>{t.btn.newGame}</button>
            <button type="button" className="btn btn--secondary btn--block" onClick={() => match.surrender()} disabled={!!s.winner}>{t.btn.surrender}</button>
          </div>
        </aside>
      </section>
      <Journal entries={s.journal} hint={t.journal.hint} foeName={t.local.model} />
      {s.winner && (
        <GameOver
          title={s.winner === "you" ? t.status.winTitle : t.status.loss}
          text={s.winner === "you"
            ? t.local.youWon(s.foeBoard.nShots)
            : s.reason === "surrender" ? t.local.surrendered : t.local.youLost(s.myBoard.nShots)}
          primary={t.btn.again} onPrimary={restart}
          secondary={t.btn.home} onSecondary={() => navigate("/")}
        />
      )}
    </>
  );
}
