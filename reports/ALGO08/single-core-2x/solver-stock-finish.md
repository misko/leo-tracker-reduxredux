# The signed phase prior explains the northern boundary shift

The collapsed solver's northern boundary endpoints exactly reproduce the stock **pre-signed predictive fit**. The stock signed phase update then moves both endpoints to the west bound. Applying that released update directly to the accepted collapsed fit restored both stock positions, owner maps, paths and complete numerical grids on the northern simulation and DS30-0016. The direct route took 7.455 CPU seconds on the northern input and 2.952 on DS30-0016, including the original publication checks and grid construction. [Paired measurements and causal trace](measurements/stock-finish.json) · [Frozen experiment choices](solver-stock-finish-protocol.md)

## Isolating the change in the objective

All northern runs use the same Q15 detections, offered square, archive, and released compact box optimizer. Stock selected the same curved track assignments and aliases, mask, powers, causal distribution, and two predictive entries as the collapsed run. The published maps contain 285 curved and 17 predictive observations per arm. After accepting its predictive fit, stock separately qualified and accepted its signed phase prior. The collapsed repair took the linear add-back because its curved mask had no dropped rows. Its final predictive pair used the ordinary phase means. [Stock signed context](../../../src/leo/analysis/localization_v3/signed_context.py) · [Collapsed linear admission](../../../tools/pipeline_eval/variants/algo08_collapsed_linear.py)

| Northern stage | East, north at `c = 0` (km) | East, north at fitted `c` (km) |
|---|---|---|
| Stock conservative recovery | −12.401754, −0.118554 | −11.934045, −0.146205 |
| Stock weighted curved fit | −12.254031, 0.121124 | −12.192216, −0.041099 |
| Stock predictive fit and collapsed selected fit | −12.259249, 0.104569 | −12.189809, −0.031876 |
| Stock signed fit and direct signed finish | −12.500000, 0.034477 | −12.500000, −0.099028 |

The upstream collapsed curved fit starts from the nominated point and posterior phase and can terminate before five rounds. Both selected predictive fits in this replay start cold at the offered center with zero phase reference and run five original phase refreshes. The ordinary fit remains inside the box during its first round. The adjusted fit reaches the west bound in its first round and remains there. Both finish with the original small bounded step condition. [Optimizer](../../../tools/pipeline_eval/variants/compact_cavity_optimizer.py) · [Collapsed schedule](../../../tools/pipeline_eval/variants/algo08_collapsed.py)

In the controlled reconstruction, replacing only the eight phase-prior means in the collapsed selected context reproduced every stock round's start and endpoint, final phase reference and final objective in both arms. The ordinary means are zero. The signed means range from −2.212 to −0.148 seconds. Holding each reconstruction's final phase reference fixed, moving one meter east from the stock bound point changed the optimizer's squared residual in opposite directions. The ordinary fit's sum of squared residuals dropped by 0.000497 at zero calibration and 0.000720 with fitted calibration. The adjusted fit's sum rose by 0.001487 and 0.001343. These are local changes within each reconstruction, using the released optimizer's one-meter forward step. [Objective samples and weight comparison](measurements/stock-finish.json)

## Direct signed update from the collapsed fit

The released signed context needs the final curved node, retained mask, family powers, causal distribution, qualified predictive entries and paired incumbent. Those are all available after collapsed recovery. The prepared scan also already holds its causal history, forecast and observation inventory. The adapter supplies those values to the stock signed context and adopts its result only when the stock paired gates pass. It adds one conditional fit between collapsed recovery and the original guard and evidence construction. [Scoped implementation](../../../tools/pipeline_eval/variants/algo08_collapsed_signed_finish.py)

