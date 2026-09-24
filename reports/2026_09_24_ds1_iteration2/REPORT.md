# DS1 iteration-2 local geographic refinement

## Sealed protocol and current result state

`iteration2-inference-manifest.json` is sealed as
`sha256:082fa1140ee0a5ebc0ddecb3554fe005904ae9d0bce50b341f28bf818677997e`.
The stage-1 one-hour manifest is sealed as
`sha256:293d49c39ef1acb84854c3f557ab34df2663a3b80273bcc7c9ba1fba4d2a8d5d`.
The post-seal evaluator verified both manifests, all task-to-stage-1 bindings,
and all eight stage-1 artifact seals before inspecting the expected iteration-2
paths.

All 16 manifest tasks are TRAIN-only, retain all qualified observations, and
forbid within-track holdout. Their local search is fixed at a 25 km radius,
with geographic levels `6.25, 3.125, 1.5625, 0.78125, 0.390625 km`. Each
task's four-point timing stencil is tau zero plus its sealed stage-1 winner and
the winner's `+/-0.25 s` neighbours. This is the inference contract; it was
not regenerated or changed by evaluation.

| Method | Complete / 8 | 1-scan error, median (range) | 6-scan error, median (range) | Seed-to-final displacement, median (range) | Timing / elapsed / grid diagnostic |
|---|---:|---|---|---|---|
| Global time | 8 / 8 | 18.362 km (6.768–29.992) | **3.912 km** (**1.689**–6.055) | 3.500 km (0.391–6.652) | 5/8 timing-stencil edges; 0/8 geographic boundaries; 85.866–512.997 s |
| Regularized per-scan time | 8 / 8 | 18.362 km (6.768–29.992) | 3.995 km (2.176–6.579) | 3.417 km (0.873–6.652) | 8/8 timing-stencil edges; 0/8 geographic boundaries; 73.453–520.298 s |

All **16/16** declared result JSON files validate as sealed, complete,
TRAIN-only, full-observation results with zero held-out observations. Only then
did the offline evaluator introduce the Sausalito reference coordinate for
errors. No inference artifact, runner, or task manifest was modified.

## Stage-1 sources and iteration-2 result matrix

The eight sealed source artifacts are:

| Stage-1 task | SHA-256 |
|---|---|
| `one-hour--train-20260921_00--first-singleton--reno--global_time` | `sha256:098e5872443729e2b070825bd6f220d5a9009e92fadb9dfc5c15ede934234bbb` |
| `one-hour--train-20260921_00--first-singleton--sacramento--global_time` | `sha256:9ca89b6b6d2fa12e8e06ae873e0067fa00ecee459d4317e47c01b0050dd8b6d6` |
| `one-hour--train-20260921_00--prefix-6--reno--global_time` | `sha256:b5389eae621619fd12840096782a650e3cc71c71fe11baebeb4d690be1055c1f` |
| `one-hour--train-20260921_00--prefix-6--sacramento--global_time` | `sha256:0b1badac7b238415cf6bb8373c0f674b5da192e95d081e0978cfb687407cb4e4` |
| `one-hour--train-20260921_16--first-singleton--reno--global_time` | `sha256:7e69f5a206c54e59ba731afc7fa353637082ae58f76eac8d5a63a0cfe66ce4ef` |
| `one-hour--train-20260921_16--first-singleton--sacramento--global_time` | `sha256:0d834dbeffdffcf13c9a65934e77569e1acdb1a304b2bcb2dae326e327ca7a6d` |
| `one-hour--train-20260921_16--prefix-6--reno--global_time` | `sha256:870668247aa940ffeb18f9e5cfb4078d28bcd14be771408228beb46df9cc9cba` |
| `one-hour--train-20260921_16--prefix-6--sacramento--global_time` | `sha256:2c7b99b653951e2b62df7d952d7fc47b120a91785494a588e56a3357e27265a9` |

Each source coordinate is the local seed for its paired global-time and
regularized-per-scan tasks. The evaluation JSON and CSV retain every task ID,
source task ID and digest, seed, and stage-1 RF selection value.

The 16 accepted RF-selected results are below. Objective delta is iteration-2
minus the sealed stage-1 RF selection value. All geographic finalists are
interior to the 25 km local radius. `edge` means at least one selected timing
nuisance reaches the endpoint of the task's four-point tau stencil.

