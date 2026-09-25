import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAgent } from "../ai/loader";
import { ApiError, api, displayName, type LeaderRow, type Me } from "../api/client";
import { Header } from "../components/Header";
import { tr, useI18n } from "../i18n";

/** Name error: a server code from nameErrors, "save_failed" or "offline". */
function nameErrorText(t: ReturnType<typeof tr>, code: string) {
  return code === "offline" ? t.noServer : t.nameErrors[code] ?? t.nameSaveFailed;
}

export function Home() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [offline, setOffline] = useState(false);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [leaders, setLeaders] = useState<LeaderRow[]>([]);
  const [current, setCurrent] = useState<{ match_id: string; phase: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void getAgent();
    api.me().then((m) => { setMe(m); setName((cur) => cur || (m.name ?? "")); }).catch(() => setOffline(true));
    api.leaderboard().then(setLeaders).catch(() => undefined);
    api.currentMatch().then((c) => c.match_id && setCurrent({ match_id: c.match_id, phase: c.phase ?? "" })).catch(() => undefined);
  }, []);

  const saveName = async () => {
    setSaving(true); setNameError(null);
    try {
      if (name.trim()) { const r = await api.setName(name); setMe((m) => m && { ...m, name: r.name }); }
      else { await api.clearName(); setMe((m) => m && { ...m, name: null }); }
    } catch (e) {
      setNameError(e instanceof ApiError ? e.code : "offline");
    } finally { setSaving(false); }
  };

  const createRoom = async () => {
    setBusy("room");
    try { const r = await api.createRoom(); navigate(`/match/${r.match_id}`); }
    catch (e) { alert(e instanceof ApiError && e.code === "already_in_match" ? tr().home.alreadyInMatch : tr().home.roomFailed); setBusy(null); }
  };

  const st = me?.stats;
  return (
    <div className="page">
      <Header />
      <section className="home">
        <div className="home__col">
          <div className="panel__status">
            <span className="status">{t.home.how}</span>
            <span className="muted">{offline ? t.home.offline : t.home.inBrowser}</span>
          </div>
          <div className="home__actions">
            <button type="button" className="btn btn--block" onClick={() => navigate("/play")}>{t.home.playModel}</button>
            <button type="button" className="btn btn--block" onClick={createRoom} disabled={offline || busy !== null}>{t.home.invite}</button>
            <button type="button" className="btn btn--block" onClick={() => navigate("/queue")} disabled={offline}>{t.home.findOpponent}</button>
            {current && (
              <Link className="btn btn--secondary btn--block" style={{ display: "flex", alignItems: "center", justifyContent: "center" }} to={`/match/${current.match_id}`}>{t.home.backToMatch}</Link>
            )}
          </div>
          <div className="divider" />
          <span className="label">{t.home.byCode}</span>
          <form className="name-form" onSubmit={(e) => { e.preventDefault(); if (code.trim()) navigate(`/room/${code.trim().toUpperCase()}`); }}>
            <input className="field" placeholder="ABC123" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} style={{ letterSpacing: "0.2em", textTransform: "uppercase" }} />
            <button type="submit" className="btn btn--small" disabled={offline || code.trim().length < 6}>{t.btn.join}</button>
          </form>
        </div>

        <div className="home__col">
          <span className="label">{t.home.introduce}</span>
          <form className="name-form" onSubmit={(e) => { e.preventDefault(); void saveName(); }}>
            <input className="field" placeholder={t.home.namePlaceholder} value={name} onChange={(e) => setName(e.target.value)} maxLength={16} disabled={offline} />
            <button type="submit" className="btn btn--small" disabled={saving || offline}>{t.btn.save}</button>
          </form>
          {nameError && <span className="error">{nameErrorText(t, nameError)}</span>}
          {me && <span className="muted">{t.home.you(displayName(me.name, me.tag))}</span>}
          <div className="divider" />
          <span className="label">{t.home.stats}</span>
          {st ? (
            <dl className="stats">
              <dt>{t.home.games}</dt><dd>{t.home.gamesValue(st.games, st.h2m_games, st.h2h_games)}</dd>
              <dt>{t.home.wins}</dt><dd>{st.wins}{st.win_rate !== null && ` · ${Math.round(st.win_rate * 100)}%`}</dd>
              <dt>{t.home.avgShots}</dt><dd>{st.avg_shots ?? "—"}</dd>
              <dt>{t.home.bestGame}</dt><dd>{st.best_shots ?? "—"}</dd>
            </dl>
          ) : <span className="muted">{offline ? t.home.unavailable : t.home.empty}</span>}
          <div className="divider" />
          <span className="label">{t.home.leaders}</span>
          {leaders.length === 0 ? <span className="muted">{t.home.noLeaders}</span> : (
            <table className="leader">
              <thead><tr><th>{t.home.colPlayer}</th><th>{t.home.colGames}</th><th>{t.home.colWins}</th><th>{t.home.colShots}</th></tr></thead>
              <tbody>
                {leaders.map((r) => (
                  <tr key={r.player_id}><td>{displayName(r.name, r.tag)}</td><td>{r.games}</td><td>{Math.round(r.win_rate * 100)}%</td><td>{r.avg_shots ?? "—"}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
      <footer className="journal">
        <div className="journal__right" style={{ width: "auto" }}>
          <p className="hint">{t.home.rules}</p>
        </div>
      </footer>
    </div>
  );
}
