import { tr } from "../i18n";
import { clearIdentity, loadIdentity, saveIdentity, type Identity } from "./identity";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public body: unknown) {
    super(`${status} ${code}`);
  }
}

export interface Stats {
  games: number; wins: number; win_rate: number | null; avg_shots: number | null; best_shots: number | null;
  h2h_games: number; h2m_games: number; h2h_wins: number;
}
export interface Me { player_id: string; name: string | null; tag: string; stats: Stats | null }
export interface LeaderRow { player_id: string; name: string | null; tag: string; games: number; wins: number; win_rate: number; avg_shots: number | null }
export interface ModelInfo { version: string; url: string }

let identity: Identity | null = loadIdentity();
let registering: Promise<Identity> | null = null;

export function currentIdentity() { return identity; }

export async function ensureIdentity(): Promise<Identity> {
  if (identity) return identity;
  if (!registering) {
    registering = fetch("/api/players", { method: "POST" })
      .then(async (r) => {
        if (!r.ok) throw new ApiError(r.status, "register_failed", await r.text());
        const body = await r.json();
        const id = { playerId: body.player_id, secret: body.secret };
        saveIdentity(id);
        identity = id;
        return id;
      })
      .finally(() => { registering = null; });
  }
  return registering;
}

async function request<T>(method: string, path: string, body?: unknown, auth = true, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) headers.Authorization = `Bearer ${(await ensureIdentity()).secret}`;
  const r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (r.status === 401 && auth && retry) {
    // the server does not know our secret (DB reset) — create a new identity
    clearIdentity(); identity = null;
    return request<T>(method, path, body, auth, false);
  }
  if (r.status === 204) return undefined as T;
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const code = typeof data?.detail === "object" && data?.detail?.code ? data.detail.code : typeof data?.detail === "string" ? data.detail : "error";
    throw new ApiError(r.status, code, data);
  }
  return data as T;
}

export const api = {
  me: () => request<Me>("GET", "/api/players/me"),
  setName: (name: string) => request<{ name: string; tag: string }>("PUT", "/api/players/me/name", { name }),
  clearName: () => request<void>("DELETE", "/api/players/me/name"),
  leaderboard: (minGames = 1) => request<LeaderRow[]>("GET", `/api/leaderboard?min_games=${minGames}&limit=20`, undefined, false),
  model: () => request<ModelInfo>("GET", "/api/model", undefined, false),
  postGames: (payload: unknown) => request<{ accepted: number[]; rejected: unknown[] }>("POST", "/api/games", payload),
  createRoom: () => request<{ match_id: string; code: string; ws_url: string }>("POST", "/api/rooms"),
  roomInfo: (code: string) => request<{ match_id: string; code: string; status: string; host_name: string | null; host_tag: string }>("GET", `/api/rooms/${code}`, undefined, false),
  joinRoom: (code: string) => request<{ match_id: string; ws_url: string }>("POST", `/api/rooms/${code}/join`),
  queue: () => request<{ status: "queued" | "matched"; match_id: string | null; ws_url: string | null }>("POST", "/api/queue"),
  leaveQueue: () => request<void>("DELETE", "/api/queue"),
  currentMatch: () => request<{ match_id: string | null; ws_url?: string; phase?: string; code?: string | null }>("GET", "/api/matches/current"),
};

export function displayName(name: string | null, tag: string) {
  return name ? `${name}#${tag}` : `${tr().player}#${tag}`;
}
