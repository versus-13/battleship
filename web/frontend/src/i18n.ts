/**
 * UI strings in English (default) and Russian. The choice is kept in localStorage.
 * A module-level store rather than a context: non-React code (displayName) reads it too.
 */
import { useSyncExternalStore } from "react";
import { colOf, rowOf } from "./engine/rules";

export type Lang = "en" | "ru";
export const LANGS: readonly Lang[] = ["en", "ru"];
const KEY = "bs.lang";

const EN_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];
const RU_LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К"];

const en = {
  langName: "English",
  title: "Battleship",
  letters: EN_LETTERS,
  cell: (i: number) => `${EN_LETTERS[colOf(i)]}${rowOf(i) + 1}`,
  player: "Player",
  header: {
    subtitle: "10 × 10 board · a fleet of ten ships",
    dark: "Dark theme",
    light: "Light theme",
  },
  board: {
    mine: "My fleet",
    enemy: "Opponent's board",
    afloat: (n: number, total: number) => `${n} of ${total} afloat`,
    sunk: (n: number, total: number) => `${n} of ${total} sunk`,
    ready: "ready for battle",
    touching: "ships are touching",
  },
  fleet: { enemy: "Enemy fleet" },
  journal: {
    title: "Recent moves",
    empty: "no moves yet",
    you: "You",
    foe: "Opponent",
    results: ["miss", "hit", "sunk"],
    hint: "Cells around a sunk ship get dotted automatically — like pencil marks in the margins.",
  },
  status: {
    win: "Victory",
    winTitle: "Victory!",
    loss: "Defeat",
    aborted: "Match aborted",
    yourTurn: "Your turn",
    over: "game over",
    shoot: "shoot at the opponent's board",
    waiting: "Waiting for an opponent",
  },
  btn: {
    newGame: "New game",
    surrender: "Surrender",
    again: "Play again",
    home: "Home",
    cancel: "Cancel",
    copy: "Copy",
    toBattle: "To battle",
    shuffle: "Shuffle",
    save: "Save",
    join: "Join",
    accept: "Accept challenge",
  },
  placement: {
    status: "Placement",
    hint: "drag a ship to move it, click to rotate",
  },
  local: {
    model: "Model",
    modelTurn: "Model's turn",
    thinking: "the model is thinking…",
    vs: (label: string) => `vs the model · ${label}`,
    loading: "loading the model…",
    loadingHint: "the model is loading…",
    youWon: (shots: number) => `You sank the model's fleet in ${shots} shots.`,
    youLost: (shots: number) => `The model sank your fleet in ${shots} shots.`,
    surrendered: "You surrendered. The model's ships are revealed on its board.",
  },
  home: {
    how: "How shall we play?",
    offline: "server unavailable — only the game against the model works",
    inBrowser: "the model runs right in your browser",
    playModel: "Play the model",
    invite: "Invite a friend",
    findOpponent: "Find an opponent",
    backToMatch: "Back to the match",
    byCode: "Join by room code",
    introduce: "Introduce yourself",
    namePlaceholder: "name or nickname",
    you: (name: string) => `you are ${name} · no login: the id is stored in this browser`,
    stats: "Your stats",
    games: "games",
    gamesValue: (all: number, h2m: number, h2h: number) => `${all} (vs model ${h2m}, vs people ${h2h})`,
    wins: "wins",
    avgShots: "avg shots",
    bestGame: "best game",
    unavailable: "unavailable",
    empty: "nothing yet",
    leaders: "Leaders · human vs human",
    noLeaders: "nobody yet — play with a friend",
    colPlayer: "player",
    colGames: "games",
    colWins: "wins",
    colShots: "avg shots",
    rules: "Rules: 10 × 10 board, fleet 4-3-3-2-2-2-1-1-1-1, ships may not touch, not even at the corners. Hit — shoot again.",
    alreadyInMatch: "you are already in a match",
    roomFailed: "could not create a room",
  },
  nameErrors: {
    too_short: "too short — at least 2 characters",
    too_long: "too long — up to 16 characters",
    invalid_chars: "only letters, digits, space, hyphen and underscore",
    rejected_profanity: "this name won't do, try another one",
    rate_limited: "the name can be changed once every 10 minutes",
  } as Record<string, string>,
  nameSaveFailed: "could not save the name",
  noServer: "no connection to the server",
  online: {
    vs: (name: string) => `vs ${name}`,
    h2h: "human vs human",
    noConnection: "no connection to the server…",
    connecting: "connecting…",
    sendLink: "send your friend the link or the room code",
    placementHint: (s: number, ready: boolean) => `${s} s left · opponent ${ready ? "is ready" : "is placing ships"}`,
    foeTurn: "Opponent's turn",
    foeLeft: "the opponent disconnected, waiting for them to return…",
    foePlacing: "the opponent is placing ships",
    shootTimer: (s: number) => `shoot at the opponent's board · ${s} s`,
    aiming: "the opponent is aiming…",
    reconnecting: "connection lost, reconnecting…",
    reason: (reason: string, youWon: boolean | null): string => ({
      fleet_sunk: youWon ? "You sank the opponent's fleet." : "The opponent sank your fleet.",
      forfeit: youWon ? "The opponent surrendered." : "You surrendered.",
      move_timeout: youWon ? "The opponent didn't move in time." : "You didn't move in time.",
      disconnect: youWon ? "The opponent didn't come back." : "You were disconnected for too long.",
      abandoned: "The match didn't take place.",
    } as Record<string, string>)[reason] ?? "",
  },
  errors: {
    not_your_turn: "it's not your turn", illegal_shot: "this cell has already been shot", bad_placement: "invalid placement",
    wrong_phase: "not allowed right now", no_match: "match not found", not_in_match: "you are not in this match",
  } as Record<string, string>,
  queue: {
    subtitle: "random opponent",
    searching: "Looking for an opponent…",
    waiting: (s: number) => `in the queue for ${s} s · if nobody shows up, invite a friend by link`,
  },
  room: {
    subtitle: "match invitation",
    title: (code: string) => `Room ${code}`,
    invites: (host: string) => `${host} challenges you`,
    busy: "the room is taken or the game is over",
    notFound: "room not found",
    taken: "the room is already taken",
    joinFailed: "could not join",
  },
};

