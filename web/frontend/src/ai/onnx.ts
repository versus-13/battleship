/**
 * Net inference in the browser via onnxruntime-web (wasm).
 * Input obs float32 [1,8,10,10], output logits [1,10,10]; the sigmoid is applied here.
 */
import * as ort from "onnxruntime-web/wasm";
import { CELLS } from "../engine/rules";

export interface Predictor {
  readonly version: string;
  predict(obs: Float32Array): Promise<Float32Array>;
}

let ortConfigured = false;
function configureOrt() {
  if (ortConfigured) return;
  ortConfigured = true;
  // the ORT bundle build knows where its .wasm is (vite puts it into assets/)
  ort.env.wasm.numThreads = 1;
}

export async function loadOnnx(source: string | Uint8Array, version: string): Promise<Predictor> {
  configureOrt();
  const session = await ort.InferenceSession.create(source as string, { executionProviders: ["wasm"] });
  const inputName = session.inputNames[0];
  const outputName = session.outputNames[0];
  return {
    version,
    async predict(obs) {
      const feeds = { [inputName]: new ort.Tensor("float32", obs, [1, 8, 10, 10]) };
      const out = await session.run(feeds);
      const logits = out[outputName].data as Float32Array;
      const p = new Float32Array(CELLS);
      for (let i = 0; i < CELLS; i++) p[i] = 1 / (1 + Math.exp(-logits[i]));
      return p;
    },
  };
}
