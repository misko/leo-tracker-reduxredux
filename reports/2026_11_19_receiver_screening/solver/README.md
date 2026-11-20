# Compact bounded Gauss–Newton with Armijo backtracking

Armijo retained all six compact v5 fixes with **30% fewer lines of numerical code** than secant. It fixed the repeated-rejection regression and used 3,885 residual evaluations on the six roof cases, compared with 3,914 for secant and 15,246 for stock. Across both calibration arms, the largest endpoint shift was **20.58 m against stock** and **11.60 m against secant**. Fresh smoke repeats showed similar optimizer time for the two smaller solvers. [Scored comparisons](scores.json) · [Locked predictions](prediction-lock.json)

The solver rebuilds its two-column Jacobian from 1 m one-sided differences at each accepted position. It minimizes the local quadratic over the 25 km box, then halves the actual feasible displacement until the original residual decreases enough. An explicit displacement check makes every evaluated backtrack strictly smaller than its rejected predecessor, even after floating-point rounding at a tile edge. The solver stops when a fresh bounded step is at most 20 m. The original residual, five initial orbit-phase updates, masks, causal inputs and cavity policy are shared with both controls. [Protocol](PROTOCOL.md) · [Source and input seal](seal.json) · [Sealed solver sources](sealed-solver-source.tar.gz)

The candidate has 85 nonblank physical lines of numerical code, down from 121 in the secant prototype, a 30% reduction. The count covers each solver's numerical constants, solver body and numerical helpers and excludes imports, instrumentation and diagnostic code. Both numerical cores depend on NumPy. The full-pipeline benchmark shares the same instrumentation and compact C orbit projector.

## Curved regression and bounds

On residual vector `[x² − 1, y]` from `[0.4, 0]` in the ±2 km box, secant evaluated `x = 1.448689` three times and stopped at `x = 0.4`. Armijo rejected that proposal once, accepted the half step to `x = 0.924345`, and returned `x = 1.003054` after 10 total residual evaluations. The automated tests also check exact feasibility of every evaluation, optimization along an active edge, singular and nearly singular geometry, and evaluation accounting.

## Six full native-factor runs

Every method returned both positions on all six recordings. Prepared observation counts, track counts and cavity-offer decisions matched. Each initial branch ran all five phase updates. All 530 Armijo optimizer calls reached the fresh 20 m stopping criterion and accepted their full trial steps on these recordings. Residual evaluations fell in every case relative to stock, with a median 3.49× reduction. Armijo used fewer evaluations than secant on three recordings. [Armijo](armijo-positions.jsonl.gz) · [Archived stock](reference-positions.jsonl.gz) · [Archived secant](secant-positions.jsonl.gz)

| Recording | Residual evaluations, stock / secant / Armijo | Whole-worker wall, stock / secant / Armijo | Largest Armijo shift from stock / secant |
|---|---:|---:|---:|
| DS26-0036 | 2,332 / 650 / 681 | 169.53 / 118.78 / 70.81 s | 20.58 / 3.17 m |
| DS26-0122 | 5,814 / 1,137 / 1,110 | 330.22 / 143.40 / 134.22 s | 7.79 / 2.99 m |
| DS26-0237 | 1,555 / 455 / 402 | 145.02 / 97.44 / 86.22 s | 9.42 / 0.09 m |
| DS29-0082 | 1,599 / 474 / 450 | 120.14 / 76.19 / 52.92 s | 1.15 / 1.52 m |
| DS29-0174 | 1,749 / 544 / 561 | 117.79 / 76.18 / 90.42 s | 7.97 / 11.60 m |
| DS29-0247 | 2,197 / 654 / 681 | 194.83 / 138.16 / 120.31 s | <0.01 / <0.01 m |

The largest absolute change in conditional RF RMS was 0.14610 Hz against stock and 0.00074 Hz against secant. Every paired arm met the fixed 50 m and 1 Hz limits. Median horizontal error at `c = 0` was 0.81846 km for stock, 0.81757 km for secant and 0.81367 km for Armijo. With fitted calibration the medians were 0.83190, 0.83109 and 0.82732 km. Within Armijo, fitting `c` reduced conditional RF RMS in five recordings and reduced position error in four. All six recordings came from the same installation. [Per-arm scores](scores.json)

## Fresh smoke timing

The fresh secant reruns reproduced both earlier endpoint coordinates, RF RMS values and residual counts exactly. With alternating order on the same cores, optimizer time was close in both pairs. Whole-worker wall moved in opposite directions. [Fresh secant timing receipts](fresh-secant-positions.jsonl.gz)

| Recording | Optimizer wall, fresh secant → Armijo | Whole-worker wall, fresh secant → Armijo |
|---|---:|---:|
| DS26-0036 | 12.47 → 12.01 s | 78.62 → 70.81 s |
| DS29-0082 | 2.060 → 2.057 s | 49.34 → 52.92 s |

Whole-worker time begins with stored native factors and includes projector compilation and compact cavity inference. The six scientific comparisons use the earlier sealed stock and secant controls. They have the same inputs and per-case pinned cores. Their wall times come from the earlier host session.

## Independent confirmation and stress

On eight further recordings, Armijo retained all fixes and its largest endpoint shift versus original no-repair v5 was 19.12 m. A separate check of two outcome-selected cases showed that Armijo preserves the major error increase from the compact cavity cutoff. Its fitted-calibration errors were 2.370 and 0.673 km versus original no-repair's 1.218 and 0.440 km. [Independent confirmation](confirmation/README.md) · [Deliberate cavity stress](stress/README.md)

## Reproduction

Use the archive host and restore the sealed files into a scratch copy of the evaluation package. Run on the CPU prescribed for each case in the seal. The two extra secant runs use alternating order on the smoke cases. The scorer authenticates the earlier stock and secant records against their own receipt.

```sh
repo="$PWD"
report="$repo/reports/2026_11_19_receiver_screening/solver"
controls="$repo/reports/2026_11_19_receiver_convergence/position-fit"
scratch="$(mktemp -d)"
mkdir "$scratch/tools"
cp -a "$repo/tools/pipeline_eval" "$scratch/tools/"
ln -s "$repo/.venv" "$scratch/.venv"
tar -xzf "$report/sealed-solver-source.tar.gz" -C "$scratch/tools/pipeline_eval/variants"

(
  cd "$scratch"
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
    .venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_fit_trial \
    --controls "$controls" --out "$OUT/$CASE" pair "$CASE" --seal "$report/seal.json"
)
.venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_fit_trial \
  --controls "$controls" --out "$REPORT_OUT" score --source "$OUT" --seal "$report/seal.json"
```
