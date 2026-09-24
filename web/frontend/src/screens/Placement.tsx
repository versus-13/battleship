import { useMemo } from "react";
import { Board, type ShipView } from "../components/Board";
import { randomPlacement, type Ships } from "../engine/rules";
import { conflicts, moveShip, rotateShip } from "../game/placement";
import type { PlacementMode } from "../game/telemetry";
import { useI18n } from "../i18n";

interface Props {
  ships: Ships;
  /** mode: "random" after "Shuffle", "manual" after a move or rotation. */
  onChange: (ships: Ships, mode: PlacementMode) => void;
  onConfirm: () => void;
  confirmLabel?: string;
  busy?: boolean;
  status: string;
  statusHint?: string;
  extra?: React.ReactNode;
}

export function Placement(p: Props) {
  const { t } = useI18n();
  const bad = useMemo(() => conflicts(p.ships), [p.ships]);
  const views: ShipView[] = p.ships.map((cells, i) => ({ cells, tone: bad.has(i) ? "danger" : "ink" }));
  const valid = bad.size === 0;
  return (
    <section className="battle">
      <Board
        caption={t.board.mine}
        counter={valid ? t.board.ready : t.board.touching}
        cells={Array(100).fill("unknown")}
        ships={views}
        onShipMove={(i, dr, dc) => p.onChange(moveShip(p.ships, i, dr, dc), "manual")}
        onShipRotate={(i) => p.onChange(rotateShip(p.ships, i), "manual")}
      />
      <aside className="panel">
        <div className="panel__status">
          <span className="status">{p.status}</span>
          <span className="muted">{p.statusHint ?? t.placement.hint}</span>
        </div>
        <div className="divider" />
        <div className="panel__buttons">
          <button type="button" className="btn btn--block" onClick={p.onConfirm} disabled={!valid || p.busy}>{p.confirmLabel ?? t.btn.toBattle}</button>
          <button type="button" className="btn btn--secondary btn--block" onClick={() => p.onChange(randomPlacement(), "random")} disabled={p.busy}>{t.btn.shuffle}</button>
        </div>
        {p.extra}
      </aside>
    </section>
  );
}
