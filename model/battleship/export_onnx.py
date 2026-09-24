"""
Checkpoint export to ONNX for the browser and the mobile app.

    python -m battleship.export_onnx --ckpt battleship/net.pt --out ../web/frontend/public/model

Writes battleship.onnx (fp32) and battleship_int8.onnx (dynamic weight quantization),
checks torch / ORT fp32 / ORT int8 on real observations and saves them as a
fixture for the TS inference tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import onnxruntime as ort
import torch

from .agents import HuntTargetAgent
from .game import Game
from .inspect_game import load


def collect_observations(rules, n: int, seed: int) -> np.ndarray:
    """n observations from heuristic games: real positions, not noise."""
    rng = np.random.default_rng(seed)
    agent = HuntTargetAgent(rng)
    obs = []
    while len(obs) < n:
        game = Game(rules, rng)
        while not game.done and len(obs) < n:
            if rng.random() < 0.15:
                obs.append(game.observation())
            r, c = agent.act(game)
            game.shoot(r, c)
    return np.stack(obs).astype(np.float32)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def run_ort(path: str, obs: np.ndarray) -> np.ndarray:
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    (inp,) = sess.get_inputs()
    (out,) = sess.run(None, {inp.name: obs})
    return sigmoid(out)


def sha256_short(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="battleship/net.pt")
    ap.add_argument("--out", default="../web/frontend/public/model")
    ap.add_argument("--fixtures", default="../web/fixtures/onnx.json")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    net, rules = load(args.ckpt)
    fp32_path = os.path.join(args.out, "battleship.onnx")
    int8_path = os.path.join(args.out, "battleship_int8.onnx")

    dummy = torch.zeros(1, rules.obs_channels, rules.size, rules.size)
    torch.onnx.export(
        net, dummy, fp32_path,
        opset_version=17,
        input_names=["obs"], output_names=["logits"],
        dynamic_axes={"obs": {0: "batch"}, "logits": {0: "batch"}},
        do_constant_folding=True,
    )

    from onnxruntime.quantization import quantize_dynamic, QuantType
    quantize_dynamic(fp32_path, int8_path, weight_type=QuantType.QUInt8)

    obs = collect_observations(rules, args.n, args.seed)
    with torch.no_grad():
        p_torch = sigmoid(net(torch.from_numpy(obs)).numpy())
    p_fp32 = run_ort(fp32_path, obs)
    p_int8 = run_ort(int8_path, obs)

    print(f"fp32: {os.path.getsize(fp32_path)/1024:.0f} КБ, sha {sha256_short(fp32_path)}")
    print(f"int8: {os.path.getsize(int8_path)/1024:.0f} КБ, sha {sha256_short(int8_path)}")
    print(f"max|Δp| torch vs ORT fp32: {np.abs(p_torch - p_fp32).max():.2e}")
    print(f"max|Δp| torch vs ORT int8: {np.abs(p_torch - p_int8).max():.2e}")

    os.makedirs(os.path.dirname(args.fixtures), exist_ok=True)
    fixtures = {
        "model_fp32": {"file": "battleship.onnx", "sha256_8": sha256_short(fp32_path)},
        "model_int8": {"file": "battleship_int8.onnx", "sha256_8": sha256_short(int8_path)},
        "input": {"name": "obs", "shape": [1, rules.obs_channels, rules.size, rules.size]},
        "output": {"name": "logits", "shape": [1, rules.size, rules.size]},
        "cases": [
            {
                "obs": [round(float(v), 6) for v in obs[i].ravel()],
                "p_fp32": [round(float(v), 6) for v in p_fp32[i].ravel()],
                "p_int8": [round(float(v), 6) for v in p_int8[i].ravel()],
            }
            for i in range(len(obs))
        ],
    }
    with open(args.fixtures, "w") as f:
        json.dump(fixtures, f, separators=(",", ":"))
    print(f"фикстура: {args.fixtures} ({len(obs)} наблюдений)")


if __name__ == "__main__":
    main()
