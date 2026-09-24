# Battleship: neural net + game

The project started as a conversation with Claude on the web and continues
here. This file carries the context over: what has been done, which decisions
were made and why, what has been measured, and where the traps are buried.

## What this is

A convolutional net that plays Battleship. The training core is finished and
works. The browser game and the server are done (`web/`, see `web/README.md`).
Next: the mobile app (`kmp/`) and fine-tuning on real logs.

## Stack and environment

* Python 3.11 (venv). **Not 3.12+ and not 3.14** — PyTorch is not built for them
  on Intel Mac. Development host: macOS Intel.
* `torch==2.2.2` — the last branch with wheels for macOS x86_64.
* numpy, onnx, onnxscript, onnxruntime.

```bash
cd model && source .venv/bin/activate
python -m battleship.train --rounds 8 --games 400 --epochs 3
python -m battleship.inspect_game --ckpt battleship/net.pt --step --compare
python -m battleship.export_onnx        # net.pt → web/frontend/public/model/*.onnx + web/fixtures/onnx.json
python -m battleship.fixtures           # engine fixtures → web/fixtures/engine.json
python -m battleship.analyze --logs logs.jsonl --ckpt battleship/net.pt   # summary of logs from the DB
python -m battleship.analyze --logs /dev/null --stub-heuristic 40 --ckpt battleship/net.pt  # the table below
```

`numpy<2` is mandatory in the venv: torch 2.2.2 does not work with numpy 2.x.

## Layout

```
model/battleship/
  game.py          rules, placement, environment, observation encoding
  agents.py        baselines: random / hunt-target / placement counting
  model.py         the net, NeuralAgent, D4 symmetries
  selfplay.py      dataset generation, measurements
  train.py         training loop (entry point)
  inspect_game.py  a game step by step with the probability map
  telemetry.py     GameLog, Recorder, replay(), validate_placement(), logs_to_dataset()
                   + placement_from_ships / ships_from_placement adapters to the web format
  analysis.py      compare_moves, split_by_phase, games_table, placement_stats
  analyze.py       CLI: summary of JSONL from the DB (+ --stub-heuristic N for the zero level)
  fixtures.py      generator of web/fixtures/engine.json for cross-checking the engines
  export_onnx.py   checkpoint export to ONNX (fp32 / int8) + parity check
  net.pt           trained checkpoint
web/
  frontend/        Vite + React + TS: engine (port of game.py), onnxruntime-web, screens
  frontend/public/model/battleship_int8.onnx   542 KB (fp32 next to it, 1.9 MB, fallback)
  server/          FastAPI: H2H arbiter (WebSocket), telemetry, name moderation, Postgres
  fixtures/        engine.json (200 games from game.py), onnx.json (64 observations)
```

`telemetry.py` and `analysis.py` are the originals from the web conversation; the
`GameLog` format is the canon for analytics (`placement` as `[size, r, c, horizontal]`,
`shooter`/`placer` as `kind:id`, `outcome`, `think_ms`, `client`).

## The key architectural decision

The task is formulated **not** as RL "state → where to shoot" but as supervised
prediction of the posterior map: for each of the 100 cells, the probability that
there is a ship, given everything revealed.

Why:
* labels are free and dense (we place the ships ourselves, so we know the truth);
* a label is a sample from the posterior; BCE over many games converges to the
  marginal probability, i.e. the net approximates Monte Carlo in a single forward;
* the policy comes for free: argmax over unopened cells;
* everything is debuggable by eye via `inspect_game.py`.

RL and search on top of the learned model are a possible development, but starting
with them would be a mistake.

## The net

```
input (8,10,10): not shot / miss / hit-alive / sunk
                 + 4 constant planes "how many ships of size 4/3/2/1 are left"
stem   conv3x3 -> BN -> ReLU (64 channels)
body   6 x ResBlock(conv3x3 x2 + BN + GlobalContext + skip)
head   conv1x1 -> logits 10x10   (sigmoid outside, in NeuralAgent)
~500K parameters
```

