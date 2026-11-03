# Gaussian-sum 64-scan evaluation

The frozen Gaussian-sum configuration accepted **0/64** scans. The greedy
diagnostic completed **12/64**, with **2/64** planned scans below 1 km; its
accepted-fit median error was 5.514 km. These results reject this bounded
acquisition configuration on the declared panel.

All 192 attempts passed the independent provenance and prior-reset audit;
47 focused tests passed. Scientific failure counts above remain unchanged by
these implementation checks.

Artifacts: [`evaluation.json`](evaluation.json),
[`evaluation.csv`](evaluation.csv), [`figures/`](figures/),
[`audit.json`](audit.json), [`validation.json`](validation.json),
[`storage-replay-equivalence.json`](storage-replay-equivalence.json), and the
interpretation and next-step discussion in
[`INTERPRETATION.md`](INTERPRETATION.md).

This report evaluates the frozen 22/21/21 chronological panel from DS9, DS10,
and DS11. Each of the 64 scans starts from the same Sacramento-centered prior
and runs three independent arms: Gaussian sum, greedy association, and prior
only. Primary results come exclusively from seal-verified receipts under
`runs-v3`; the superseded `runs` and interrupted `runs-v2` directories are not
part of the 192-attempt scientific denominator.

The intended prior is uniform over a 250 km disk centered at
38.5816 N, 121.4944 W. The implementation approximates it with 32 equal-weight,
moment-matched Gaussian cells. It is not an exactly clipped uniform posterior:
the Gaussian tails put 2.546% of represented mass outside the intended disk.
The configured prior-center point estimate is 118.894 km from the common roof
reference. This point is the prior-only baseline; an arbitrary equal-weight
component is not used as the prior estimate.

Only receipts with status `complete` contribute localization errors. Gate
failures, exceptions, timeouts, unsealed outputs, and missing attempts remain in
the denominator and in per-dataset failure counts. Partial posteriors are
diagnostic and are never reported as accepted estimates. Error medians, 90th
percentiles, and worst cases are therefore explicitly conditional on completed
fits, while the less-than-1-km rate uses all 64 planned scans as its denominator.
Gaussian-sum versus greedy comparisons include only scans where both arms
completed.

Runtime figures use the launcher's end-to-end wall time, including state
compression and hashing within the 90-second job budget. The receipt's native
`wall_seconds`, which stops before final artifact work, is retained separately as
`native_pre_artifact_runtime_s` in the evaluation outputs.

The evaluator uses the fixed operator-supplied, unsurveyed roof coordinate
37.849056280893684 N, 122.48575489722863 W. This reference is used only after
the receipts are sealed; it was not used to select scans, tune the prior, or
choose examples. Map examples use the first chronological selected scan from
each dataset rather than a scan selected by error.

`historical-context.json` records 64 read-only outputs from the published
Sacramento standard pipeline. All 64 report incomplete 400-point searches.
Their published selected coordinates are retained as diagnostics and have their
errors recomputed against the same roof reference. They are not a matched arm:
they use different tracks, objective, and search budget.

Final numerical tables and figures are generated only after all 192 `runs-v3`
attempts are present. The abandoned `runs-v2` execution encountered stalled
bulk-filesystem directory operations and temporary-filesystem pressure,
including two child processes killed while blocked in disk I/O and six jobs
stopped after their first sealed Gaussian-sum receipt when a log write failed.
The orchestrator was terminated because the blocked children could not safely be
recovered or migrated. These are engineering interruptions rather than remote
service failures or physical-inference outcomes. The full panel is replayed in
`runs-v3` with the same frozen scientific model and thresholds; only the state
artifact root moved to SSD-backed storage and the output namespace changed.

