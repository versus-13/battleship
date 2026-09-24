/** Random queue: poll the server every 2 s until a pair is found. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Header } from "../components/Header";
import { useI18n } from "../i18n";

export function Queue() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const r = await api.queue();
        if (stop) return;
        if (r.status === "matched" && r.match_id) { navigate(`/match/${r.match_id}`, { replace: true }); return; }
      } catch { setError(true); }
      if (!stop) setTimeout(poll, 2000);
    };
    void poll();
    const tick = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => { stop = true; clearInterval(tick); void api.leaveQueue().catch(() => undefined); };
  }, [navigate]);

  return (
    <div className="page">
      <Header subtitle={t.queue.subtitle} />
      <section className="home__col">
        <span className="status">{t.queue.searching}</span>
        <span className="muted">{error ? t.noServer : t.queue.waiting(seconds)}</span>
        <div className="home__actions">
          <button type="button" className="btn btn--secondary btn--block" onClick={() => navigate("/")}>{t.btn.cancel}</button>
        </div>
      </section>
    </div>
  );
}
