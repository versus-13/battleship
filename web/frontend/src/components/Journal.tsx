import type { ShotResult } from "../engine/rules";
import { useI18n } from "../i18n";

export interface JournalEntry {
  who: "you" | "foe";
  cell: number;
  result: ShotResult;
  /** made by the server when the move timer ran out */
  auto?: boolean;
}

export function Journal({ entries, hint, foeName }: { entries: JournalEntry[]; hint?: string; foeName?: string }) {
  const { t } = useI18n();
  const last = entries.slice(-6).reverse();
  return (
    <footer className="journal">
      <div className="journal__left">
        <span className="label">{t.journal.title}</span>
        <div className="chips">
          {last.length === 0 && <span className="muted">{t.journal.empty}</span>}
          {last.map((e, i) => (
            <span key={i} className={"chip" + (e.result === 2 ? " chip--hit" : e.result === 0 ? " chip--miss" : "")}>
              {e.who === "you" ? t.journal.you : foeName ?? t.journal.foe} · {t.cell(e.cell)} — {t.journal.results[e.result]}{e.auto && ` · ${t.journal.auto}`}
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
