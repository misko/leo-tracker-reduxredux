# Independent Armijo confirmation and cavity stress

The Armijo source and dependencies come from the six-case source seal. Preserve the original five phase updates, causal archive, 25 km tile and full stored native factors. The independent group is the exact eight-recording secant confirmation roster. The separate stress group is DS26-0066 and DS26-0287, chosen for their previously observed error increases at the compact cavity cutoff relative to original no-repair v5. Keep the groups separate because the stress cases are deliberately outcome-selected.

Run Armijo once per recording with one numerical thread pinned to core 8, 9, 20 or 21 and a 480-second case limit. Use sealed older secant and stock compact cavity records when their source and truth-free input match. Bind the original no-repair requests and archived outputs separately. Retain all attempts. For each calibration arm report geographic error and position shifts, conditional RF RMS, point and track counts, and whether Armijo preserves the large compact-to-original errors. Label historical wall times with their measured boundaries and cores.

## Reproduction

Use the archive host and the [sealed solver files](sealed-solver-source.tar.gz). The [fixed plan](confirmation-plan.json) supplies the CPU per recording. If running in a scratch copy of the package, point `PIPELINE_EVAL_BLIND_ROOT` to the original repository's blind-regional report so the public case hashes continue to bind the same files. Set `WORK` to a fresh local result directory and `BROAD` to the broad secant replay work directory.

```sh
report="$PWD/reports/2026_11_19_receiver_screening/solver"
export PIPELINE_EVAL_BLIND_ROOT="$PWD/reports/2026_11_18_blind_regional_receiver"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_confirmation \
  --solver-seal "$report/seal.json" --out "$WORK/$CASE" \
  run "$CASE" --plan "$report/confirmation-plan.json"

.venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_confirmation \
  --solver-seal "$report/seal.json" --out "$REPORT_OUT" score \
  --plan "$report/confirmation-plan.json" --source "$WORK" --broad "$BROAD"
```
