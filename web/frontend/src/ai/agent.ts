/**
 * Policy on top of the probability map: argmax over unopened cells,
 * random choice among ties (NeuralAgent.act in model.py).
 */
import { Board, CELLS, type Rng } from "../engine/rules";
import { heuristicScores } from "./heuristic";
import type { Predictor } from "./onnx";

export interface Agent {
  readonly label: string;
  /** Pick a cell to shoot at on the board (the one under fire). */
  choose(board: Board): Promise<number>;
  /** Probability map for debugging/highlighting, if available. */
  probs?(board: Board): Promise<Float32Array>;
}

export function argmaxUnknown(p: Float32Array, board: Board, rng: Rng = Math.random): number {
  let best = -1;
  for (let i = 0; i < CELLS; i++) if (!board.known[i] && p[i] > best) best = p[i];
  const cand: number[] = [];
  for (let i = 0; i < CELLS; i++) if (!board.known[i] && p[i] >= best - 1e-9) cand.push(i);
  return cand[Math.floor(rng() * cand.length)];
}

export function neuralAgent(predictor: Predictor, rng: Rng = Math.random): Agent {
  return {
    label: `model:${predictor.version}`,
    probs: (board) => predictor.predict(board.observation()),
    async choose(board) {
      const p = await predictor.predict(board.observation());
      return argmaxUnknown(p, board, rng);
    },
  };
}

export function heuristicAgent(rng: Rng = Math.random): Agent {
  return {
    label: "heuristic:hunt-target",
    async choose(board) {
      return argmaxUnknown(heuristicScores(board), board, rng);
    },
  };
}
