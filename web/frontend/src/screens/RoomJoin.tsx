/** Join by link /room/:code — show the host and join. */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, displayName } from "../api/client";
import { Header } from "../components/Header";

export function RoomJoin() {
  const { code = "" } = useParams();
  const navigate = useNavigate();
  const [host, setHost] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.roomInfo(code).then((r) => {
      if (r.status !== "waiting") setError("комната уже занята или игра закончилась");
      setHost(displayName(r.host_name, r.host_tag));
    }).catch(() => setError("комната не найдена"));
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
      setError(c === "room_unavailable" ? "комната уже занята" : "не удалось войти"); setBusy(false);
    }
  };

  return (
    <div className="page">
      <Header subtitle="приглашение в матч" />
      <section className="home__col">
        <span className="status">Комната {code}</span>
        {host && !error && <span className="muted">вас зовёт {host}</span>}
        {error && <span className="error">{error}</span>}
        <div className="home__actions">
          <button type="button" className="btn btn--block" onClick={join} disabled={!!error || !host || busy}>Принять вызов</button>
          <button type="button" className="btn btn--secondary btn--block" onClick={() => navigate("/")}>На главную</button>
        </div>
      </section>
    </div>
  );
}
