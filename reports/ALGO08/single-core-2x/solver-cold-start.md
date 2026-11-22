# Exact overlap at the start of refreshed fits

The first full likelihood evaluation of each cold initial branch repeats its ranking evaluation. Reusing it saved two calls on the physical input and three on the northern simulation. The repeated calls accounted for under 10 ms of CPU on each replay. The instrumentation found zero duplicate fixed-zero native evaluations between distinct ranked branches or between the initial and conservative recovery scopes. The experimental overlay stays out of the candidate launcher. [Paired measurements](measurements/cold-start.json)

## Scope of reuse

Initial discovery proposes branches at the centre and at the four region corners. It deduplicates their owner and alias signatures, ranks the remaining branches with a fixed-zero calibration residual at the centre and sends up to three branches through five phase refreshes. The first refresh starts at the same coordinates and zero orbital phase reference used for ranking. Later refreshes use the preceding position and posterior phase. The conservative unit-phase fit uses the genuine previous orbital input and its retained mask. The conservative causal fit can start at the same coordinates with different phase prior widths. The audit hashes each numeric argument to the underlying native likelihood at the exact centre and zero phase reference, including the masked response, current feature matrix, active noise vector and group map. [Initial selection](../../../tools/pipeline_eval/variants/v5_core.py) · [Phase refresh](../../../src/leo/analysis/localization_v3/position.py) · [Conservative recovery](../../../src/leo/analysis/localization_v3/conservative_recovery.py)

The experiment keeps at most three ranked residuals within one initial selection. It requires exact equality of the scan and native implementation identities, explicit region, previous orbit input, owner labels, aliases, reference, prior widths, observation mask, noise and the numerical inputs to geometry and features. Snapshots are bounded to 8 MiB per score. A key mismatch, oversized snapshot or different starting coordinate takes the release path. A hit supplies a private copy at the optimizer's first call. The scope discards entries before recovery. The component tests cover changed model inputs, mutable hardware, the orbital prior, and signed zero at the start. [Overlay](../../../tools/pipeline_eval/variants/algo08_cold_start.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_cold_start.py)

## Saved replay

Both comparisons use matching saved detections, causal archive reuse, coarse salvage statistics, and the existing exact re-use of an unchanged recovery pair. The physical control and the simulated candidate ran first in their respective pairs. All solves ran on one low-priority pinned CPU with one numerical thread. [Trial runner](solver_cold_start_trial.py) · [Previous recovery reuse](solver-recovery-reuse.md)

| Input | Unique centre native calls in control (ranking / refresh / causal / unit) | Ranking-to-refresh matches | Total ranking evaluation CPU (ms) | Snapshot and lookup CPU (ms) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|---:|
| DS30-0016, physical | 2 / 2 / 2 / 1 | 2 | 2.00 | 0.11 | 4.682 → 4.640 |
| North far, simulated receiver outside offer | 5 / 3 / 4 / 1 | 3 | 9.30 | 0.54 | 11.233 → 10.949 |

Total ranking evaluation CPU excludes the time spent hashing native inputs. The northern total includes two ranking evaluations for branches that did not advance. Unrelated scan preparation varied by 50 ms on the physical pair and by 269 ms on the simulation pair. It accounts for the apparent difference in whole-solver CPU.

The entire five-refresh `NormalPosition` constructor cost across the initial fits and conservative recovery was 9.16 ms for DS30-0016 and 28.83 ms for north far. The `AnchoredFamilies` layout inside that cost accounted for 7.40 and 22.09 ms, respectively. It recomputes anchor aliases even when supplied aliases override them. The constructor totals cap the potential gain from removing those calculations or sharing invariant observation and nuisance layouts across the phases on these inputs. Both totals are below 0.26% of complete-solver CPU. The existing DS30-0374 `cProfile` trace recorded 1.27 seconds for 220 `NormalPosition` constructions, with 0.62 seconds in related `AnchoredFamilies` calls across the trace. These aggregate profiled times include other solver stages.

| Input and calibration arm | Latitude, longitude | Owners | Horizontal error (km) | Solver RF RMS (Hz) |
|---|---|---:|---:|---:|
| DS30-0016, `c = 0` | 37.834938, −122.491301 | 109 | 1.644 | 109.375 |
| DS30-0016, fitted `c` | 37.835682, −122.494190 | 109 | 1.662 | 109.479 |
| North far, `c = 0` | 47.785644, 16.798538 | 228 | 52.455 | 37.951 |
| North far, fitted `c` | 47.753706, 16.798538 | 228 | 52.491 | 37.533 |

Both arms of each comparison reproduced the exact decisions, endpoints, owner maps, recovery trims, shortlist, objective replay, and all fields of the complete grid after excluding elapsed times. DS30-0016 evaluated 179 grid points, and north far evaluated 137. The northern false fix remains on the offered boundary. The reference coordinates were used only for scoring. [Physical reference](../location-audit/README.md) · [Simulated reference scores](../regional-release/blind-scores.csv)

## Reproduce

Use the pins in the paired measurements with the release interpreter and saved detections. The two component suites passed 17 tests. [Measurements and input hashes](measurements/cold-start.json)

```sh
work=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
for mode in control reuse; do
  flock "$work/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_cold_start_trial.py \
    "$mode" "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
done
```
