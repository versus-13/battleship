/** Routing with the language prefix: / is English, /ru/ is Russian (see initLang in i18n.ts). */
import { useCallback, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigate, type NavigateOptions } from "react-router-dom";
import { langOfPath, rememberLang, setLang, stripLang, useI18n, withLang, type Lang } from "./i18n";

/** Keeps the i18n store in step with the URL (language switch, back/forward). */
export function LangSync() {
  const { pathname } = useLocation();
  useLayoutEffect(() => setLang(langOfPath(pathname)), [pathname]);
  return null;
}

/** A path in the current language: lp("/play") is /ru/play on the Russian site. */
export function useLangPath() {
  const { lang } = useI18n();
  return useCallback((path: string) => withLang(lang, path), [lang]);
}

/**
 * useNavigate that keeps the language prefix. Its identity is stable: effects depend on it
 * (Queue leaves the queue in cleanup), and a language switch must not re-run them.
 */
export function useLangNavigate() {
  const navigate = useNavigate();
  const { lang } = useI18n();
  const latest = useRef({ navigate, lang });
  latest.current = { navigate, lang };
  return useCallback((to: string, opts?: NavigateOptions) => {
    const { navigate, lang } = latest.current;
    void navigate(withLang(lang, to), opts);
  }, []);
}

/** The same screen in another language; the choice is remembered. */
export function useSwitchLang() {
  const navigate = useNavigate();
  const loc = useLocation();
  return (l: Lang) => {
    rememberLang(l);
    void navigate(withLang(l, stripLang(loc.pathname)) + loc.search + loc.hash, { replace: true, state: loc.state });
  };
}
