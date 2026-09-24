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

export function cellViews(b: Engine): CellView[] {
  const out: CellView[] = [];
  for (let i = 0; i < 100; i++) out.push(!b.known[i] ? "unknown" : b.sunk[i] ? "sunk" : b.hit[i] ? "hit" : "miss");
  return out;
}

const HINT = "Клетки вокруг убитого корабля помечаются точками сами — как карандашом на полях.";

export function BattleLocal({ ships, placement, agent, onNewGame }: { ships: Ships; placement: PlacementMode; agent: Agent; onNewGame: () => void }) {
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

  const status = s.winner ? (s.winner === "you" ? "Победа" : "Поражение") : s.yourTurn ? "Ваш ход" : "Ход модели";
  const hint = s.winner ? "партия окончена" : s.yourTurn ? "стреляйте по полю соперника" : "модель думает…";

  const restart = () => setMatch(new LocalMatch(ships, agent, placement));

  return (
    <>
      <section className="battle">
        <Board caption="Мой флот" counter={`уцелело ${myAlive} из ${TOTAL_CELLS}`} cells={myCells}
          ships={shipsView(s.myBoard.ships).map((v) => (s.myBoard.sunk[v.cells[0]] ? { ...v, tone: "sunk" } : v))}
          aim={s.lastFoeShot} ariaHidden />
        <Board caption="Поле соперника" counter={`потоплено ${foeSunk} из 10`} cells={foeCells} ships={foeShips}
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
            <button type="button" className="btn btn--block" onClick={onNewGame}>Новая игра</button>
            <button type="button" className="btn btn--secondary btn--block" onClick={() => match.surrender()} disabled={!!s.winner}>Сдаться</button>
          </div>
        </aside>
      </section>
      <Journal entries={s.journal} hint={HINT} foeName="Модель" />
      {s.winner && (
        <GameOver
          title={s.winner === "you" ? "Победа!" : "Поражение"}
          text={s.winner === "you"
            ? `Вы потопили флот модели за ${s.foeBoard.nShots} выстрелов.`
            : s.reason === "surrender" ? "Вы сдались. Корабли модели раскрыты на её поле." : `Модель потопила ваш флот за ${s.myBoard.nShots} выстрелов.`}
          primary="Ещё раз" onPrimary={restart}
          secondary="На главную" onSecondary={() => navigate("/")}
        />
      )}
    </>
  );
}