Three non-obvious points:
1. **The remaining-fleet planes are mandatory** — without them the net does not
   know whether it is looking for the four-decker or the last single.
2. **Zero padding here is a feature, not a hack** — fewer ships fit near the wall,
   the zeros at the edges signal the border by themselves. Circular padding would
   break the task.
3. **GlobalContext** (average over the board → MLP → add to every cell) gives a
   global summary right away without waiting for the receptive field to grow.
   Limitation: it carries "how many" but not "where" — the spatial work is done
   only by the convolutions.

## What has been measured

Metric — mean number of shots to clear the board. Russian rules: 1x4, 2x3, 3x2,
4x1, touching is forbidden even diagonally, cells around a sunk ship open
automatically.

| agent | mean shots (300 games) |
|---|---|
| random | 75.8 |
| hunt/target with parity | 58.6 |
| placement counting | 55.2 |
| net (4 rounds, ~25 min CPU) | 55.3 |
| net + TTA | 55.1 |
| theoretical minimum | 20 |

The net is **on par** with the heuristic, not better. Training has not converged —
this is a starting point, not a ceiling.

**On noise: σ ≈ 7, on 120 games SEM ≈ 0.65.** Half a shot of difference on such
a measurement is nothing. Measure on 300+ games with a fixed seed. We got burned
once already: on 120 games the net "beat" the heuristic, on 300 it was on par.

Ablation 1 block vs 6 (short training, 3 rounds): 55.19 vs 54.59 — inside the
noise. Depth seems excessive for this task; verify with long training and on
`--fleet classic`.

### Inference performance

| | latency | throughput |
|---|---|---|
| PyTorch, 1 core | 2.06 ms/move | 485 moves/s |
| ONNX Runtime, 1 core | 0.75 ms/move | 1329 moves/s |
| PyTorch, batch 128 | 0.88 ms/move | 1138 moves/s |

One core at one move per 3 s handles ~1500 concurrent games. **The model is not a
bottleneck under any realistic traffic.** Triton/TorchServe are overkill. int8
quantization: 2.1 MB → 595 KB, quality does not suffer (55.16 vs 55.44 on 250 games).

Export (`export_onnx.py`): opset 17, input `obs` [B,8,10,10], output `logits`
[B,10,10], sigmoid outside, BatchNorm folded. Dynamic quantization produces
`ConvInteger` / `MatMulInteger` — the ORT wasm backend handles them. Parity: torch ↔
ORT fp32 1e-6; int8 deviates from fp32 by up to 0.04 in probability, and **the int8
kernels in wasm and in Python differ from each other** (Δ ≈ 0.02) — compare int8
against fp32, not byte for byte.

## Telemetry

The logging unit is **one attacker against one board**. A human-vs-human match =
two logs. This way human, model and heuristic land in one table and compare directly.

We log **the seed, not the states**: placement (`[[idx,…] × 10]`, idx = r*10+c) +
the sequence of shots as indices 0..99. `replay()` restores every frame byte for
byte; `log_to_dataset()` builds training samples in the same format as self-play.
`validate_placement()` is mandatory — the placement comes from the client.

Logs live in Postgres (`game_logs`); export: `web/server/scripts/export_logs.py` →
JSONL in `GameLog` format → `battleship.analyze` / `telemetry.logs_to_dataset()`.
Besides the seed we collect what replay cannot restore: `think_ms` per move (for the
model — inference latency), `started_at`, `client_info` (platform, screen, touch,
placement mode random/manual, model backend — no personal data). In H2H the server
measures this. Unfinished games are written too (`won=null`, `outcome=abandoned` in
the export) — useful for the placement prior, useless for the shots metric; games
played to the end but lost are `outcome=lost`, `games_table` skips them.
h2m logs come from the client and **are not protected from forgery** — hence the
leaderboard is H2H only, where the server is the referee.

### The main analytical trick

Compare **moves, not games**. For every human move, ask the model what it would
play from the same position. 40 games give 2287 comparisons.

