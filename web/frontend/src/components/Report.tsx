/**
 * A report on the opponent of an H2H match. The server picks who is reported and
 * always answers 204; the reporter only ever sees "thanks".
 */
import { useEffect, useState } from "react";
import { api, type ReportReason } from "../api/client";
import { useI18n } from "../i18n";

const REASONS: readonly ReportReason[] = ["name", "impersonation", "cheating", "stalling", "bug"];
const key = (matchId: string) => `bs.reported.${matchId}`;

function wasReported(matchId: string): boolean {
  try { return localStorage.getItem(key(matchId)) === "1"; } catch { return false; }
}

/** One report per match: remembered here so the button stays disabled after a reload. */
export function useReport(matchId: string | undefined) {
  const [sent, setSent] = useState(() => (matchId ? wasReported(matchId) : false));
  const [open, setOpen] = useState(false);
  useEffect(() => { setSent(matchId ? wasReported(matchId) : false); }, [matchId]);
  const send = (reason: ReportReason) => {
    if (!matchId) return;
    setSent(true);
    try { localStorage.setItem(key(matchId), "1"); } catch { /* private mode */ }
    void api.report(matchId, reason).catch(() => undefined);   // "thanks" regardless
  };
  return { sent, open, setOpen, send };
}

export function ReportLink({ sent, onOpen }: { sent: boolean; onOpen: () => void }) {
  const { t } = useI18n();
  return (
    <button type="button" className="report-link" disabled={sent} onClick={onOpen}>
      {sent ? t.report.sent : t.report.button}
    </button>
  );
}

export function ReportDialog({ onSend, onClose }: { onSend: (r: ReportReason) => void; onClose: () => void }) {
  const { t } = useI18n();
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [thanks, setThanks] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="report-title">
      <form className="overlay__card" onSubmit={(e) => { e.preventDefault(); if (reason) { onSend(reason); setThanks(true); } }}>
        {thanks ? (
          <h2 className="overlay__title" id="report-title">{t.report.thanks}</h2>
        ) : (
          <>
            <h2 className="overlay__title" id="report-title">{t.report.title}</h2>
            <fieldset className="report-reasons">
              <legend className="label">{t.report.question}</legend>
              {REASONS.map((r) => (
                <label key={r}>
                  <input type="radio" name="reason" value={r} checked={reason === r} onChange={() => setReason(r)} />
                  {t.report.reasons[r]}
                </label>
              ))}
            </fieldset>
          </>
        )}
        <div className="panel__buttons">
          {!thanks && <button type="submit" className="btn btn--block" disabled={!reason}>{t.report.send}</button>}
          <button type="button" className="btn btn--secondary btn--block" onClick={onClose}>{t.report.close}</button>
        </div>
      </form>
    </div>
  );
}