Regenerate the sealed evaluation, flat attempt table, and all figures with one
numerical thread:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_30_gaussian_sum_64_scan/evaluate.py
```

The command refuses to publish unless every selected unit has exactly one record
for each of the three arms. It writes `evaluation.json`, `evaluation.csv`, and
the PNG files under `figures/` from `runs-v3` only.

## Results

All 192 planned attempts have sealed records. No Gaussian-sum fit passed the
frozen acceptance gates: 63 stopped on a gate and DS9-F020 reached the internal
wall budget after 35 of 45 factors. The greedy approximation completed 12 of 64
fits; 36 stopped on a gate and 16 ended because a moved prediction time lacked
the required four-knot orbit support. All 64 prior-only controls completed.

| Dataset | Arm | Complete | Gate failed | Error | Budget reached |
|---|---:|---:|---:|---:|---:|
| DS9 (22) | Gaussian sum | 0 | 21 | 0 | 1 |
|  | Greedy | 6 | 11 | 5 | 0 |
|  | Prior only | 22 | 0 | 0 | 0 |
| DS10 (21) | Gaussian sum | 0 | 21 | 0 | 0 |
|  | Greedy | 3 | 11 | 7 | 0 |
|  | Prior only | 21 | 0 | 0 | 0 |
| DS11 (21) | Gaussian sum | 0 | 21 | 0 | 0 |
|  | Greedy | 3 | 14 | 4 | 0 |
|  | Prior only | 21 | 0 | 0 | 0 |
| Pooled (64) | Gaussian sum | 0 | 63 | 0 | 1 |
|  | Greedy | 12 | 36 | 16 | 0 |
|  | Prior only | 64 | 0 | 0 | 0 |

Errors below are conditional on accepted fits. The last column instead divides
the count below 1 km by every planned scan, so failures cannot disappear from
the accuracy rate.

| Dataset | Arm | Accepted errors | Median (km) | 90th percentile (km) | Worst (km) | Below 1 km / all planned |
|---|---:|---:|---:|---:|---:|---:|
| DS9 | Gaussian sum | 0 | — | — | — | 0/22 (0%) |
|  | Greedy | 6 | 2.877 | 23.643 | 39.275 | 1/22 (4.55%) |
|  | Prior center | 22 | 118.894 | 118.894 | 118.894 | 0/22 (0%) |
| DS10 | Gaussian sum | 0 | — | — | — | 0/21 (0%) |
|  | Greedy | 3 | 200.531 | 213.683 | 216.971 | 0/21 (0%) |
|  | Prior center | 21 | 118.894 | 118.894 | 118.894 | 0/21 (0%) |
| DS11 | Gaussian sum | 0 | — | — | — | 0/21 (0%) |
|  | Greedy | 3 | 11.473 | 92.759 | 113.080 | 1/21 (4.76%) |
|  | Prior center | 21 | 118.894 | 118.894 | 118.894 | 0/21 (0%) |
| Pooled | Gaussian sum | 0 | — | — | — | 0/64 (0%) |
|  | Greedy | 12 | 5.514 | 191.786 | 216.971 | 2/64 (3.125%) |
|  | Prior center | 64 | 118.894 | 118.894 | 118.894 | 0/64 (0%) |

Because no Gaussian-sum fit was accepted, there are no paired accepted
Gaussian-sum/greedy comparisons and no defensible Gaussian-sum point-error
summary. The dominant Gaussian-sum diagnostic was excessive pruned posterior
mass (48 scans); region-center and position-support gates also fired, and
reasons can overlap. Greedy completion does not establish correct satellite
identity or calibrated confidence.

The separate published-pipeline context has 64 selected points but every
400-point Sacramento search reports incomplete. Its diagnostic median error is
5.800 km, 90th percentile 13.541 km, and worst error 39.828 km, with 0/64 below
1 km. Those numbers are not a matched comparison because the tracks, objective,
and search budget differ.

The main conclusion is a failure of this bounded acquisition configuration,
not evidence that single-scan localization or Gaussian mixtures are generally
impossible. The 32-component cap often loses too much posterior mass after the
first factor, while support checks and the local-linear model stop other paths.
The narrow background model also makes concentrated association weights
insufficient evidence of physical calibration. See
[`INTERPRETATION.md`](INTERPRETATION.md) for the limitations and the proposed
independent next experiment.