Result with a heuristic stub instead of a human:

| | hunt | target |
|---|---|---|
| agreement with the model | 4.9% | 60.9% |
| median rank of the choice | 15 | 0 |
| shooter hit rate | 23.5% | 68.6% |
| model would-hit rate | 36.1% | 76.5% |

The averaged "19% agreement" would hide this picture entirely. Always split by
phase (`split_by_phase`).

## What is honestly broken

* **Placement is not uniform.** `random_placement` is a greedy sequential sampler.
  It covers the set of legal placements unevenly and the net learns exactly this
  prior. Against a human who hugs the edges it will degrade. `placement_stats()`
  already measures this; the cure is fine-tuning on real logs via
  `logs_to_dataset()`. The radical fix is MCMC over configurations.
* **The greedy policy is suboptimal.** Max probability ≠ max information.
* **The net does not know the move history**, only the current picture. Enough for
  this task (the state is Markovian).

## Game rules (fixed for web and mobile)

* Hit or sink — shoot again; miss — the turn passes. So "shots to clear" directly
  decides the outcome.
* The perimeter of a sunk ship opens automatically and **does not count as shots**;
  shooting an already-open cell is a protocol error, not a miss.
* First move — a coin toss.

## Web and server: what is done and where the traps are

* Three implementations of the rules must match byte for byte: `game.py` (reference),
  `web/server/app/rules.py`, `web/frontend/src/engine/rules.ts`. Cross-check — tests
  on `web/fixtures/engine.json`; regenerate the fixtures when the rules change.
* Identity without login: the server issues `player_id` + `secret`, the client keeps
  them in localStorage. The server issues the id, not the client — otherwise anyone
  can claim someone else's id.
* Name moderation — a local stop-list only, with homoglyph normalization. False
  positives are fixed via `allowlist.txt`. Rejected names are not logged.
* H2H matches live in the memory of one process — `uvicorn --workers 1`. Match
  timers finish the match themselves, so `_disarm` never cancels the current task
  (otherwise `game_over` is never sent).
* React StrictMode mounts twice: side effects (AI timer, socket) go only in
  `start()/stop()` and effects, not constructors; in `MatchSocket` the `onclose` of
  a discarded socket must not touch state.
* Import onnxruntime-web as `onnxruntime-web/wasm` (bundle build): the default
  import pulls the JSEP/WebGPU loader. Vite puts the `.wasm` into `assets/` itself (14 MB).

## Plan

1. **Mobile** (`kmp/`): the same ONNX via onnxruntime-mobile / Core ML; the API is
   described in `web/README.md`. The rules engine is a third port — cross-check
   against `web/fixtures/engine.json`.
2. **Fine-tuning on real logs** — closes the placement-prior problem.
   `export_logs.py --attacker model --all` yields human placements.
3. Accumulate real games and look at `analyze` by phase: on the first 27 games
   (mostly e2e scripts, not humans) the target phase already shows a gap of
   0.45 → 0.87 in hit rate.

### Experiments worth running

* `--fleet classic` — without single-deckers the endgame stops being a blind
  search; the gap between the net and the heuristic should grow.
* Long training: `--games 1500 --epochs 6`. The bottleneck is generation (a
  batch-1 forward per move). Vectorize several games in parallel in `selfplay.py` —
  a straightforward change, roughly a tenfold speedup.
* Ablations: `--no-global`, depth, drop the remaining-fleet channels.

## Conventions

* Comments and documentation — in English. Console messages — in Russian.
* UI strings live only in `web/frontend/src/i18n.ts` (English by default, Russian;
  the choice is kept in localStorage `bs.lang`). A new string goes into both
  dictionaries — `ru` is typed as `Dict`, so a missing key fails `tsc`. The e2e
  scripts pin `ru`: their selectors are Russian.
* Back any quality claim with a measurement on 300+ games with a fixed seed. Do not
  trust a difference below 1.5 shots.
* Telemetry: pseudonymous ids, no personal data collected.
