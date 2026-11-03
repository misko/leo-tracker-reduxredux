# Recorded-IQ replay

The production-acquired comparison completed all 96 windows. These unlabeled
recordings do not establish a replacement detector's ROC, recall, or improved
tracking. On each fixed candidate, Gaussian GLRT64 and its margin diagnostic
return exactly the current detector's CFO. Their changed denominator and control
subtraction change candidate rankings. The primary Gaussian score chose the
current winner in 24/32 holdout windows; Gaussian margin chose it in 31/32.

## Frozen scope and fairness

Selection uses the first two real visits by visit index per rate and split in the
DS5 server-evaluation manifest, without looking at detector outcomes: 24 visits,
both receivers, and two nonoverlapping 20 ms windows starting at 0 and 40 ms.
There are 32 windows and 16 receiver/window-pair comparisons in each split.
All manifest and raw NPY hashes, shapes, and dtypes are checked. Scoring sessions
are disjoint across development, validation, and holdout.

Each method receives identical immutable raw correlation matrices, symbols 2..65,
exact and roll-17 control templates, complete supported frames, and a 512-bin
residual CFO grid with 4.4 us symbol spacing. Actual pilot energy vectors enter
the Gaussian/adaptive likelihood model; baseline raw correlations remain intact.
Independent-frame phase and amplitude are nuisance parameters. Each candidate
has 14 or 15 complete frames; 68/96 production current winners have 15 frames
and 28/96 have 14. Full per-window natural scores, candidate order,
winner identity, exact/control scores, and absolute model CFO are in results.json.

Two acquisition regimes were frozen and evaluated separately:

- `coarse_final`: shared existing coarse numerical helpers; 11 CFO bins from
  -400 to +400 kHz, 80 kHz steps, eight retained basins, one-sample epoch refinement.
  This is a coarse acquisition pilot, not ordinary production acquisition.
- `production_final`: existing `acquire_symbolwise`, its complete coarse/fine/
  conditioned CFO search and verification, and eight retained candidates. The
  full production acquisition configuration is serialized in selection.json;
  maximum samples are adjusted only to the common 20 ms window at each rate.

Development timing preflight at 10 MS/s returned eight production candidates
in 0.50465 CPU seconds, supporting the same 24-visit confirmatory scope. This
preflight assessed runtime, not detector performance.

Covariance training uses the third/fourth development visits per rate, both RX,
first 20 ms, epoch zero and CFO zero. None of these visits/samples are scored.
The four rate-specific fits each use 60 energy-normalized frames, 64 columns,
zero assumed mean, and fixed 0.25 trace-target shrinkage. Training observations
are unlabeled, may contain pilots/interference, and are not established IID
noise. Development training shares sessions with development scoring, while
validation/holdout sessions are excluded. Every validation rate uses the opposite
edge to its development covariance fit; every holdout rate matches its development
edge. Exact/control share the exact-trained covariance despite potentially
different colored-background null covariance under their template projections.
Adaptive margin is therefore a model-mismatched diagnostic, not a primary scored
recommendation. This is a data-adaptive model, not measured noise truth. Normalized
training rows, covariances and precisions are in training.npz.

## Held-out descriptive results

Joint window consistency means circular timing difference at most one symbol
(4.4 us) and absolute CFO difference at most 5 kHz. Windows are independently
acquired; this is descriptive continuity, not held-out truth confirmation.

| Method | Production holdout winner agreement | Production consistent pairs | Coarse consistent pairs | Production median rank correlation |
|---|---:|---:|---:|---:|
| Current GLRT64 margin | 32/32 | 3/16 | 3/16 | 1.000 |
| Gaussian GLRT64 | 24/32 | 3/16 | 3/16 | 0.738 |
| Gaussian GLRT64 margin diagnostic | 31/32 | 3/16 | 3/16 | 1.000 |
| Adaptive NMF64 | 12/32 | 3/16 | 4/16 | 0.202 |
| Adaptive NMF64 margin diagnostic | 13/32 | 4/16 | 4/16 | 0.464 |
| Segmented GLRT32 | 17/32 | 3/16 | 3/16 | 0.440 |
| Differential lag1 | 13/32 | 4/16 | 3/16 | 0.226 |

Production development consistency is 0/16 for every method; validation is 3/16
for every method. The holdout one-pair differences do not establish better
tracking. Transmitter changes, intermittent pilot presence, interference, and
timing/CFO aliases can all change the winner. Absolute reported CFO is relative
to a declared zero calibration center; no independently measured receiver CFO
truth is available. The residual correlation CFO grid has a 227272.7 Hz alias
period, so large raw CFO differences can include aliases. No synthetic threshold
is applied to declare these recordings positive or negative.

## Cost and reproducibility

| Regime | Replay wall seconds | Shared acquisition CPU seconds | Correlation extraction CPU seconds | All seven scores CPU seconds |
|---|---:|---:|---:|---:|
| Coarse final | 20.439 | 18.662 | 0.860 | 0.369 |
| Production final | 23.585 | 21.879 | 0.851 | 0.369 |

Training CPU is 0.111 seconds for production. Times are descriptive single-run
host measurements, not p99 latency or a per-method timing breakdown. Timing
excludes source/manifest initialization and includes cache serialization in wall
time. BLAS/OpenMP threads are fixed to one. Matrices are cached once for all
methods; acquisition and extraction are separate from pooled scoring CPU.

Canonical final artifacts are only `recorded/coarse_final/` and
`recorded/production_final/`. Each contains selection.json, provenance.json,
results.json, matrices.npz, training.npz and run.log. Provenance hashes Python
numerical sources, the installed native acquisition binary, this harness and
the method source. Source hashes are checked again before saving final results.
Both final regimes use methods SHA256
`bbe54b87d14ffc47305fd9880c74cc7839b3af5409074b6efd93d082904fa4b1`.

The initial `recorded/run.log` documents an explicit source-hash rejection after
an overlapping method edit; no results were saved for that attempt.
`recorded/coarse/` is an earlier successful frozen-source preliminary replay.
`recorded/production/` contains a superseded preflight selection only. These are
retained for audit and are excluded from the final comparison.

Commands, executed from the repository root (substitute `MODE=coarse` or
`MODE=production` and `OUT=recorded/coarse_final` or `OUT=recorded/production_final`):

```bash
.venv/bin/python reports/2026_10_07_glrt_detector_comparison/recorded.py freeze --acquisition MODE --output reports/2026_10_07_glrt_detector_comparison/OUT
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 240 .venv/bin/python reports/2026_10_07_glrt_detector_comparison/recorded.py run --acquisition MODE --output reports/2026_10_07_glrt_detector_comparison/OUT
.venv/bin/python -m pytest reports/2026_10_07_glrt_detector_comparison/test_recorded.py -q
.venv/bin/python -m ruff check reports/2026_10_07_glrt_detector_comparison/recorded.py reports/2026_10_07_glrt_detector_comparison/test_recorded.py
```

Seven replay tests pass; Ruff passes. Tests cover deterministic outcome-independent
selection, session/sample leaks, common immutable evidence, omitted/nonfinite
method errors, input hashes/path containment, frozen configuration, and equality
between cached workspace and direct numerical correlation helpers.
