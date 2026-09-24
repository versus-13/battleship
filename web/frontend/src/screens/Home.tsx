import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAgent } from "../ai/loader";
import { ApiError, api, displayName, type LeaderRow, type Me } from "../api/client";
import { Header } from "../components/Header";

const NAME_ERRORS: Record<string, string> = {
  too_short: "слишком коротко — от 2 символов",
  too_long: "слишком длинно — до 16 символов",
  invalid_chars: "только буквы, цифры, пробел, дефис и подчёркивание",
  rejected_profanity: "такое имя не подходит, попробуйте другое",
  rate_limited: "имя можно менять раз в 10 минут",
};

export function Home() {
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
      setNameError(e instanceof ApiError ? NAME_ERRORS[e.code] ?? "не удалось сохранить имя" : "нет связи с сервером");
    } finally { setSaving(false); }
  };

  const createRoom = async () => {
    setBusy("room");
    try { const r = await api.createRoom(); navigate(`/match/${r.match_id}`); }
    catch (e) { alert(e instanceof ApiError && e.code === "already_in_match" ? "вы уже в матче" : "не удалось создать комнату"); setBusy(null); }
  };

  const st = me?.stats;
  return (
    <div className="page">
      <Header />
      <section className="home">
        <div className="home__col">
          <div className="panel__status">
            <span className="status">Как играем?</span>
            <span className="muted">{offline ? "сервер недоступен — доступна только игра с моделью" : "модель считается прямо в браузере"}</span>
          </div>
          <div className="home__actions">
            <button type="button" className="btn btn--block" onClick={() => navigate("/play")}>Играть с моделью</button>
            <button type="button" className="btn btn--block" onClick={createRoom} disabled={offline || busy !== null}>Позвать друга</button>
            <button type="button" className="btn btn--block" onClick={() => navigate("/queue")} disabled={offline}>Найти соперника</button>
            {current && (
              <Link className="btn btn--secondary btn--block" style={{ display: "flex", alignItems: "center", justifyContent: "center" }} to={`/match/${current.match_id}`}>Вернуться в матч</Link>
            )}
          </div>
          <div className="divider" />
          <span className="label">По коду комнаты</span>
          <form className="name-form" onSubmit={(e) => { e.preventDefault(); if (code.trim()) navigate(`/room/${code.trim().toUpperCase()}`); }}>
            <input className="field" placeholder="ABC123" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} style={{ letterSpacing: "0.2em", textTransform: "uppercase" }} />
            <button type="submit" className="btn btn--small" disabled={offline || code.trim().length < 6}>Войти</button>
          </form>
        </div>

        <div className="home__col">
          <span className="label">Представиться</span>
          <form className="name-form" onSubmit={(e) => { e.preventDefault(); void saveName(); }}>
            <input className="field" placeholder="имя или ник" value={name} onChange={(e) => setName(e.target.value)} maxLength={16} disabled={offline} />
            <button type="submit" className="btn btn--small" disabled={saving || offline}>Сохранить</button>
          </form>
          {nameError && <span className="error">{nameError}</span>}
          {me && <span className="muted">вы — {displayName(me.name, me.tag)} · без логина: id хранится в этом браузере</span>}
          <div className="divider" />
          <span className="label">Ваша статистика</span>
          {st ? (
            <dl className="stats">
              <dt>партий</dt><dd>{st.games} (с моделью {st.h2m_games}, с людьми {st.h2h_games})</dd>
              <dt>побед</dt><dd>{st.wins}{st.win_rate !== null && ` · ${Math.round(st.win_rate * 100)}%`}</dd>
              <dt>ср. выстрелов</dt><dd>{st.avg_shots ?? "—"}</dd>
              <dt>лучшая партия</dt><dd>{st.best_shots ?? "—"}</dd>
            </dl>
          ) : <span className="muted">{offline ? "недоступна" : "пока пусто"}</span>}
          <div className="divider" />
          <span className="label">Лидеры · человек против человека</span>
          {leaders.length === 0 ? <span className="muted">пока никого — сыграйте с другом</span> : (
            <table className="leader">
              <thead><tr><th>игрок</th><th>партий</th><th>побед</th><th>ср. выстр.</th></tr></thead>
              <tbody>
                {leaders.map((r) => (
                  <tr key={r.player_id}><td>{displayName(r.name, r.tag)}</td><td>{r.games}</td><td>{Math.round(r.win_rate * 100)}%</td><td>{r.avg_shots}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
      <footer className="journal">
        <div className="journal__right" style={{ width: "auto" }}>
          <p className="hint">Правила: поле 10 × 10, флот 4-3-3-2-2-2-1-1-1-1, корабли не касаются даже углами. Попал — стреляешь снова.</p>
        </div>
      </footer>
    </div>
  );
}
