# Paid quadratic packets with the certified solver

The paid quadratic receiver and certified solver failed the frozen accuracy screen on both containing offers. DS30-0016 rose to **8.623 / 8.621 km** in the fixed-zero and fitted calibration arms, versus **1.644 / 1.661 km** from the complete old-receiver control. The southern containing offer rose to **1.931 / 2.726 km**, versus **0.817 / 1.101 km** from both the old-receiver control and installed v3. Both complete and paid southern displaced offers reached the original two-receiver exterior decision. [Frozen protocol](paid-certified-protocol.md) · [All six scored fits](measurements/paid-certified-summary.json) · [Sealed fit receipts](measurements/paid-certified.json.gz)

## Where the containing fits diverged

| Saved recording | Compared route | Horizontal error, zero / fitted (km) | RF RMS, zero / fitted (Hz) | Owners per arm |
|---|---|---:|---:|---:|
| DS30-0016 | Complete packet, previous full signed solver | 1.644 / 1.661 | 109.375 / 109.479 | 109 |
| DS30-0016 | Complete packet, certified solver | 1.644 / 1.661 | 109.375 / 109.479 | 109 |
| DS30-0016 | Paid quadratic packet, previous full signed solver | 0.247 / 0.182 | 121.482 / 121.379 | 36 |
| DS30-0016 | Paid quadratic packet, certified solver | **8.623 / 8.621** | 112.389 / 112.390 | 18 |
| South containing | Complete packet, previous full signed solver | 0.817 / 1.101 | 6.502 / 6.392 | 266 |
| South containing | Complete packet, certified solver | 0.791 / 1.086 | 6.499 / 6.391 | 266 |
| South containing | Paid quadratic packet, previous solver | 1.266 / 1.109 | 6.388 / 6.322 | 118 |
| South containing | Paid quadratic packet, certified solver | **1.931 / 2.726** | 19.038 / 19.037 | 90 |

The full physical packet entered the certified catalogue closure with 127 curved points. Its original support gates rejected all 127 at the proposed state, so it paid for the full signed fallback at **1.335 CPU seconds** and exactly reproduced the archived fit, ownership and numerical path and grid. The paid physical packet had 49 curved points. The first checks retained 18, salvage recovered another 17 and the second checks returned to 18. The warm signed pair passed. Both endpoints triggered the existing exterior check, which evaluated 25 probes in **1.959 CPU seconds** and did not find enough evidence to veto. The result matches the global gates but lies about seven kilometres farther from the evaluation reference in each arm. On the identical paid packet the RF RMS fell by about 9 Hz from the earlier full signed solve, while horizontal errors increased by 8.376 and 8.440 km. [Physical support, fits and exterior probes](measurements/paid-certified.json.gz)

The complete southern containing packet kept 266 points. Its family closure admitted one exterior family in the first round, then the warm signed pair passed. The paid containing packet entered with 118 curved points and retained 90 from the first support check through publication. The signed pair also passed. Relative to the earlier full signed solve on the same paid packet, fixed-zero error rose by 0.665 km, fitted error rose by 1.617 km and RF RMS rose by about 12.65 / 12.72 Hz. Across complete and paid certified southern outputs, 52 owners shared the identical physical observation and CFO, and all 52 agreed on satellite and role. The other 214 complete owners and 38 paid owners had no mate in the other output. The physical pair shared 11 identical owners, lost 98 from the complete output and gained seven in the paid output. [Owner and per-arm comparisons](measurements/paid-certified-summary.json)

The existing interval certificate examined 237 possible supports on the paid physical packet, removed 198 by infeasibility and 13 by support-length ranking, and ran 26 exact profiles. It had no qualifying fine supports to prune on either paid southern offer, although the shared coarse geometry ran there. On the complete displaced southern packet the certificate removed 3,074 of 3,210 supports. Both displaced cells ran 96 exterior probes with both receivers. The paid exterior stage used **1.950 CPU seconds** versus **2.848** on the complete packet. The installed south comparators use a different native detector and share the same raw authority, catalogue and offered regions. [Activation and qualification receipts](measurements/paid-certified-summary.json)

## Charged times and preparation audit

| Same offered region | Measured saved solve CPU, complete → paid (s) | Solve CPU with released preparation, projected (s) | Acquisition + solve CPU, projected (s) |
|---|---:|---:|---:|
| DS30-0016 containing | 7.296 → 7.826 | 3.604 → 4.365 | 10.196 → 7.832 |
| South containing | 6.654 → 6.249 | 3.153 → 2.822 | 12.574 → 8.016 |
| South displaced | 9.149 → 7.565 | 5.764 → 4.614 | 15.185 → 9.807 |

The wrapper used to time the six fits captured the bare preparation function before the release installed its causal/parser and regional capture wrappers. Those measurements include the resulting 4.993–5.442 CPU seconds of preparation. The fixed wrapper captures the active release function. Paired preparation-only audits reproduced the **exact normalized solver inputs in all six cells**, including orbit bank array bytes, graph, noise and phase history. Released preparation used **1.702–2.042 CPU seconds**. The projected solve column substitutes those measured preparation costs and retains the original charged fit, qualification, numerical grid, exterior and fallback times. There were six fits total. The separate audit stopped before each optimizer. [Preparation audits, numerical identity and solve projections](measurements/paid-certified-preparation.json)

The acquisition projection replaces the original native-call CPU with the archived cost of calls on the paid stereo visits, preserves the rest of the measured acquisition and adds the measured maximum-margin selection. It excludes PNG rendering, file-wait changes and any raw retry. The complete and paid controls used the original two-scan receiver's ledger and exact sealed packet digests. Only the paid packets use the six-point quadratic graph. The fit comparisons establish a regression from applying the certified joint route to those sparse packets even with the original exterior and numerical evidence. [Paid visit charges](paid-graph.md) · [Scored fit and acquisition components](measurements/paid-certified-summary.json)

## Reproduction

The six fit receipts retain the original measured driver digest in commit `b8c472b78`. Use the shared single-core wrapper below to replay only preparation on the fixed driver. Use fresh paths for both `scope` values (`original-instrumentation` and `released`), the three `case` values (`DS30-0016`, `south-containing`, `south-far`) and both `mode` values (`complete`, `quadratic`). Pass the saved fit archive, directory of preparation-only receipts and a new output to `paid_certified_preparation.py` using the same CPU and numerical-thread settings. The original scorer was called only after the six fit receipts were complete. [Fit runner](paid_certified_trial.py) · [Preparation comparison](paid_certified_preparation.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 75s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/paid_certified_trial.py \
  run "$case" "$mode" "$out/$case-$mode-$scope.json" --preparation-audit "$scope"
```

Twenty-seven focused tests passed. They include original packet and paid-mask binding, common-recording checks for the independent detector, separation of CFO changes from satellite reassignment, accounting and actual exterior classification. [Component tests](../../../tests/pipeline_eval/test_paid_certified_trial.py)
