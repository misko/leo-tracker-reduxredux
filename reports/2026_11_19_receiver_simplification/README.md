# How early can v5 stop and still give a reliable position?

V5 can stop after its cavity fit and keep the original median, P95, maximum error and fix count on 127 DS26 and eight DS29 roof recordings in both calibration settings. Twelve DS26 positions moved by more than one metre. The largest individual loss was on DS26-0066, where fitted-calibration error rose from 1.218 to 2.370 km. All eight DS29 coordinates matched. Both datasets used the same physical installation and the original single 25 km tile. [Per-recording differences](checkpoint-errors.csv) · [Study protocol](PROTOCOL.md)

[Five stopping points and the new worker, fitted calibration](figures/fitted_c/stopping-points.pdf) · [Same six charts with zero calibration](figures/c0/stopping-points.pdf) · [Original ten modifications](../2026_11_18_pipeline_eval/figures/README.md)

## Where the accuracy comes from

Each row gives the position v5 had computed by that point, extracted from its original recorded numerical state. Each of these stages produced a coordinate for every recording. Distances are in kilometres. Some of the final recovery steps fit more radio observations, so residuals can change even when a coordinate stays fixed. [Distributions for both calibration settings](checkpoint-distributions.csv)

| Last stage included | DS26 fitted median | DS26 fitted P95 | DS29 fitted median | DS29 fitted P95 | Chart |
|---|---:|---:|---:|---:|---|
| Initial satellite assignment | 1.297 | 4.542 | 0.968 | 3.292 | [PNG](figures/fitted_c/v5_stop_initial.png) |
| Conservative track refit | 1.130 | 3.977 | 1.341 | 2.377 | [PNG](figures/fitted_c/v5_stop_conservative.png) |
| Satellite-family refit | 1.020 | 3.466 | 0.718 | 1.640 | [PNG](figures/fitted_c/v5_stop_family.png) |
| Signed orbit correction | 1.018 | 3.338 | 0.742 | 1.650 | [PNG](figures/fitted_c/v5_stop_signed.png) |
| Cavity fit | 0.999 | 3.126 | 0.742 | 1.312 | [PNG](figures/fitted_c/v5_stop_cavity.png) |
| Original v5, no repair | 0.999 | 3.126 | 0.742 | 1.312 | Included on each chart |

The cavity fit temporarily leaves out each candidate satellite family and checks whether the other observations support changing its assignment. Stopping one step earlier kept the DS29 median at 0.742 km but raised its P95 by 26%. A median alone would have selected that cheaper cutoff. [DS29 and DS26 recording-level figure data](figures/fitted_c/stopping-points.csv)

The choice used 16 DS26 development recordings picked by hash. On the remaining 111 DS26 recordings, fitted-cavity median and P95 were 0.988 and 3.380 km. The final v5 values were the same. Both put 109/111 inside 5 km. Across all 135 recordings, zero cases crossed the 5 km threshold in either calibration setting. These are retrospective checks on the frozen benchmark. A new geographic holdout is still needed. [Development checkpoints](development.jsonl.gz) · [Confirmation checkpoints](confirmation.jsonl.gz)

All six preselected runtime cases happened to have the same final and cavity positions. A seventh, deliberately selected run tested the largest loss, DS26-0066. The reduced worker independently reproduced the archived cavity positions in both arms. Its error was 2.389 km with zero calibration and 2.370 km with fitted calibration. Full v5 achieved 1.244 and 1.218 km respectively. This diagnostic is excluded from the six-case runtime statistic. [Fitted chart](DS26-0066/position-errors-fitted_c.png) · [Zero-calibration chart](DS26-0066/position-errors-c0.png) · [Worker output](DS26-0066/predictions.jsonl)

## Calibration and frequency fit

Both calibration settings used the same observations, candidate identities, region, other priors and search budgets. The common initial branch was chosen using zero calibration, as in original v5. The numbers below are for the cavity cutoff. Frequency RMS is the median of the per-recording conditional residual RMS values.

| Dataset and calibration | Median error (km) | P95 (km) | Maximum (km) | Within 5 km | Median conditional RMS (Hz) |
|---|---:|---:|---:|---:|---:|
| DS26, zero | 0.988 | 3.084 | 7.269 | 125/127 | 70.751 |
| DS26, fitted | 0.999 | 3.126 | 6.858 | 125/127 | 70.722 |
| DS29, zero | 0.753 | 1.210 | 1.320 | 8/8 | 77.221 |
| DS29, fitted | 0.742 | 1.312 | 1.458 | 8/8 | 77.276 |

On DS26, fitting calibration reduced the cavity median residual RMS by 0.029 Hz while median position error rose from 0.988 to 0.999 km. On DS29 it increased median residual RMS by 0.055 Hz while median position error fell from 0.753 to 0.742 km. Each stopping point lists how many recordings supplied a conditional RMS. [Recording-level frequency and position errors](checkpoint-errors.csv)

## What the new worker runs

The reduced worker runs six of v5's eighteen named numerical stages. It uses the original detector observations, track preparation, orbit catalogue, native objective and orbit priors. At initial assignment, v5 chooses its winning hypothesis and its first track mask using only the zero-calibration fit. The reduced worker still ranks the same three branches. It skips their unused fitted-calibration fits and the zero-phase diagnostic controls. Both calibration settings run through the remaining position fits. The worker reuses the previous-catalogue state across these fits and skips a cavity refit if no change has positive predictive gain. It returns its two positions directly. [Worker implementation](../../tools/pipeline_eval/variants/v5_core.py)