The history is assembled for each scan from Space-Track catalogue snapshots collected in the preceding 72 hours, with both collection times and element epochs at or before the capture cutoff. Each forecast transition uses three chronologically ordered, distinct TLE epochs, with along-orbit differences derived from SGP4 predictions. The forecast sets a chronological prefix boundary. Signed feature choice uses the prefix with one satellite partition withheld. The prefix model must beat the original prior on the later pre-capture transitions and on the held satellite partition before an all-past coefficient is fitted. The released routine binds the forecast to the history digest and checks the scan clock and source times. The supplied sky screen determines candidate eligibility. The coefficient is fitted from TLE differences with no surveyed position or radio residual as an input. [Archive preparation](../../../src/leo/operations/localization_v3_inputs.py) · [Pre-RF transitions](../../../src/leo/analysis/localization_v3/phase_prior.py) · [Signed qualification](../../../src/leo/analysis/localization_v3/signed_phase.py)

Both scans selected the standardized signed feature, with coefficients −0.270298 on north and −0.257824 on DS30-0016. The two capture histories have distinct digests and contain 23 and 20 source snapshots, respectively. Their latest qualifying update targets preceded the capture cutoffs by more than three hours. Both routes on each scan reproduced its own signed qualification and phase-prior centers. [Per-scan history bindings](measurements/stock-finish.json)

| Saved input | Stock CPU (s) | Collapsed CPU (s) | Direct signed CPU (s) | Signed update / exterior guard CPU (s) | Exact stock owners per arm | `c = 0` / fitted `c` horizontal error (km) |
|---|---:|---:|---:|---:|---:|---:|
| North, 100 m inside | 8.122 and 8.449 | 4.375 | 7.455 | 0.204 / 2.750 | 302 | 0.106 / 0.141 |
| DS30-0016 | 3.284 | 2.789 | 2.952 | 0.136 / 0 | 109 | 1.644 / 1.662 |

Both stock outputs and the direct finishes agreed exactly within each input after dropping the grid elapsed field. The grid evaluated 137 points on north and 179 on DS30-0016. North's signed update restored the local bound hits and triggered the original far-exterior diagnostic, which retained both positions after evaluating 96 probes. The interior roof fits bypassed that extra work. The ordinary collapsed RF RMS was slightly lower on north despite larger horizontal errors. The signed score check and postfit geographic error answer different questions. This route inherits its accepted collapsed support. The two saved development inputs leave the earlier dense owner loss unresolved. [Physical reference](../location-audit/README.md) · [Northern reference scores](batch-publication.md) · [Dense owner count](repair-dense-probe.md)

## Screened nomination with the original finish

The predeclared hybrid preserved the original paired endpoints, RF RMS, owners, optimizer paths and grids in both cases. Two refreshes on each proposal followed by the remaining three on the winning branch reduced the northern branch fit count from 15 to 9 and the roof count from 10 to 7. Initial selection CPU changed from 0.591 to 0.535 seconds on the reversed northern pair and from 0.289 to 0.284 on the roof. The original stock finish retained all prospective fitting and acceptance gates. Complete northern CPU changed from 8.122 to 8.281 seconds in the first order and 8.449 to 8.019 in reverse. The roof changed from 3.284 to 3.303. These small comparisons do not establish a material whole-solver gain for screened nomination. [Hybrid scope](../../../tools/pipeline_eval/variants/algo08_stock_finish.py) · [Nomination screen](../../../tools/pipeline_eval/variants/v5_screen_winner.py)

## Reproduction

The trial binds the saved detector bytes and original causal inventory and verifies the selected frozen `spec.json` and its source pins. The `control` and `hybrid` modes use the `shared-tables` freeze. The `collapsed` and `signed-finish` modes use the matched `collapsed-repair` freeze. `--control-trace` adds the off-clock signed-mean reconstruction to a collapsed replay when the control used the same detected rows, region, and archive. The original grid and guard remain inside the saved-solve timing. Fifteen component tests passed, covering the screen, scoped update, causal binding, and paired fallback. [Runner](solver_stock_finish_trial.py) · [Input and freeze pins](measurements/stock-finish.json)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$freeze:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/solver_stock_finish_trial.py \
  "$mode" "$saved_detections" "$freeze/spec.json" "$archive" "$offer" "$new_receipt" \
  "$native_sha256" "$specification_sha256" "$archive_sha256"
```
