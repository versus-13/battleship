import { labelOf, type ShotResult } from "../engine/rules";

export interface JournalEntry {
  who: "you" | "foe";
  cell: number;
  result: ShotResult;
}

const WORDS = ["мимо", "ранил", "убил"] as const;

export function Journal({ entries, hint, foeName = "Соперник" }: { entries: JournalEntry[]; hint?: string; foeName?: string }) {
  const last = entries.slice(-6).reverse();
  return (
    <footer className="journal">
      <div className="journal__left">
        <span className="label">Последние ходы</span>
        <div className="chips">
          {last.length === 0 && <span className="muted">ходов пока нет</span>}
          {last.map((e, i) => (
            <span key={i} className={"chip" + (e.result === 2 ? " chip--hit" : e.result === 0 ? " chip--miss" : "")}>
              {e.who === "you" ? "Вы" : foeName} · {labelOf(e.cell)} — {WORDS[e.result]}
            </span>
          ))}
        </div>
      </div>
      {hint && (
        <div className="journal__right">
          <p className="hint">{hint}</p>
        </div>
      )}
    </footer>
  );
}
