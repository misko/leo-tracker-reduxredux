# Position from one robust anonymous-track fit

The receiver published **5 of 6** positions from the original anonymous GLRT track projections. All five were within 5 km in both calibration arms. The fitted-calibration median was **2.136 km** and the worst published error was **4.158 km**. The original v5 reference published six, with a fitted median of 0.832 km and a worst error of 1.458 km. The fixed wrong tile withheld in both arms. The six correct-tile workers took **1.41–2.23 s wall** and **149,072–154,404 KiB peak RSS** each on pinned x86. [Frozen protocol](PROTOCOL.md) · [Predictions](positions.jsonl.gz) · [Independent scorer output](scores.csv)

## The fit

The sandbox receives each anonymous track's measurement times, CFOs, receiver, channel and RF, along with the capture's clock and causal TLE text and its offered tile. It receives no previous position, satellite assignments or evaluation coordinates. DS26 inputs are the frozen projection of the original GLRT track graph. DS29 inputs are the same projection in the portable archive. The loader verifies the observation, catalogue and capture authority digests recorded with each result. [Input and sandbox code](../../../tools/pipeline_eval/qualification/robust_em_trials.py) · [Code lock](source-lock.json)

The receiver propagates a coarse 20-second orbit grid for the causal catalogue and a 5-second Hermite grid for the regional horizon survivors. Each track scores the regional candidates using shape after removing a free frequency level and allowing a penalized phase shift. It retains up to 16 candidate satellites. An initial consensus over curved tracks estimates a wrapped receiver/band offset and drift. The model then alternates association and bounded weighted least squares with one shared position, four receiver/band offsets and drifts, and a shared phase per used satellite. Position and phase use the first-order Doppler derivatives about the tile centre and the nominal orbit. [Receiver implementation](../../../tools/pipeline_eval/variants/robust_em.py)

The frequency likelihood uses a 150 Hz white component and a 200 Hz Ornstein–Uhlenbeck component with a 4 s correlation time. It uses one integer alias per track, applies robust track weights and bounds each phase to ±7.5 s with a 2.5 s prior. Both final arms use the same assigned tracks, aliases, weights and model budgets. Fitted calibration adds one RF slope. The conditional RMS describes these fitted observations. Four calibration lanes and bounded orbit-phase errors allow a deliberately small single model from track association through both position arms.

All 20,127 original track points entered candidate screening across the six cases. The pooled fits used 19,017, including the diagnostic fit of the withheld case. The portable projection lacks original opportunity IDs. The code removes exact same-lane copies with folded CFO and retains whole grouped tracks for the validation holdout. Tracks grouped by their midpoint can have overlapping time extents, so this holdout measures transfer across tracks rather than an independent sample-level predictive likelihood.

## Position, frequency and rejection

| Recording | Position error in km, zero / fitted | Conditional RMS in Hz, zero / fitted | Used points / input points | Wall s | Peak RSS KiB |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 1.832 / 2.136 | 174.31 / 141.99 | 2,867 / 2,867 | 1.41 | 149,484 |
| DS26-0122 | 2.688 / 2.729 | 218.08 / 217.27 | 3,694 / 4,155 | 1.63 | 154,404 |
| DS26-0237 | 1.279 / 0.801 | 149.20 / 118.65 | 3,265 / 3,293 | 1.82 | 153,864 |
| DS29-0082 | 4.479 / 4.158 | 283.76 / 233.79 | 1,483 / 1,526 | 2.23 | 149,072 |
| DS29-0174 | 1.462 / 1.359 | 176.38 / 126.08 | 3,587 / 3,587 | 1.53 | 149,264 |
| DS29-0247 | Withheld in both arms | 281.18 / 272.55 on the forced fit | 4,121 / 4,699 | 1.96 | 154,224 |

Fitting `c` lowered conditional RMS on all six recordings. It improved the geographic error on three of the five published positions and worsened it on two. On DS29-0247 the pooled and training positions were 12.15 km apart, exceeding the 4 km acceptance limit. The withheld forced errors of 3.045 km and 2.794 km remain diagnostics. [Per-arm CSV](scores.csv)

With only DS26-0036's frozen alternate `r0` tile, the held-track score was 0.221 against a 0.28 threshold. The candidate withheld. Its forced errors were 23.119 and 23.199 km. The test covers one alternate tile, and all six captures came from the same installation. [Wrong-tile receipt](wrong-region.jsonl.gz)

The planted fit recovered the true offsets to 0.1 km with track-wide alias shifts. A duplicate-orbit control exposed an unfair margin between a satellite with a fitted phase and an otherwise identical alternative. The correction gives both hypotheses the same bounded phase freedom for the margin while preserving held data scoring at the training solution. It was locked before opening the geographic scores, and all seven archive subprocesses were rerun. A null input withheld. An additional planted RF slope test recovered the coefficient on the same paired support, while the `c = 0` held-track acceptance check still withheld. [Component tests](../../../tests/pipeline_eval/test_robust_em.py)

## Cost and reproduction

The regional catalogue retained 911–1,151 satellites per recording from 10,964–11,172 causal entries. The largest core numerical step on most runs was the track-wise shortlist, with a median wall time of 0.463 s. Median coarse and fine propagation combined took 0.246 s. Median paired fit and validation took 0.112 s. Whole worker CPU was 1.06–1.62 s. The implementation retains the 16-candidate output per track and evaluates each dense visible-candidate matrix one track at a time. For a track with `n` samples and `S` visible orbits, the whitening and coarse profile cost is `O(S n²)` after a per-track `O(n³)` covariance factorization. The bounded final system has two position columns, eight shared radio columns, one phase per used orbit and the optional RF slope.

The measured boundary begins with archived anonymous tracks and ends with serialized position results. The relative performance against raw-IQ receivers and physical embedded timing need separate measurements.

```sh
taskset -c 0,1 .venv/bin/python -m tools.pipeline_eval.qualification.robust_em_trials \
  --cpus 0 1 --cache /tmp/robust-em-inputs --out /tmp/robust-em-results
taskset -c 0 env OPENBLAS_NUM_THREADS=1 .venv/bin/pytest -q tests/pipeline_eval/test_robust_em.py
```
