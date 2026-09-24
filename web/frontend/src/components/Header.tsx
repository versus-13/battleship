import { Link } from "react-router-dom";
import { useTheme } from "../theme";
import { MoonIcon, SunIcon } from "./marks";

export function Header({ subtitle = "поле 10 × 10 · флот из десяти кораблей", right }: { subtitle?: string; right?: React.ReactNode }) {
  const [theme, toggle] = useTheme();
  return (
    <header className="header">
      <div>
        <h1 className="header__title"><Link to="/">Морской бой</Link></h1>
        <p className="header__sub">{subtitle}</p>
      </div>
      <div className="header__right">
        {right}
        <button type="button" className="theme-link" onClick={toggle}>
          {theme === "light" ? <MoonIcon /> : <SunIcon />}
          {theme === "light" ? "Тёмная тема" : "Светлая тема"}
        </button>
      </div>
    </header>
  );
}
