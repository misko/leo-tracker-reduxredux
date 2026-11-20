# Safeguarded secant position fitting

The secant solver retained all six compact v5 fixes with a **1.52×** median paired end-to-end speedup. Across 12 calibration-arm endpoints, the median displacement was **9.60 m**, the largest was **19.63 m**, and the largest conditional RF RMS change was **0.146 Hz**. Every endpoint met the preregistered 50 m and 1 Hz limits. The six recordings came from one roof installation. [Paired scores](scores.json) · [Locked predictions](prediction-lock.json)

The stock position solver evaluates four central finite differences per Jacobian and tries up to nine damped steps. The candidate initializes from two one-sided finite differences and updates its Jacobian from accepted position and residual changes. It minimizes a quadratic over the 25 km tile and a bounded trust region, including along active edges. Every accepted iterate still lowers the squared norm of the original residual. A fresh local Jacobian must confirm that the best bounded step is at most 20 m for the small-step stop. Both implementations preserve the original observation masks, nuisance fits, causal orbit inputs and all five outer phase refreshes. [Protocol](PROTOCOL.md) · [Preregistered source seal](seal.json) · [Sealed solver sources](sealed-solver-source.tar.gz)

## Six matched full runs

Both implementations invoked the replaced optimizer 530 times, with the same count in every pair. Residual evaluations fell from **15,246 to 3,914**. The median paired evaluation ratio was 3.40×, and optimizer wall time improved 3.97× at the median. All 530 secant fits stopped after verifying the 20 m criterion. The stock solver recorded 420 small-step exits, 103 exits without an accepted damped step, and seven iteration-budget exits. Observation and track counts and cavity-offer decisions agreed on all six cases. [Stock predictions](reference-positions.jsonl.gz) · [Secant predictions](secant-positions.jsonl.gz)

| Recording | Residual evaluations, stock → secant | Whole-worker wall, stock → secant | Endpoint shift `c = 0` / fitted `c` |
|---|---:|---:|---:|
| DS26-0036 | 2,332 → 650 | 169.53 → 118.78 s | 19.63 / 13.65 m |
| DS26-0122 | 5,814 → 1,137 | 330.22 → 143.40 s | 10.54 / 10.61 m |
| DS26-0237 | 1,555 → 455 | 145.02 → 97.44 s | 8.92 / 9.49 m |
| DS29-0082 | 1,599 → 474 | 120.14 → 76.19 s | 2.23 / 1.92 m |
| DS29-0174 | 1,749 → 544 | 117.79 → 76.18 s | 10.17 / 9.72 m |
| DS29-0247 | 2,197 → 654 | 194.83 → 138.16 s | <0.01 / <0.01 m |

Each pair ran with one numerical thread on the same pinned x86 core, alternating order across the roster. Whole-worker time starts with stored native factors and includes kernel compilation, process startup and the compact cavity fit. End-to-end speedups ranged from 1.41× to 2.30× on the shared host. The largest combined wall time was 473.62 seconds for DS26-0122. [Execution receipts](prediction-lock.json)

## Position and frequency fit

Median horizontal error at `c = 0` was 0.81846 km for stock and 0.81757 km for secant. With fitted calibration it was 0.83190 km and 0.83109 km. In each implementation, fitting `c` reduced conditional RF RMS in five recordings and position error in four. [Calibrated and zero-calibration scores](scores.json)

The physical check estimated the sensitivity of the conditional Doppler residual at the first completed initial branch, using two 20 m displacements and the fitted observation mask. Across the six cases, the P95 pointwise Doppler change over a 20 m step was 0.119–0.199 Hz, compared with median nominal per-point noise of 58–84 Hz. Both implementations made three posterior calculations for this diagnostic outside the optimizer evaluation counter. [Local slope measurements](secant-positions.jsonl.gz)

## Trust contraction limit

A separate curved residual test exposed a limit of the fixed three-trial budget. For the residual vector `[x² − 1, y]`, starting at `[0.4, 0]` in a ±2 km box, the model proposes `x = 1.449`. The first two halvings still encompass that proposal, so all three evaluations repeat and the optimizer returns `[0.4, 0]` with `no_accepted_trust_step`. The qualification retains this preregistered contraction rule.

## Reproduction

Use the archive host and restore the sealed solver files into a scratch copy of the evaluation package. The pair command enforces the stored order and case deadline. The scorer uses the frozen reference coordinate only after reading the prediction receipts.

```sh
repo="$PWD"
report="$repo/reports/2026_11_19_receiver_convergence/position-fit"
scratch="$(mktemp -d)"
mkdir "$scratch/tools"
cp -a "$repo/tools/pipeline_eval" "$scratch/tools/"
ln -s "$repo/.venv" "$scratch/.venv"
tar -xzf "$report/sealed-solver-source.tar.gz" -C "$scratch/tools/pipeline_eval/variants"

(
  cd "$scratch"
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
    .venv/bin/python -B -m tools.pipeline_eval.qualification.secant_fit_trial \
    --out "$OUT/$CASE" pair "$CASE" --seal "$report/seal.json"
)
.venv/bin/python -B -m tools.pipeline_eval.qualification.secant_fit_trial \
  --out "$REPORT_OUT" score --source "$OUT" --seal "$report/seal.json"
```
