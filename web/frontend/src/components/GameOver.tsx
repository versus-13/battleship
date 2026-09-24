export function GameOver(p: { title: string; text: string; primary: string; onPrimary: () => void; secondary?: string; onSecondary?: () => void }) {
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="overlay__card">
        <h2 className="overlay__title">{p.title}</h2>
        <p className="muted" style={{ fontSize: 13 }}>{p.text}</p>
        <div className="panel__buttons">
          <button type="button" className="btn btn--block" onClick={p.onPrimary}>{p.primary}</button>
          {p.secondary && <button type="button" className="btn btn--secondary btn--block" onClick={p.onSecondary}>{p.secondary}</button>}
        </div>
      </div>
    </div>
  );
}
