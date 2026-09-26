import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import { flushOutbox } from "./game/telemetry";
import { initLang } from "./i18n";
import { applyTheme, initialTheme } from "./theme";

applyTheme(initialTheme());
initLang();
void flushOutbox();          // logs left unsent last time (e.g. the server was being updated)
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
