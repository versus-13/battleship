import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import { initLang } from "./i18n";
import { applyTheme, initialTheme } from "./theme";

applyTheme(initialTheme());
initLang();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
