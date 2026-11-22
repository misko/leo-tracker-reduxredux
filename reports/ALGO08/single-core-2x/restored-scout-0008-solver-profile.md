# Dense DS30-0008 solver profile

The corrected physical pair spent **80.570 seconds deployed and 67.792 seconds candidate** between saved detections and the position decision. This interval was **27.507 seconds above half-time**. One saved profile of the actual candidate detections took **67.759 CPU seconds** and **69.707 elapsed seconds**. It reproduced the complete publication decision, nullable reason, both coordinates and Doppler residuals, 4,472 owners per arm, the optimizer path, all 179 grid locations and their scores, and both zero endpoint objective-replay differences. [Profile receipt](measurements/restored-scout-0008-solver-profile.json) · [Actual publication audit](measurements/restored-scout-0008-audit.json)

## Where the solve grew

The first two columns use the same 25 km roof offer, screening center, and pinned solver sources. The southern column uses the earlier screened-stock implementation with deployed salvage. These are cumulative process CPU seconds within disjoint top-level boundaries. [DS30-0374 profile](measurements/guarded-packed-residual.json) · [Southern profile](measurements/screened-stock-profile.json)

| Boundary | DS30-0008 | DS30-0374 | Southern portable containing |
|---|---:|---:|---:|
| Track and causal preparation | 8.550 | 5.731 | 6.455 |
| Initial ranking and phase fits | 17.398 | 6.016 | 6.254 |
| Conservative recovery | 14.706 | 5.155 | 34.348 |
| Family history | 8.955 | 3.788 | 3.465 |
| Signed update | 3.166 | 0.090 | 0.991 |
| Complete-family cavity | 6.628 | 3.470 | 5.211 |
| Selected evidence and grid | 7.486 | 3.940 | 4.200 |

Initial ranking used 8.130 seconds and the nine screened fits used 9.268. The two conservative paired fitting gates used 8.192 seconds. Salvage used another 6.241 seconds, including 5.028 for fine support evaluation and 0.170 for guarded coarse statistics. On the different southern offer, deployed salvage used 31.602 profiled seconds. Turning on guarded salvage there preserved all proposals and owners, with 10.986 directly timed CPU seconds in salvage. The two roof recordings used the same region and show a broader workload increase than the southern salvage hotspot. [Southern guarded salvage](screened-stock-salvage.md)

## What could affect the full gap

The native likelihood port used 21.048 profiled seconds across the stages above. Its 1,383 foreign calls used 14.099 seconds, including 356 posterior-export calls. Its 83 calls to the dense Python fallback used 5.120 seconds. `NormalPosition.calculate` accounts for 15.051 seconds of the complete port cost, against 5.383 for the history model and 0.614 for discovery likelihood. DS30-0374 made 1,323 port calls and spent 3.904 seconds in C and 0.862 in its 76 dense Python fallbacks. DS30-0008 used 3.6 times the C time on 1.11 times the total port calls. This profile measures call costs and does not establish which design dimensions or variational iteration counts explain the increase. [Profile counters](measurements/restored-scout-0008-solver-profile.json) · [Likelihood implementation](../../../src/leo/analysis/localization_v4/native_bound.py)

The raw candidate needs **21.423 seconds less CPU and 26.375 seconds less elapsed time** to halve full publication. Even removing the complete measured likelihood port would fall below both reductions under a direct profile-to-publication transfer. Adding all 8.130 seconds of ranking to that hypothetical saving counts overlapping likelihood calls. A larger redesign needs to cover the initial and conservative fit schedules together, which consume 32.104 profiled seconds. Prioritize the per-update shared/private posterior factorization and dense fallbacks in `NormalPosition`, then reduce independently measured full-sky ranking and fine salvage work. Preserve the full catalogue, both arm gates and the published objective. The unsuccessful earlier shortened fits and changed support in southern Africa rule out treating fewer fits as an equivalent shortcut. No prototype or timing gain was measured in this profile. [Native factor experiment](solver-native-family.md) · [Earlier shortened fits](solver-stock-finish.md) · [Southern assignment change](portable-south-solver-attribution.md)

## Reproduction

Stage the saved detector and offer with `solver_fused_phase_trial.saved_inputs` using the actual restored pair and its matching frozen specification. The command runs one saved profile with a 165-second cap and writes to fresh local files. [Existing harness](guarded_solver_profile.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
frozen="$bench/integration-restored-scout-graph"
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
archive=/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0008/tle
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$frozen:$release/src:$release" timeout 165 "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/guarded_solver_profile.py "$native" "$frozen/spec.json" \
  "$archive" "$offer" "$new_terminal" "$new_profile"
```
