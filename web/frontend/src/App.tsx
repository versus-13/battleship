import { BrowserRouter, Route, Routes } from "react-router-dom";
import { LangSync } from "./langRoute";
import { Home } from "./screens/Home";
import { MatchOnline } from "./screens/MatchOnline";
import { PlayLocal } from "./screens/PlayLocal";
import { Queue } from "./screens/Queue";
import { RoomJoin } from "./screens/RoomJoin";

// every screen also lives under /ru/: the same route, so a language switch keeps the screen's state
export function App() {
  return (
    <BrowserRouter>
      <LangSync />
      <Routes>
        <Route path="/ru?" element={<Home />} />
        <Route path="/ru?/play" element={<PlayLocal />} />
        <Route path="/ru?/queue" element={<Queue />} />
        <Route path="/ru?/room/:code" element={<RoomJoin />} />
        <Route path="/ru?/match/:id" element={<MatchOnline />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
