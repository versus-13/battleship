"""
Training loop.

Each round:
  1) play N games with the current policy (+ noise and baselines mixed in),
     recording the states;
  2) fine-tune the net on the buffer of the last rounds;
  3) measure the mean number of shots with the greedy policy.

Run:
    python -m battleship.train --rounds 8 --games 400 --epochs 3
"""
from __future__ import annotations

import argparse
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn

from .game import Rules, RUSSIAN_FLEET, CLASSIC_FLEET
from .agents import RandomAgent, HuntTargetAgent, ProbabilityAgent, EpsilonMix
from .model import BattleshipNet, NeuralAgent, dihedral
from .selfplay import Dataset, generate, evaluate, print_table


def augment_batch(obs, tgt, msk, rng):
    """A random D4 symmetry over the whole batch (one k per sample)."""
    ks = rng.integers(0, 8, size=len(obs))
    o = np.stack([np.ascontiguousarray(dihedral(obs[i], int(k))) for i, k in enumerate(ks)])
    t = np.stack([np.ascontiguousarray(dihedral(tgt[i], int(k))) for i, k in enumerate(ks)])
    m = np.stack([np.ascontiguousarray(dihedral(msk[i], int(k))) for i, k in enumerate(ks)])
    return o, t, m


def train_epoch(net, opt, ds: Dataset, batch_size, device, rng, augment=True):
    net.train()
    lossf = nn.BCEWithLogitsLoss(reduction="none")
    order = rng.permutation(len(ds))
    total, nb = 0.0, 0
    for i in range(0, len(order) - batch_size + 1, batch_size):
        sel = order[i:i + batch_size]
        o, t, m = ds.obs[sel], ds.target[sel], ds.mask[sel]
        if augment:
            o, t, m = augment_batch(o, t, m, rng)
        o = torch.from_numpy(o).to(device)
        t = torch.from_numpy(t).to(device)
        m = torch.from_numpy(m).to(device)

        logits = net(o)
        loss = (lossf(logits, t) * m).sum() / m.sum().clamp(min=1.0)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        total += loss.detach().item()
        nb += 1
    return total / max(nb, 1)


@torch.no_grad()
def masked_metrics(net, ds: Dataset, device, limit=4096):
    """How well the net estimates the probability in unknown cells."""
    net.eval()
    n = min(limit, len(ds))
    o = torch.from_numpy(ds.obs[:n]).to(device)
    t = torch.from_numpy(ds.target[:n]).to(device)
    m = torch.from_numpy(ds.mask[:n]).to(device)
    p = torch.sigmoid(net(o))
    brier = (((p - t) ** 2) * m).sum() / m.sum()
    # "top-1 accuracy": the most confident unknown cell really contains a ship
    p_masked = torch.where(m > 0, p, torch.full_like(p, -1.0)).flatten(1)
    idx = p_masked.argmax(1)
    hit = t.flatten(1).gather(1, idx[:, None]).mean()
    return float(brier), float(hit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--games", type=int, default=400, help="партий на итерацию")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--blocks", type=int, default=6)
    ap.add_argument("--no-global", action="store_true")
    ap.add_argument("--buffer-rounds", type=int, default=4)
    ap.add_argument("--keep-prob", type=float, default=0.35)
    ap.add_argument("--eval-games", type=int, default=150)
    ap.add_argument("--epsilon", type=float, default=0.08)
    ap.add_argument("--fleet", choices=["ru", "classic"], default="ru")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="net.pt")
    args = ap.parse_args()

    rules = Rules(fleet=RUSSIAN_FLEET if args.fleet == "ru" else CLASSIC_FLEET)
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    device = args.device

    net = BattleshipNet(rules.obs_channels, args.width, args.blocks,
                        use_global=not args.no_global).to(device)
    nparam = sum(p.numel() for p in net.parameters())
    print(f"поле {rules.size}x{rules.size}, флот {rules.fleet}, "
          f"каналов {rules.obs_channels}, параметров {nparam/1e3:.0f}K, device={device}")

    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.rounds)
    buffer = deque(maxlen=args.buffer_rounds)

    print("\nбейзлайны:")
    print_table([evaluate(rules, a, args.eval_games, rng)
                 for a in (RandomAgent(rng), HuntTargetAgent(rng), ProbabilityAgent(rng))])
    print()

    for rnd in range(args.rounds):
        t0 = time.time()
        if rnd == 0:
            # cold start: there is no own policy yet
            behavior = EpsilonMix(
                [HuntTargetAgent(rng), ProbabilityAgent(rng), RandomAgent(rng)],
                [0.5, 0.3, 0.2], rng)
        else:
            behavior = EpsilonMix(
                [NeuralAgent(net, device, rng, epsilon=args.epsilon),
                 NeuralAgent(net, device, rng, temperature=0.05),
                 RandomAgent(rng)],
                [0.6, 0.3, 0.1], rng)

        ds, beh_shots = generate(rules, behavior, args.games, rng, keep_prob=args.keep_prob)
        buffer.append(ds)
        train_ds = Dataset.concat(list(buffer))

        for _ in range(args.epochs):
            loss = train_epoch(net, opt, train_ds, args.batch, device, rng)
        sched.step()

        brier, top1 = masked_metrics(net, ds, device)
        greedy = evaluate(rules, NeuralAgent(net, device, rng), args.eval_games, rng)
        print(f"round {rnd:>2} | состояний {len(train_ds):>6} | loss {loss:.4f} | "
              f"brier {brier:.4f} | top1 {top1:.3f} | "
              f"выстрелов(жадно) {greedy['mean']:.2f} | "
              f"поведение {beh_shots:.1f} | {time.time()-t0:.0f}s", flush=True)

        torch.save({"state_dict": net.state_dict(),
                    "rules": rules,
                    "width": args.width, "blocks": args.blocks,
                    "use_global": not args.no_global}, args.out)

    print("\nитог:")
    final = [evaluate(rules, ProbabilityAgent(rng), args.eval_games * 2, rng),
             evaluate(rules, NeuralAgent(net, device, rng), args.eval_games * 2, rng),
             evaluate(rules, NeuralAgent(net, device, rng, tta=True), args.eval_games * 2, rng)]
    final[2]["agent"] = "neural+TTA"
    print_table(final)
    print(f"\nвеса сохранены в {args.out}")


if __name__ == "__main__":
    main()
