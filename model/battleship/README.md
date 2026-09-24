# Battleship: the experimental core

A fully working skeleton: rules, environment, three baselines, a convolutional
net, self-play data generation, training and a visual inspector.

```
battleship/
  game.py          rules, placement, environment, observation encoding
  agents.py        random / hunt-target / placement counting
  model.py         the net + NeuralAgent + D4 symmetries
  selfplay.py      dataset generation, quality measurement
  train.py         training loop (entry point)
  inspect_game.py  a game step by step with the probability map
```

```bash
pip install torch numpy
python -m battleship.train --rounds 8 --games 400 --epochs 3
python -m battleship.inspect_game --ckpt net.pt --step
```

---

## The main architectural decision

It is tempting to formulate the task as RL: "state → where to shoot", reward
for a hit. It can be done, but it is the worst entry into the topic: the signal
is sparse, the episode is long, credit assignment is murky, training takes hours
and it is unclear what broke.

There is a much nicer construction. We place the ships **ourselves**, so for any
state we know the truth. Therefore we learn not a policy but a **posterior map**:

> for each of the 100 cells — the probability that there is a ship, given
> everything revealed so far

This is an ordinary supervised task with per-pixel BCE. Properties:

* **Labels are free and dense.** One game ≈ 50 states × 100 labels. 400 games
  per round is millions of training signals.
* **The target is a sample, the answer is the mean.** Within one game the label
  of a cell is 0/1, a single sample from the posterior. BCE over many games
  converges to the marginal probability. So the net learns to approximate the
  result of Monte Carlo, but in a single forward pass.
* **The policy comes for free**: argmax of probability over unopened cells.
* **Debugging by eye.** The probability map can be printed and you immediately
  see what the net understood and what it did not (`inspect_game.py`).

### The net

Fully convolutional, no downsampling — the board is 10×10, there is no
resolution to lose.

```
input (8, 10, 10)
  0  not shot
  1  miss (or an empty cell opened automatically around a sunk ship)
  2  hit but not sunk            <- the most informative channel
  3  sunk
  4..7 how many ships of size 4/3/2/1 are left (constant planes)

stem   conv3x3 -> BN -> ReLU            (64 channels)
body   6 × ResBlock(conv3x3 ×2 + BN + GlobalContext)
head   conv1x1 -> 1 channel = 10×10 logits
```

Three points that are not obvious:

1. **The remaining-fleet planes are mandatory.** Without them the net does not
   know whether it is looking for the four-decker or the last single — and those
   are completely different maps. A scalar "smeared" as a constant over the whole
   board: cheap and it works.

2. **The edges of the board carry information** — fewer ships fit near the
   wall. So zero padding here is not a hack but a feature: the zeros at the
   edges signal the border by themselves. Circular padding would break the task.

3. **`GlobalContext`.** A 3×3 convolution sees locally; the receptive field grows
   by 2 cells per layer. But the reasoning "4 ship cells left among 30 unopened"
   is global. The block averages features over the board, runs them through an
   MLP and adds them back to every cell. A couple of lines, and the net starts
   counting noticeably better. Try `--no-global` and compare.

### Where the states come from

A subtlety people usually trip over. The distribution of states depends on who
played. If you train on games of a random agent, the net never sees the
positions that arise for a strong player — and those are exactly where it has
to work.

Hence a DAgger-like loop: in round zero the data is collected by heuristics,
afterwards by the **current net** with ε-noise and baselines mixed in. The
buffer keeps the last `--buffer-rounds` rounds so as not to forget.

### Augmentation

The board is symmetric under the dihedral group D4 — 8 transforms. That is a
free eightfold increase of data and a strong hint to the net about the structure
of the task. At inference the same 8 transforms can be averaged
(`NeuralAgent(..., tta=True)`).

---

## Baselines

Metric — mean number of shots to clear the board completely (Russian rules: 1×4,
2×3, 3×2, 4×1, touching forbidden even diagonally, cells around a sunk ship open
automatically).

| agent | mean shots (300 games) |
|---|---|
| random | 75.8 |
| hunt/target with parity | 58.6 |
| placement counting | 55.2 |
| net (4 rounds, ~25 min CPU) | 55.3 |
| net + TTA | 55.1 |
| theoretical minimum | 20 |

**On measurement noise.** σ here is ≈ 7 shots, so on 120 games the standard
error of the mean is ≈ 0.65. Half a shot of difference on such a measurement is
nothing. The attached checkpoint showed 54.65 on 120 games and "beat" the
heuristic; on 300 games it turned out to be on par. Measure on 300+ games with
a fixed seed, otherwise you will be chasing ghosts — this is perhaps the most
useful lesson in the whole repository.

`placement_heatmap` is the classic: enumerate all legal positions of every
remaining ship and count how many of them cover a cell. It honours the no-touch
rule (if a known ship cell next to a position is not part of the position
itself, the position is impossible). Weak spot: ships are counted independently,
which is false. That dependence is exactly what the net can learn.

The ~55 threshold is low not because the agents are bad, but because the four
single-deckers in the endgame are almost impossible to search for — there the
task is close to a blind search. With the Hasbro fleet (`--fleet classic`, no
single-deckers) the picture is quite different and the gap between the
heuristic and the net is more visible.

---

## What is worth playing with

Quick experiments, each answers a concrete question:

* `--no-global` — how much does the global context give?
* `--blocks 2` vs `--blocks 10` — where does depth saturate?
* Remove channels 4..7 (remaining fleet) — how much does it degrade?
* `--buffer-rounds 1` — watch the net forget and oscillate.
* Collect data only with `RandomAgent` — the classic distribution-shift demo:
  great loss, plays badly.
* `--fleet classic` — different fleet structure, different optimum.
* TTA is on in the final table — measure how much it really gives.

## What is honestly broken here

* **Placement is not uniform.** `random_placement` is a greedy sequential
  sampler: big ships first, a random valid position. It covers the set of all
  legal placements unevenly, and the net will learn exactly that prior. Against
  a human who likes to hug the edges it will degrade. The honest way is MCMC
  over configurations or weighted rejection sampling; a good standalone project.
* **The net does not know the move history**, only the current picture. Enough
  for this task (the state is Markovian), but if you add an adapting opponent it
  stops being so.
* **The greedy policy is suboptimal.** Max probability ≠ max information. It is
  sometimes better to shoot where the answer narrows the hypothesis space more.
  This is where RL or search on top of the learned model honestly asks to be
  used — but that is not where to start.
