import { Link } from "react-router-dom";
import { LANGS, LANG_NAMES, useI18n } from "../i18n";
import { useTheme } from "../theme";
import { MoonIcon, SunIcon } from "./marks";

export function Header({ subtitle, right }: { subtitle?: string; right?: React.ReactNode }) {
  const [theme, toggle] = useTheme();
  const { lang, t, setLang } = useI18n();
  const next = LANGS[(LANGS.indexOf(lang) + 1) % LANGS.length];
  return (
    <header className="header">
      <div>
        <h1 className="header__title"><Link to="/">{t.title}</Link></h1>
        <p className="header__sub">{subtitle ?? t.header.subtitle}</p>
      </div>
      <div className="header__right">
        {right}
        <button type="button" className="theme-link" onClick={() => setLang(next)} lang={next}>
          {LANG_NAMES[next]}
        </button>
        <button type="button" className="theme-link" onClick={toggle}>
          {theme === "light" ? <MoonIcon /> : <SunIcon />}
          {theme === "light" ? t.header.dark : t.header.light}
        </button>
      </div>
    </header>
  );
}
