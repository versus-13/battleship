/** Join by link /room/:code — show the host and join. */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, displayName } from "../api/client";
import { Header } from "../components/Header";
import { useI18n } from "../i18n";

type RoomError = "busy" | "notFound" | "taken" | "joinFailed";

export function RoomJoin() {
  const { code = "" } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [host, setHost] = useState<{ name: string | null; tag: string } | null>(null);
  const [error, setError] = useState<RoomError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.roomInfo(code).then((r) => {
      if (r.status !== "waiting") setError("busy");
      setHost({ name: r.host_name, tag: r.host_tag });
    }).catch(() => setError("notFound"));
  }, [code]);

  const join = async () => {
    setBusy(true);
    try { const r = await api.joinRoom(code); navigate(`/match/${r.match_id}`, { replace: true }); }
    catch (e) {
      const c = e instanceof ApiError ? e.code : "";
      if (c === "already_in_match" && e instanceof ApiError) {
        const mid = (e.body as { detail?: { match_id?: string } })?.detail?.match_id;
        if (mid) { navigate(`/match/${mid}`, { replace: true }); return; }
      }
      setError(c === "room_unavailable" ? "taken" : "joinFailed"); setBusy(false);
    }
  };

  return (
    <div className="page">
      <Header subtitle={t.room.subtitle} />
      <section className="home__col">
        <span className="status">{t.room.title(code)}</span>
        {host && !error && <span className="muted">{t.room.invites(displayName(host.name, host.tag))}</span>}
        {error && <span className="error">{t.room[error]}</span>}
        <div className="home__actions">
          <button type="button" className="btn btn--block" onClick={join} disabled={!!error || !host || busy}>{t.btn.accept}</button>
          <button type="button" className="btn btn--secondary btn--block" onClick={() => navigate("/")}>{t.btn.home}</button>
        </div>
      </section>
    </div>
  );
}
