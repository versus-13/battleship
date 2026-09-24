/** The "human vs model" flow: placement → battle. */
import { useEffect, useState } from "react";
import type { Agent } from "../ai/agent";
import { getAgent } from "../ai/loader";
import { Header } from "../components/Header";
import { randomPlacement, type Ships } from "../engine/rules";
import type { PlacementMode } from "../game/telemetry";
import { BattleLocal } from "./BattleLocal";
import { Placement } from "./Placement";

export function PlayLocal() {
  const [ships, setShips] = useState<Ships>(() => randomPlacement());
  const [mode, setMode] = useState<PlacementMode>("random");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [stage, setStage] = useState<"place" | "battle">("place");

  useEffect(() => { void getAgent().then(setAgent); }, []);

  return (
    <div className="page">
      <Header subtitle={agent ? `против модели · ${agent.label}` : "загружаем модель…"} />
      {stage === "place" ? (
        <Placement ships={ships} onChange={(s, m) => { setShips(s); setMode(m); }} onConfirm={() => setStage("battle")} busy={!agent}
          status="Расстановка" statusHint={agent ? undefined : "модель загружается…"} />
      ) : (
        <BattleLocal ships={ships} placement={mode} agent={agent!} onNewGame={() => setStage("place")} />
      )}
    </div>
  );
}