export type Dict = typeof en;

const ru: Dict = {
  langName: "Русский",
  title: "Морской бой",
  letters: RU_LETTERS,
  cell: (i) => `${RU_LETTERS[colOf(i)]}${rowOf(i) + 1}`,
  player: "Игрок",
  header: {
    subtitle: "поле 10 × 10 · флот из десяти кораблей",
    dark: "Тёмная тема",
    light: "Светлая тема",
  },
  board: {
    mine: "Мой флот",
    enemy: "Поле соперника",
    afloat: (n, total) => `уцелело ${n} из ${total}`,
    sunk: (n, total) => `потоплено ${n} из ${total}`,
    ready: "готово к бою",
    touching: "корабли касаются",
  },
  fleet: { enemy: "Флот соперника" },
  journal: {
    title: "Последние ходы",
    empty: "ходов пока нет",
    you: "Вы",
    foe: "Соперник",
    results: ["мимо", "ранил", "убил"],
    hint: "Клетки вокруг убитого корабля помечаются точками сами — как карандашом на полях.",
  },
  status: {
    win: "Победа",
    winTitle: "Победа!",
    loss: "Поражение",
    aborted: "Матч прерван",
    yourTurn: "Ваш ход",
    over: "партия окончена",
    shoot: "стреляйте по полю соперника",
    waiting: "Ждём соперника",
  },
  btn: {
    newGame: "Новая игра",
    surrender: "Сдаться",
    again: "Ещё раз",
    home: "На главную",
    cancel: "Отменить",
    copy: "Копировать",
    toBattle: "К бою",
    shuffle: "Перемешать",
    save: "Сохранить",
    join: "Войти",
    accept: "Принять вызов",
  },
  placement: {
    status: "Расстановка",
    hint: "перетащите корабль — перенос, клик — поворот",
  },
  local: {
    model: "Модель",
    modelTurn: "Ход модели",
    thinking: "модель думает…",
    vs: (label) => `против модели · ${label}`,
    loading: "загружаем модель…",
    loadingHint: "модель загружается…",
    youWon: (shots) => `Вы потопили флот модели за ${shots} выстрелов.`,
    youLost: (shots) => `Модель потопила ваш флот за ${shots} выстрелов.`,
    surrendered: "Вы сдались. Корабли модели раскрыты на её поле.",
  },
  home: {
    how: "Как играем?",
    offline: "сервер недоступен — доступна только игра с моделью",
    inBrowser: "модель считается прямо в браузере",
    playModel: "Играть с моделью",
    invite: "Позвать друга",
    findOpponent: "Найти соперника",
    backToMatch: "Вернуться в матч",
    byCode: "По коду комнаты",
    introduce: "Представиться",
    namePlaceholder: "имя или ник",
    you: (name) => `вы — ${name} · без логина: id хранится в этом браузере`,
    stats: "Ваша статистика",
    games: "партий",
    gamesValue: (all, h2m, h2h) => `${all} (с моделью ${h2m}, с людьми ${h2h})`,
    wins: "побед",
    avgShots: "ср. выстрелов",
    bestGame: "лучшая партия",
    unavailable: "недоступна",
    empty: "пока пусто",
    leaders: "Лидеры · человек против человека",
    noLeaders: "пока никого — сыграйте с другом",
    colPlayer: "игрок",
    colGames: "партий",
    colWins: "побед",
    colShots: "ср. выстр.",
    rules: "Правила: поле 10 × 10, флот 4-3-3-2-2-2-1-1-1-1, корабли не касаются даже углами. Попал — стреляешь снова.",
    alreadyInMatch: "вы уже в матче",
    roomFailed: "не удалось создать комнату",
  },
  nameErrors: {
    too_short: "слишком коротко — от 2 символов",
    too_long: "слишком длинно — до 16 символов",
    invalid_chars: "только буквы, цифры, пробел, дефис и подчёркивание",
    rejected_profanity: "такое имя не подходит, попробуйте другое",
    rate_limited: "имя можно менять раз в 10 минут",
  },
  nameSaveFailed: "не удалось сохранить имя",
  noServer: "нет связи с сервером",
  online: {
    vs: (name) => `против ${name}`,
    h2h: "человек против человека",
    noConnection: "нет связи с сервером…",
    connecting: "подключаемся…",
    sendLink: "отправьте другу ссылку или код комнаты",
    placementHint: (s, ready) => `осталось ${s} с · соперник ${ready ? "готов" : "расставляет"}`,
    foeTurn: "Ход соперника",
    foeLeft: "соперник отключился, ждём возвращения…",
    foePlacing: "соперник расставляет корабли",
    shootTimer: (s) => `стреляйте по полю соперника · ${s} с`,
    aiming: "соперник целится…",
    reconnecting: "связь потеряна, переподключаемся…",
    reason: (reason, youWon) => ({
      fleet_sunk: youWon ? "Вы потопили флот соперника." : "Соперник потопил ваш флот.",
      forfeit: youWon ? "Соперник сдался." : "Вы сдались.",
      move_timeout: youWon ? "Соперник не сделал ход вовремя." : "Вы не сделали ход вовремя.",
      disconnect: youWon ? "Соперник не вернулся в игру." : "Вы отключились слишком надолго.",
      abandoned: "Матч не состоялся.",
    } as Record<string, string>)[reason] ?? "",
  },
  errors: {
    not_your_turn: "сейчас не ваш ход", illegal_shot: "в эту клетку уже стреляли", bad_placement: "расстановка неверна",
    wrong_phase: "сейчас нельзя", no_match: "матч не найден", not_in_match: "вы не участник этого матча",
  },
  queue: {
    subtitle: "случайный соперник",
    searching: "Ищем соперника…",
    waiting: (s) => `в очереди ${s} с · можно позвать друга по ссылке, если никого нет`,
  },
  room: {
    subtitle: "приглашение в матч",
    title: (code) => `Комната ${code}`,
    invites: (host) => `вас зовёт ${host}`,
    busy: "комната уже занята или игра закончилась",
    notFound: "комната не найдена",
    taken: "комната уже занята",
    joinFailed: "не удалось войти",
  },
};

const DICTS: Record<Lang, Dict> = { en, ru };
/** Each language named in itself — for the switcher. */
export const LANG_NAMES: Record<Lang, string> = { en: en.langName, ru: ru.langName };

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "en" || saved === "ru") return saved;
  } catch { /* private mode */ }
  return "en";
}

let lang: Lang = initialLang();
const listeners = new Set<() => void>();

function applyLang(l: Lang) {
  document.documentElement.lang = l;
  document.title = DICTS[l].title;
}

export function initLang() { applyLang(lang); }

export function setLang(l: Lang) {
  if (l === lang) return;
  lang = l;
  try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
  applyLang(l);
  listeners.forEach((fn) => fn());
}

/** Strings of the current language outside React. Components use useI18n() to re-render on change. */
export function tr(): Dict { return DICTS[lang]; }

const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };

export function useI18n() {
  const l = useSyncExternalStore(subscribe, () => lang);
  return { lang: l, t: DICTS[l], setLang };
}
