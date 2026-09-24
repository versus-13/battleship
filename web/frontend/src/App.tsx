import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Home } from "./screens/Home";
import { MatchOnline } from "./screens/MatchOnline";
import { PlayLocal } from "./screens/PlayLocal";
import { Queue } from "./screens/Queue";
import { RoomJoin } from "./screens/RoomJoin";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/play" element={<PlayLocal />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/room/:code" element={<RoomJoin />} />
        <Route path="/match/:id" element={<MatchOnline />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
