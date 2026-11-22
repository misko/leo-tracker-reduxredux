# Canonical Graph proposals on the frozen DS30-0008 solver

Canonicalizing equivalent polynomial proposals improved the `e279026b…` candidate-factor positions by **12.460 m** at fixed zero and **12.052 m** with fitted `c`. Both positions still had higher horizontal error than deployment, by **6.627 m** and **6.840 m** respectively. The candidate-factor run failed the paired deployment-error criterion for a second canonical replay. [Scored receipt](measurements/screened-graph-alias-0008.json)

The experiment loaded the previously published polynomial-group rule by its source digest during track preparation inside the frozen e279 launcher. The rule groups proposals with identical ordered support, degree, time reference, scale and certified relative carrier winding. It uses the earliest proposal’s group order and refits the common lifted response with the first raw measurement fixing the gauge. The native Graph path ran 201 searches across 16 packed lanes in both e279 candidate-factor runs. The candidate detector input, offer, causal orbit archive and scoring reference matched the prior e279 replay. [Reviewed rule and equivalence tests](graph-canonical-alias.md) · [Frozen solver](measurements/screened-tiled-graph-freeze.json) · [Matched input plan](screened-graph-transfer.md)

The earlier southern waveform comparison gained nine Graph members under this rule. It retained the same final 266 owners and returned the same positions, RMS, and decisions on the containing and near-omitted offers. DS30-0008 measures the rule downstream on a different, physical saved input. [Earlier southern solver receipt](measurements/graph-canonical-alias-south-solver.json)

| Solver and detector evidence | Horizontal error, fixed-zero / fitted | Conditional Doppler RMS, fixed-zero / fitted | Final owners per arm |
|---|---:|---:|---:|
| Deployment, deployed detections | 1.638978 / 1.511956 km | 129.7030 / 129.6629 Hz | 4,472 |
| Plain e279, deployed detections | 1.638978 / 1.511956 km | 129.7030 / 129.6629 Hz | 4,472 |
| Earlier covariance solver, candidate detections | 1.331146 / 1.308399 km | 125.8921 / 125.8201 Hz | — |
| Plain e279, candidate detections | 1.658065 / 1.530849 km | 129.7516 / 129.7110 Hz | 4,470 |
| Canonical e279, candidate detections | 1.645605 / 1.518796 km | 129.5294 / 129.4892 Hz | 4,489 |

The canonical solve formed 14 groups of equivalent proposals and removed 21 duplicates. It prepared 6,473 owned Graph observations across 236 tracks, 111 with curvature. The final maps had 19 more observations than plain e279 on the same candidate detections, and their digests differed from both plain e279 and deployment. The fitted coefficient was −357.092 Hz/GHz. The stored comparison arms give the corresponding position and RMS values. Fitting `c` lowered canonical RMS by 0.0402 Hz and horizontal error by 0.127 km. The fitted and fixed-zero endpoints both remained farther from truth than their deployed counterparts. [Polynomial coefficient digest, fitted coefficient and owner comparisons](measurements/screened-graph-alias-0008.json)

The canonical saved solve used 57.81 CPU seconds versus 61.58 for the already recorded plain e279 candidate-factor solve. These are singleton timings that include the selected evidence packet, with the canonical run also collecting the polynomial coefficient digest. The earlier parent covariance result uses a different downstream solver on the same candidate detections. [Bounded run results](measurements/screened-graph-alias-0008.json)

## Reproduction

Use the original DS30-0008 paired receipt, the existing `screened-graph-dense.json` saved control, and the frozen e279 bundle. The command runs one saved-detection solve under the shared Gauss lock. The separate plain-e279 deployed-detection control adds a comparator row when its receipt is present. [Runner](screened_graph_alias_trial.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -BPs -m reports.ALGO08.single-core-2x.screened_graph_alias_trial run \
  "$bench" /tmp/ds30-v2-stage-covariance-375895/DS30-0008/pair.json \
  "$bench/screened-graph-canonical-0008-new.json"
```
