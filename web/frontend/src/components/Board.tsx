import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { CELLS, N, colOf, rowOf, type Ships } from "../engine/rules";
import { useI18n } from "../i18n";
import { AimMark, HitMark, MissMark, ShipOutline, type ShipTone } from "./marks";

export type CellView = "unknown" | "miss" | "hit" | "sunk";

export interface ShipView {
  cells: number[];
  tone: ShipTone;
}

export interface BoardProps {
  caption: string;
  counter?: string;
  cells: CellView[];
  ships?: ShipView[];
  interactive?: boolean;
  disabled?: boolean;
  aim?: number | null;
  dim?: boolean;
  onShoot?: (idx: number) => void;
  /** Placement mode: dragging (dx, dy in cells) and rotation by click. */
  onShipMove?: (shipIndex: number, dr: number, dc: number) => void;
  onShipRotate?: (shipIndex: number) => void;
  ariaHidden?: boolean;
}

export function shipGeometry(cells: number[]) {
  const sorted = [...cells].sort((a, b) => a - b);
  const horizontal = sorted.length === 1 || rowOf(sorted[0]) === rowOf(sorted[1]);
  return { row: rowOf(sorted[0]), col: colOf(sorted[0]), size: sorted.length, horizontal };
}

export function Board(p: BoardProps) {
  const { t } = useI18n();
  const boardRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ index: number; dr: number; dc: number } | null>(null);
  const start = useRef<{ index: number; x: number; y: number; moved: boolean } | null>(null);

  const cellPx = () => (boardRef.current ? boardRef.current.getBoundingClientRect().width / N : 40);

  const onPointerDown = (index: number) => (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!p.onShipMove) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    start.current = { index, x: e.clientX, y: e.clientY, moved: false };
    setDrag({ index, dr: 0, dc: 0 });
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const s = start.current;
    if (!s) return;
    const px = cellPx();
    const dc = Math.round((e.clientX - s.x) / px);
    const dr = Math.round((e.clientY - s.y) / px);
    if (dr !== 0 || dc !== 0) s.moved = true;
    setDrag({ index: s.index, dr, dc });
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const s = start.current;
    if (!s) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    const px = cellPx();
    const dc = Math.round((e.clientX - s.x) / px);
    const dr = Math.round((e.clientY - s.y) / px);
    start.current = null;
    setDrag(null);
    if (dr === 0 && dc === 0 && !s.moved) p.onShipRotate?.(s.index);
    else p.onShipMove?.(s.index, dr, dc);
  };

  return (
    <div className="board-col" aria-hidden={p.ariaHidden || undefined}>
      <div className="board-col__caption">
        <span className="caption">{p.caption}</span>
        {p.counter && <span className="muted">{p.counter}</span>}
      </div>
      <div className="ruler">
        <div className="ruler__corner" />
        {t.letters.map((ch) => (
          <div key={ch} className="ruler__cell">{ch}</div>
        ))}
      </div>
      <div className="board-row">
        <div className="ruler ruler--v">
          {Array.from({ length: N }, (_, i) => (
            <div key={i} className="ruler__cell">{i + 1}</div>
          ))}
        </div>
        <div className={"board" + (p.dim ? " board--dim" : "")} ref={boardRef}>
          <div className="board__grid">
            {Array.from({ length: CELLS }, (_, i) => {
              const st = p.cells[i];
              const mark = st === "miss" ? <MissMark /> : st === "hit" || st === "sunk" ? <HitMark /> : p.aim === i ? <AimMark /> : null;
              if (p.interactive) {
                return (
                  <button
                    key={i}
                    type="button"
                    className="cell cell--btn"
                    aria-label={t.cell(i)}
                    disabled={p.disabled || st !== "unknown"}
                    onClick={() => p.onShoot?.(i)}
                  >
                    {mark}
                  </button>
                );
              }
              return <div key={i} className="cell">{mark}</div>;
            })}
          </div>
          <div className="board__overlay">
            {p.ships?.map((ship, index) => {
              const g = shipGeometry(ship.cells);
              const d = drag && drag.index === index ? drag : null;
              const row = g.row + (d?.dr ?? 0), col = g.col + (d?.dc ?? 0);
              const w = g.horizontal ? g.size : 1, h = g.horizontal ? 1 : g.size;
              return (
                <div
                  key={index}
                  className={"ship" + (p.onShipMove ? " ship--drag" : "") + (d ? " ship--dragging" : "")}
                  style={{
                    left: `calc(var(--cell) * ${col})`, top: `calc(var(--cell) * ${row})`,
                    width: `calc(var(--cell) * ${w})`, height: `calc(var(--cell) * ${h})`,
                  }}
                  onPointerDown={onPointerDown(index)}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={() => { start.current = null; setDrag(null); }}
                >
                  <ShipOutline size={g.size} horizontal={g.horizontal} tone={ship.tone} />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Build ship views from groups of sunk cells (outlines on the enemy board). */
export function sunkShipsFromCells(sunkGroups: number[][]): ShipView[] {
  return sunkGroups.map((cells) => ({ cells, tone: "sunk" }));
}

export function shipsView(ships: Ships, tone: ShipTone = "ink"): ShipView[] {
  return ships.map((cells) => ({ cells, tone }));
}
