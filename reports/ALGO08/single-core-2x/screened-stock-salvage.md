# Guarded salvage with the screened stock solver

On the saved southern African containing offer, enabling the existing guarded salvage overlays preserved all 22 returned trim alternatives, selected trims, retained observations, both endpoints and Doppler residuals, and the final owner maps. The saved solve used **35.134 CPU seconds**, compared with **50.885** in the archived screened stock solve and **60.305** in the archived deployed solve. The archived controls used different instrumentation and process invocations. India exercised the same solver with no salvage calls, and both fits and owner maps matched. [Measured evidence](measurements/screened-stock-salvage.json.gz) · [Archived controls](measurements/screened-stock-recovery-containing.json)

## Matched inference

The adapter runs the actual frozen `6703ec6d…` screened stock publication launcher with the original solver options. It substitutes saved native detections at the analysis callback and scopes two existing overlays to the solver call. `salvage_statistics()` uses the existing guarded quadratic computation for coarse ranks with the tiled routine as its fallback. `stable_pruning("gate")` retains the existing fine supports and phases and skips the polynomial noise test when an earlier stock gate already disqualifies that support. The optional endpoint bound stays off. The runner verifies both frozen specifications and source hashes, and validates the original supplied search and screening centers, detector document, and capture-time orbit archive on each case. Public coordinates enter the subsequent horizontal error calculation. [Runner](screened_stock_salvage_trial.py) · [Screened freeze](measurements/screened-stock-freeze.json) · [Covariance parent freeze](measurements/covariance-posterior-freeze.json) · [Coarse statistics](../../../tools/pipeline_eval/variants/algo08_salvage_statistics.py) · [Fine gates](../../../tools/pipeline_eval/variants/algo08_salvage_bound.py)

| Saved simulation | Horizontal error, fixed-zero / fitted | Conditional Doppler RMS, fixed-zero / fitted | Exact deployed owners per arm | Solver CPU, deployed / archived screened / guarded |
|---|---:|---:|---:|---:|
| Portable southern Africa | 0.351 / 0.583 km | 24.107 / 24.089 Hz | 4,149 | 60.305 / 50.885 / 35.134 s |
| India waveform | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 517 | 9.785 / 5.747 / 5.652 s |

The southern replay entered one salvage call with nine rejected fragments. It returned the same 22 alternatives in the same order per fragment. The five selected alternatives had 123, 164, 144, 19 and 157 points, with exact phase, alias, cost, RMS and sigma diagnostics. The incoming and immediate outgoing masks held 3,534 and 4,141 observations, respectively, with the same identities as the deployed trace. The original repaired gate then dropped the same 19-point fragment. The six archived stage checks matched, including the signed incumbent and accepted complete-family cavity. The archived deployed objective replay also matched exactly. Both arms published a fix on both sites. The candidate produced complete position grid and optimizer path digests for future checks. The archived controls lack those full grid and path objects on these saved offers. [Deployed trace](measurements/portable-south-solver-attribution.json.gz) · [Measured comparisons](measurements/screened-stock-salvage.json.gz)

## Cost and scope

All 35 southern coarse windows used the guarded statistics with zero fallbacks. The fine stage profiled all 65,375 support trials. Existing early rejection gates avoided 64,200 of those trials’ polynomial noise tests, leaving 1,175. The guarded salvage call used 10.986 CPU seconds. An existing stock profile attributed 31.602 cumulative CPU seconds to salvage, including 15.641 in 65,410 profile calls and 9.770 in 65,375 noise tests. Conservative stage elapsed time in the archived unprofiled trace and guarded trial was 31.584 and 13.662 seconds, respectively. The 15.751-second whole-solve decrease is an archived comparison. The results combine the coarse overlay and gate reordering, so their standalone savings remain unmeasured. India’s 0.095-second whole-solve difference is run-to-run variation in a case where neither overlay executed. [Archived stock profile](measurements/screened-stock-profile.json) · [Guarded counters](measurements/screened-stock-salvage.json.gz)

These two containing simulations show that the earlier southern loss of support is avoidable with this same screened stock incumbent and conservative gate history. The coarse calculation can change finite-precision ranking away from the guarded fallback cases. The measured parity covers only these inputs. Both replays ended after building the selected evidence packet. Raw acquisition, figure publication, omitted offers, and physical qualification were outside this measurement.

## Reproduction

Run in a configured checkout with its project Python. The output directory must be new. The runner uses the release Python in each child and executes exactly one guarded solve per saved offer.

```sh
bench=/tmp/leo-algo08v2-2x-bench
python_bin=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$python_bin" -BPs reports/ALGO08/single-core-2x/screened_stock_salvage_trial.py run \
  "$bench/portable-v5-geodiverse" "$bench/integration-screened-stock-finish" \
  "$bench/integration-covariance-posterior" "$bench/screened-stock-salvage-next"
```

## Integrated launcher and the India omission

The subsequently integrated `c803a300…` launcher ran one saved India omission with its original 25 km search and screening offer. The public reference is 1.500 km outside. Both arms still returned the same false fixes as deployment and screened stock. Horizontal errors were 1.580 km for fixed-zero and 1.534 km for fitted, with 15.631 and 15.451 Hz conditional Doppler RMS and the same 517 observation owners in each arm. All six archived stage checks and the complete regional guard diagnostics matched. Both receivers preferred the same probed point 3.125 km outside the nearest face. The existing veto requires at least 25 km exterior clearance for this offer. The solve took 6.530 CPU seconds and never called salvage. [Integrated omission](measurements/screened-tiled-india-omitted.json.gz) · [Integrated freeze](measurements/screened-tiled-freeze.json) · [Archived omissions](measurements/screened-stock-recovery-omitted.json)

The integrated replay uses the frozen launcher’s own overlays. To repeat it, use the same environment and lock as above with the integrated subcommand and a fresh output path.

```sh
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$python_bin" -BPs reports/ALGO08/single-core-2x/screened_stock_salvage_trial.py \
  integrated-omission "$bench/portable-v5-geodiverse" \
  "$bench/integration-screened-tiled-finish" "$bench/screened-tiled-india-omitted-next"
```