| Task | Source | Result seal | Seed → final (lat, lon) | Objective delta | Displ. | Error | Tau (s) / elapsed | Grid |
|---|---|---|---|---:|---:|---:|---|---|
| `00 first Reno global` | `098e…4bbb` | `3213…4e20` | (37.705647, -122.229172) → (37.663491, -122.238047) | -0.004483 | 4.752 | 29.992 | -1.75 / 85.866 | edge, interior |
| `00 first Reno per-scan` | `098e…4bbb` | `3de4…b087` | (37.705647, -122.229172) → (37.663491, -122.238047) | -0.004483 | 4.752 | 29.992 | -1.75 to 0.00 / 73.453 | edge, interior |
| `00 first Sacramento global` | `9ca8…b6d6` | `bf24…3727` | (37.680122, -122.204575) → (37.662551, -122.240076) | -0.001955 | 3.685 | 29.935 | -1.75 / 102.745 | edge, interior |
| `00 first Sacramento per-scan` | `9ca8…b6d6` | `f457…677d` | (37.680122, -122.204575) → (37.662551, -122.240076) | -0.001955 | 3.685 | 29.935 | -1.75 to 0.00 / 107.504 | edge, interior |
| `00 prefix Reno global` | `b538…5c1f` | `8e71…3662` | (37.924024, -122.521516) → (37.902944, -122.494803) | -0.000853 | 3.315 | 6.048 | -1.25 / 376.549 | interior, interior |
| `00 prefix Reno per-scan` | `b538…5c1f` | `0635…9c51` | (37.924024, -122.521516) → (37.906458, -122.503706) | -0.002180 | 2.501 | 6.579 | -1.50 to 0.25 / 368.391 | edge, interior |
| `00 prefix Sacramento global` | `0b1b…b4e4` | `15ec…f3f6` | (37.902860, -122.491674) → (37.902860, -122.496126) | -0.001327 | 0.391 | 6.055 | -1.25 / 365.061 | edge, interior |
| `00 prefix Sacramento per-scan` | `0b1b…b4e4` | `927a…82a4` | (37.902860, -122.491674) → (37.899346, -122.473866) | -0.002461 | 1.611 | 5.689 | -1.00 to 0.25 / 348.993 | edge, interior |
| `16 first Reno global` | `7e69…4ef` | `7c3e…7e44` | (37.924024, -122.521516) → (37.909968, -122.490348) | -0.002786 | 3.149 | 6.788 | -1.75 / 114.158 | interior, interior |
| `16 first Reno per-scan` | `7e69…4ef` | `96ef…a25` | (37.924024, -122.521516) → (37.909968, -122.490348) | -0.002786 | 3.149 | 6.788 | -1.75 to 0.00 / 120.494 | edge, interior |
| `16 first Sacramento global` | `0d83…7a6d` | `e119…933e` | (37.902860, -122.491674) → (37.909886, -122.487221) | -0.001528 | 0.873 | 6.768 | -1.75 / 110.326 | edge, interior |
| `16 first Sacramento per-scan` | `0d83…7a6d` | `5467…933e` | (37.902860, -122.491674) → (37.909886, -122.487221) | -0.001528 | 0.873 | 6.768 | -1.75 to 0.00 / 112.425 | edge, interior |
| `16 prefix Reno global` | `8706…cba` | `ea5e…c972` | (37.811684, -122.517337) → (37.857342, -122.468394) | -0.018208 | 6.652 | 1.775 | -1.25 / 509.486 | edge, interior |
| `16 prefix Reno per-scan` | `8706…cba` | `d9fd…3099` | (37.811684, -122.517337) → (37.850312, -122.459501) | -0.020343 | 6.652 | 2.301 | -1.00 to 0.25 / 520.298 | edge, interior |
| `16 prefix Sacramento global` | `2c7b…65a9` | `29cc…5040` | (37.902860, -122.491674) → (37.857189, -122.469427) | -0.008793 | 5.441 | **1.689** | -1.25 / 512.997 | interior, interior |
| `16 prefix Sacramento per-scan` | `2c7b…65a9` | `104b…7410` | (37.902860, -122.491674) → (37.867729, -122.478324) | -0.010784 | 4.078 | 2.176 | -1.50 to 0.25 / 509.078 | edge, interior |

For all four one-scan arms, both methods select the same final coordinate.
Their post-seal median error is 18.362 km, essentially unchanged from the
18.262 km median of the sealed stage-1 seeds. The six-scan local refinement is
meaningfully better: global time's median falls from 6.009 km at the sealed
stage-1 seeds to 3.912 km, while regularized per-scan time reaches 3.995 km.
The lowest observed post-seal error is 1.689 km for `16 prefix Sacramento
global`; it is a result description, not a selection rule.

Paired-prior final separations are below. A pair is called converged only when
its separation is at most the final 0.390625 km grid step.

| View | Global time | Regularized per-scan time |
|---|---:|---:|
| `00 first singleton` | 0.206893 km, converged | 0.206893 km, converged |
| `00 prefix-6` | 0.116451 km, converged | 2.734996 km, not converged |
| `16 first singleton` | 0.274450 km, converged | 0.274450 km, converged |
| `16 prefix-6` | 0.092262 km, converged | 2.545878 km, not converged |

## Post-seal reference rule

The Sausalito coordinate is not present in the manifest, source artifacts, or
iteration-2 tasks. The evaluator introduces it only after every expected
iteration-2 seal and result contract validates. That condition was met for
all 16 results, so the evaluator added it solely to calculate the errors in
the table above. No method, seed, timing value, final coordinate, or result was
selected using reference data.

RF-objective deltas are descriptive only. The per-scan method can include its
timing regularization, so its numeric objective is not a cross-method ranking.

## Artifacts and limits

- `post-seal-evaluation/iteration2-post-seal-evaluation.json` is the sealed
  machine-readable status and evaluation record.
- `post-seal-evaluation/iteration2-post-seal-evaluation.csv` is its flat table.
- `post-seal-evaluation/iteration2-post-seal-evaluation.png` is the completed
  post-seal comparison render.
- `evaluate_postseal.py` is an offline evaluator only; it does not import or
  modify the live scheduler or either inference runner.

The four fixed views overlap, so these arms are paired development evidence,
not independent validation samples. A `0.390625 km` final grid is a cell-centre
screen, not a sub-grid accuracy claim. Timing-stencil endpoint selections are
common, especially for regularized per-scan time, and its two prefix-6 prior
pairs do not converge. These facts limit the result to evidence for the local
grid and timing configuration; they do not establish an independently
validated position or a method choice.
