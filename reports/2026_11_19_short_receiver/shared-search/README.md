# Shared initial association in v5

This experiment reuses identical discovery requests and confines curve profiling to the candidates that can influence the original visibility-gated selection. The timed boundary starts with stored native GLRT detections and runs through both position estimates. The stock and candidate methods use the same single 25 km roof region, eight channels, causal orbital evidence, calibration priors and search budgets. [Protocol](PROTOCOL.md)

## Where the work repeated

In a pinned exploratory DS26-0036 profile, initial selection took 15.98 seconds. Association took 4.20 seconds across 28 requests and 1,652 curve profiles, while coordinate refits took 6.42 seconds. Conservative salvage took 4.97 seconds in its separate stage. The cProfile attribution predates the matched timing runs and uses a wall clock. [Initial diagnosis](stock-initial-profile.json.gz) · [Salvage diagnosis](stock-salvage-profile.json.gz)

The frozen discovery method requests the same association twice within each exploration. It overwrites the first result before consuming any of its fields. The candidate reuses that result within the exploration and shares the base projection at the center of the region. Other positions and shifted orbit hypotheses still receive their original projections. For each curved-track association, the original visibility criterion already excludes below-horizon candidates. The candidate gathers the eligible rows in catalogue order, keeps index zero for the original fallback, and calls the original curve and noise-screen routines. The stock association code still applies its original gates and chooses the winner. [Implementation](../../../tools/pipeline_eval/variants/v5_shared_search.py)

The variant adds a 142-line Python adapter, including its worker entry point. It keeps one center projection live through the initial stage and leaves the original likelihood, branch ranking, coordinate optimizer and recovery logic in place. The smaller row batches can change intermediate floating-point accumulations. In a synthetic check of the frozen profile kernel, aliases, RMS values and gates matched exactly, and maximum absolute cost difference was 2.38e-7. The recorded replay comparisons use association outcomes, initial labels and gates, and complete position and RF outputs. [Numerical check](numeric-check.json) · [Tests](../../../tests/pipeline_eval/test_v5_shared_search.py)

## Matched timing

Association CPU includes the original association body with the candidate's compact curve calls. Initial-stage CPU includes the outer sharing checks and tracing. Whole-worker CPU and elapsed time include launch and kernel compilation. Each pair ran on a single pinned core of the shared x86 host.

| Recording | Stock → candidate profiled candidate-time cells | Stock → candidate association CPU (s) | Stock → candidate initial CPU (s) | Stock → candidate complete CPU (s) | Stock → candidate complete wall (s) |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 99,767,136 → 16,861,180 | 10.57 → 6.27 | 26.24 → 21.80 | 197.36 → 173.11 | 229.41 → 191.49 |
| DS29-0082 | 47,087,040 → 8,001,995 | 5.42 → 2.14 | 10.23 → 5.91 | 125.99 → 135.16 | 134.79 → 166.65 |
| DS29-0174 | 107,782,864 → 19,036,243 | 10.54 → 7.67 | 26.95 → 22.85 | 252.20 → 251.42 | 272.44 → 292.12 |

The completed pairs kept the same 28 logical association requests, reusing 12 and executing 16. Each saved eight center projections. Association CPU speedup was 1.69× on DS26-0036, 2.54× on DS29-0082 and 1.37× on DS29-0174. The DS29-0082 candidate spent 43.39 seconds in unchanged reassociation admission compared with 26.16 seconds in its stock run. Whole-worker timing includes that variability. [Measured receipt](receipt.json)

On DS26-0122, stock completed in 484.48 seconds wall and the initial candidate reached the pair's 650-second deadline before emitting a position. The candidate had already completed the same observed initial decisions with 136,468,416 → 22,233,224 profiled cells, 11.26 → 8.21 CPU seconds in association, and 68.46 → 58.44 CPU seconds through initial selection. The original schedule therefore produced fixes for three of four candidate attempts and four of four stock attempts in each arm. The separate same-CPU confirmation has its own 650-second limit. [Original DS26-0122 attempt](DS26-0122-deadline-attempt.json) · [Original candidate schedule](original-positions.jsonl.gz) · [Original stock schedule](original-stock-positions.jsonl.gz) · [Schedule digests](original-receipt.json)

The DS26-0122 standalone confirmation completed in 353.67 seconds wall and 352.05 seconds CPU on the same core. It reproduced the same 22,233,224 profiled cells, initial decisions, and both frozen endpoints. Association used 5.88 CPU seconds and the complete initial stage used 48.19 CPU seconds. The complete-result archive labels this row `standalone_corroboration` and the table above uses only completed original pairs. [Follow-up position](followup-position.jsonl.gz) · [Follow-up journal](DS26-0122-followup-attempt.json) · [Follow-up digest](followup-receipt.json)

## Matched positions and frequency fit

Each pair below gives `c = 0` followed by fitted `c`. The geographic errors come from independent scoring against the receiver location. The RMS values describe the selected RF fit. Both methods returned the same endpoints, association counts, RF objectives, conditional RMS and downstream recovery decisions.

| Recording | Geographic error (km) | Conditional Doppler RMS (Hz) |
|---|---:|---:|
| DS26-0036 | 1.278 / 1.208 | 74.761 / 74.682 |
| DS29-0082 | 0.567 / 0.517 | 97.004 / 96.684 |
| DS29-0174 | 0.885 / 0.917 | 95.405 / 95.518 |
| DS26-0122 standalone confirmation | 0.751 / 0.747 | 76.220 / 76.215 |

[Candidate predictions](positions.jsonl.gz) · [Stock predictions](stock-positions.jsonl.gz)

## Reproduce

Run each recording with its declared CPU. Complete the two primary paired runs before the corroboration recordings. The qualification verifies source bindings, the discovery decisions, and both calibration arms' positions and frequency evidence. The timing trial restarted after the shared core and projector wrappers were frozen near the start of the study.

```sh
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 560s .venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --case DS26-0036 --out /tmp/shared-search
taskset -c 21 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 560s .venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --case DS29-0082 --out /tmp/shared-search
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 650s .venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --case DS26-0122 --out /tmp/shared-search
taskset -c 21 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 650s .venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --case DS29-0174 --out /tmp/shared-search
```

For the recorded standalone confirmation, run the DS26-0122 candidate after the original pair's deadline. Then package the actual exit status and the completed results.

```sh
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 650s .venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --case DS26-0122 --confirm-missing-candidate --out /tmp/shared-search
shared_search_exit=$?
.venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --package /tmp/shared-search --followup-exit "$shared_search_exit" --out /tmp/shared-search-report
.venv/bin/python -m tools.pipeline_eval.qualification.shared_search_eval \
  --package /tmp/shared-search --out /tmp/shared-search-report
```