An independent execution trace on DS29-0082 counted the named Python functions entered by each worker, including forked numerical children. Within the localization analysis, application and two candidate modules, the count fell from **299 functions in 63 files to 189 in 37 files**. Across the complete frozen Python source and the two candidate modules, including input preparation and validation, it fell from **1,544 in 228 files to 1,404 in 196 files**. Those counts describe the path exercised on this recording. Both workers load the same native kernel, third-party libraries and frozen scientific implementation. [Full v5 trace](footprint/v5_lean.json.gz) · [Reduced worker trace](footprint/v5_core.json.gz)

## Fresh positions and runtime

Both workers started with the same native detector outputs and causal orbit data. The full numerical control already had evidence rendering disabled. Each pair ran on the same single logical CPU with one numerical thread. The order was counterbalanced on a shared Intel Core Ultra 9 285K host. Raw-IQ acquisition, the GLRT and figure generation are outside this measurement. The six reduced runs reproduced all twelve expected cavity-stage coordinates exactly. [Paired predictions and input digests](paired.jsonl.gz) · [Runtime rows](paired-runtime.csv) · [Fresh worker chart](figures/fitted_c/v5_core.png)

| Recording | Full numerical v5 (s) | Reduced v5 (s) | Paired speedup |
|---|---:|---:|---:|
| DS26-0036 | 204.05 | 116.55 | 1.75× |
| DS26-0122 | 513.34 | 334.60 | 1.53× |
| DS26-0237 | 253.45 | 130.98 | 1.94× |
| DS29-0082 | 146.30 | 63.09 | 2.32× |
| DS29-0174 | 279.79 | 140.78 | 1.99× |
| DS29-0247 | 320.13 | 205.75 | 1.56× |

Median wall time fell from **266.62 to 135.88 seconds**, a **1.96×** ratio of medians. The median of the six paired ratios was **1.84×**. The worker was faster on all six, with one pair exceeding 2×. The result falls short of the predeclared 2× median-time target. Five cases have one timing pair on a shared x86 host. Embedded end-to-end runtime remains unmeasured.

An earlier DS26-0036 pair took 161.12 and 130.82 seconds and used the previous launcher for the control. The primary comparison uses the common launcher versions across all six cases. During the repeat the supervisor exited after recording the full control. The reduced worker returned its expected coordinates in 95.01 seconds internally, and a fresh supervised run supplied the 116.55-second wall measurement above. The earlier measurements are retained for comparison. [First pair](first-smoke-pair.jsonl.gz) · [Worker receipt without a supervisor wall time](smoke-worker-without-wall-time.json)

## Reproduce the comparison

The figure command below uses the saved numerical evidence and runs without the radio archive. The receiver benchmark command runs fresh native-input fits on the corpus host.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.prefix_figures --out /tmp/v5-stopping-points
.venv/bin/python -m tools.pipeline_eval run --panel smoke --variant v5_lean --variant v5_core --jobs 1 --pin --require-inputs --out /tmp/v5-pair
.venv/bin/python -m tools.pipeline_eval run --panel ds26-common127 --case DS26-0066 --variant v5_core --pin --require-inputs --out /tmp/v5-diagnostic
```

To re-extract the archived numerical states, run the following commands on the corpus host. Fresh timing pairs use the six case IDs, counterbalanced order and one-core restrictions in the protocol. The figure generator checks that both workers received the same inputs and that all twelve pairs of calibrated positions agree with their respective original numerical stages within one millimetre.

```sh
EVIDENCE=/tmp/v5-stopping-evidence
RUNS=/tmp/v5-timing-pairs
.venv/bin/python -m tools.pipeline_eval.qualification.v5_prefix_audit --cohort development --jobs 2 --out "$EVIDENCE/development.jsonl.gz"
.venv/bin/python -m tools.pipeline_eval.qualification.v5_prefix_audit --cohort confirmation --jobs 2 --out "$EVIDENCE/confirmation.jsonl.gz"
pair() {
  .venv/bin/python -m tools.pipeline_eval run --panel "$1" --case "$2" --variant "$3" --variant "$4" --jobs 1 --pin --require-inputs --out "$RUNS"
}
pair smoke DS26-0036 v5_lean v5_core
pair ds26-common127 DS26-0122 v5_core v5_lean
pair ds26-common127 DS26-0237 v5_lean v5_core
pair smoke DS29-0082 v5_core v5_lean
pair roof16 DS29-0174 v5_lean v5_core
pair roof16 DS29-0247 v5_core v5_lean
.venv/bin/python -m tools.pipeline_eval.qualification.prefix_figures --collect "$RUNS" --data "$EVIDENCE" --out /tmp/v5-stopping-points
```

For the separate function counts, run `.venv/bin/python -m tools.pipeline_eval.qualification.trace_prefix --case DS29-0082 --method v5_core --out /tmp/core-functions.json.gz`. Repeat with method `v5_lean` and a separate output file. The timing comparison uses uninstrumented workers.
