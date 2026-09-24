/** Player identity: server-issued id and secret in localStorage. No login, no personal data. */
const KEY = "bs.identity";

export interface Identity { playerId: string; secret: string }

export function loadIdentity(): Identity | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    if (typeof v?.playerId === "string" && typeof v?.secret === "string") return v;
  } catch { /* ignore */ }
  return null;
}

export function saveIdentity(id: Identity) {
  try { localStorage.setItem(KEY, JSON.stringify(id)); } catch { /* ignore */ }
}

export function clearIdentity() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
