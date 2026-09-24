import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadOnnx } from "../src/ai/onnx";
import { argmaxUnknown } from "../src/ai/agent";
import { Board } from "../src/engine/rules";

const fx = JSON.parse(readFileSync(new URL("../../fixtures/onnx.json", import.meta.url), "utf8"));

async function check(file: string, key: "p_fp32" | "p_int8", tol: number) {
  const bytes = new Uint8Array(readFileSync(new URL(`../public/model/${file}`, import.meta.url)));
  const model = await loadOnnx(bytes, "test");
  let maxDiff = 0;
  for (const c of fx.cases) {
    const p = await model.predict(Float32Array.from(c.obs));
    for (let i = 0; i < 100; i++) maxDiff = Math.max(maxDiff, Math.abs(p[i] - c[key][i]));
  }
  expect(maxDiff).toBeLessThan(tol);
  return maxDiff;
}

describe("onnx in wasm matches ORT in Python", () => {
  it("fp32", async () => {
    const d = await check(fx.model_fp32.file, "p_fp32", 1e-4);
    console.log("fp32 max|Δp| =", d);
  });
  it("int8 (dynamic quantization: wasm and Python kernels differ, compare against fp32)", async () => {
    const d = await check(fx.model_int8.file, "p_fp32", 0.06);
    console.log("int8 vs fp32 max|Δp| =", d);
  });
  it("the policy picks an unopened cell", async () => {
    const bytes = new Uint8Array(readFileSync(new URL(`../public/model/${fx.model_int8.file}`, import.meta.url)));
    const model = await loadOnnx(bytes, "test");
    const board = new Board([[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]);
    board.shoot(0);
    const p = await model.predict(board.observation());
    const pick = argmaxUnknown(p, board);
    expect(board.known[pick]).toBe(0);
    expect([1, 10]).toContain(pick);   // after a hit in the corner the net should finish off a neighbour
  });
});
