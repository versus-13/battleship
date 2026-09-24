/** Load the model once per page: int8 → fp32 → heuristic. */
import { api } from "../api/client";
import { heuristicAgent, neuralAgent, type Agent } from "./agent";
import { loadOnnx } from "./onnx";

let cached: Promise<Agent> | null = null;

export function getAgent(): Promise<Agent> {
  if (!cached) cached = load();
  return cached;
}

async function load(): Promise<Agent> {
  let url = "/model/battleship_int8.onnx", version = "int8";
  try {
    const info = await api.model();
    url = info.url; version = info.version;
  } catch { /* server unavailable — play with the local model */ }
  try {
    return neuralAgent(await loadOnnx(url, version));
  } catch (e) {
    console.warn("int8-модель не загрузилась, пробуем fp32", e);
  }
  try {
    return neuralAgent(await loadOnnx("/model/battleship.onnx", "fp32"));
  } catch (e) {
    console.error("ONNX недоступен, играет эвристика", e);
    return heuristicAgent();
  }
}
