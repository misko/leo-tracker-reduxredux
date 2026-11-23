# The DS30-0016 gain depends on both the detector and solver

The full-short detector and candidate solver together reduced DS30-0016 errors from **1.644 / 1.661 km** to **0.710 / 0.861 km** in fixed-zero and fitted `c` order. The detector alone reached **1.311 / 1.694 km** with the installed solver. The candidate graph and solver alone reached **1.988 / 1.974 km** with the installed detector. The paired improvement depends on the interaction between the changed detector measurements and the candidate quadratic graph and solver bundle. [Frozen crossover](full-short-crossover-protocol.md) · [Scored results](measurements/full-short-crossover-summary.json) · [Full receipts](measurements/full-short-crossover.json.gz)

## Four cells on one authenticated recording

The southern saved preflight passed with a unique far exterior optimum on both receivers and withheld before rank or fitting. Both physical arms then exited successfully. Their sealed detector packets matched the same signed recording authority, inventory, clocks, 808 original visits and 713 admitted stereo visits. The candidate retained its own full-short recipe and distinct analysis manifest. The two saved runs used those exact unchanged detector packets, the original 25 km square and the original causal archive. The diagonal owner digests, selected support counts and complete grid and path matched the original raw receipts. [Raw pair and original protocol](full-short-physical-protocol.md) · [Exact crossover bindings](measurements/full-short-crossover.json.gz)

| Detector | Graph and solver | Horizontal error, zero / fitted (km) | Frequency RMS, zero / fitted (Hz) | Graph points | Owners per arm | Solve CPU / elapsed (s) |
|---|---|---:|---:|---:|---:|---:|
| Installed | Installed | 1.644 / 1.661 | 109.375 / 109.479 | 374 | 109 | 3.356 / 3.356 |
| Full-short | Installed | 1.311 / 1.694 | 121.526 / 120.291 | 354 | 116 | 3.401 / 3.401 |
| Installed | Quadratic and optimized full catalogue | 1.988 / 1.974 | 109.446 / 109.515 | 392 | 121 | 2.939 / 2.939 |
| Full-short | Quadratic and optimized full catalogue | **0.710 / 0.861** | **108.253 / 108.046** | 395 | 125 | 3.026 / 3.026 |

All four cells returned both positions and a 179-point complete numerical grid, with zero objective replay difference in both calibration arms. Both candidate solver cells ran the original region-first probe on the prepared catalogue. Each evaluated 24 probes, stopped at `eligible_exterior_separation` and continued into its original full-catalogue route. The proof took **0.383 CPU seconds** in the crossover and **0.387** in the raw candidate. Neither candidate route requested an installed-level fallback. The solve clocks include all numerical evidence and charged regional work. The two off-diagonal runs started from saved detections, so they carry no new receiver, raw-to-publication or image timing. [Full route and evidence receipts](measurements/full-short-crossover.json.gz)

## What changes with each component

| Changed component and fixed other component | Endpoint shift, zero / fitted (km) | Signed error change, zero / fitted (km) | Signed RF RMS change, zero / fitted (Hz) |
|---|---:|---:|---:|
| Detector, installed solver fixed | 0.456 / 0.790 | −0.333 / +0.033 | +12.151 / +10.812 |
| Detector, candidate solver fixed | 1.414 / 1.360 | −1.278 / −1.114 | −1.193 / −1.469 |
| Solver bundle, installed detector fixed | 0.359 / 0.413 | +0.344 / +0.313 | +0.071 / +0.036 |
| Solver bundle, full-short detector fixed | 0.646 / 0.833 | −0.601 / −0.833 | −13.274 / −12.245 |

Changing only the receiver substantially raised RF RMS under installed inference and made fixed-zero location better while fitted location moved slightly farther from reference. On the full-short detector output, adopting the candidate graph and solver improved both location and RF. On installed detectors, that same bundle added twelve measurements and moved both positions away from reference. The observed detector effect on horizontal error differs between solvers by **0.945 km** in the fixed-zero arm and **1.146 km** in the fitted arm. These two crossover fits distinguish the detector from the entire candidate graph, inference and region bundle. They leave attribution among the bundle's internal changes open. [Signed contrasts](measurements/full-short-crossover-summary.json)

For owner comparisons, the join uses the original receiver, channel, RF, edge and signed sample-counter epoch. CFO matches use the exact selected native value. With one detector fixed, the solver bundle kept the NORAD and role of all shared owners. It retained **109** shared measurements on the installed detector and **114** on the full-short detector. Switching detectors changed CFO at **93 of 106** shared counters under installed inference and **97 of 111** under candidate inference. The other 13 and 14 shared counters respectively retained the same CFO and exact fractional factor. Both calibration arms showed the same overlap counts. [Physical owner audit](measurements/full-short-crossover-summary.json)

## Reproduce

The sealed paired root is `/var/tmp/leo-full-short-DS30-0016-pair` and the original preflight receipt is `/var/tmp/leo-full-short-DS30-0016-far-gate.json`. Use fresh output paths. `run candidate-stock` applies installed inference to the actual candidate detector, and `run stock-candidate` applies the candidate graph and solver to the actual installed detector. Both require authentic raw diagonal receipts and the locked offer before opening the saved solve. After both results seal, `score DIR SUMMARY FULL` reads the physical reference with the local repository root, `src` and trial directory on `PYTHONPATH`. Forty-one focused tests passed. [Runner](full_short_crossover.py) · [Component tests](../../../tests/pipeline_eval/test_full_short_crossover.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 70s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/full_short_crossover.py \
  run "$cell" "$output" --pair /var/tmp/leo-full-short-DS30-0016-pair
```
