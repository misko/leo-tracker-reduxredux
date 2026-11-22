# Cyclic collection during saved solver preparation

Deferring automatic cyclic collection during scan preparation saved **0.53 CPU seconds (11.5%)** on DS30-0016 and **0.63 CPU seconds (5.6%)** on the northern public simulation. Both totals include a final full collection. Both calibration arms reproduced their decisions, positions, owners, and complete numerical grids on each input. [Paired measurements](measurements/solver-gc.json)

## Where the collector ran

The release interpreter was CPython 3.12.14 with its default `(700, 10, 10)` collection thresholds. A `gc.callbacks` observer timed each collection and counted its unreachable and uncollectable objects by generation and by the innermost active stage. Preparation includes the existing causal TLE parser, its temporary records, and the surrounding scan, sky, noise, and phase-history preparation. The remaining stages include preparation serialization, discovery, fitting and recovery, and the selected figure packet with its full grid. [Observer and prototype](../../../tools/pipeline_eval/variants/algo08_gc_audit.py)

| Input and run | Preparation collections | Preparation GC CPU (ms) | Other solver GC CPU (ms) | Final full sweep CPU (ms) | Total GC CPU (ms) | Solve and final sweep CPU (s) |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016, control | 920 | 640.8 | 10.7 | 82.6 | 734.1 | 4.647 |
| DS30-0016, deferred | 1 | 43.2 | 101.3 | 104.5 | 249.1 | 4.113 |
| North far, control | 1,030 | 791.5 | 22.8 | 94.5 | 908.9 | 11.261 |
| North far, deferred | 1 | 56.0 | 111.9 | 80.8 | 248.7 | 10.628 |

In the controls, the catalogue parser alone accounted for 512 and 650 ms of CPU. It triggered five and six full-generation collections and reclaimed zero and 127 unreachable objects, respectively. The deferred scope suppresses automatic collections only while `prepare_native_scan` runs. On exit it collects the youngest generation once, including when preparation raises, and restores the original enabled state before serialization and inference. It retains the current thresholds. Other interpreters, a pre-disabled collector, GC debugging, and additional Python threads use the ordinary path. Each deferred solver subsequently ran one automatic full-generation collection. The measured saving includes that work and the closing full sweep in both arms.

## Memory and scientific equivalence

| Input | Peak RSS, control → deferred (MiB) | RSS before closing sweep (MiB) | RSS after closing sweep (MiB) | Unreachable objects collected, including closing sweep |
|---|---:|---:|---:|---:|
| DS30-0016 | 609.6 → 594.6 | 536.9 → 520.1 | 388.5 → 384.0 | 6,484 → 6,479 |
| North far | 940.7 → 941.6 | 532.0 → 531.2 | 514.0 → 430.0 | 11,308 → 11,287 |

Both runs reported zero uncollectable objects and empty `gc.garbage` throughout the recorded boundaries. After the closing collection the deferred workers had 16 additional tracked objects on each input, including any difference in the diagnostic bookkeeping. The component tests verify callback and wrapper cleanup, restoration of enabled state and thresholds, propagation of the original exception, and collection of a test cycle with a finalizer on scope exit. [Component tests](../../../tests/pipeline_eval/test_algo08_gc_audit.py)

| Input and calibration | Owners | Horizontal error (km) | Solver RF RMS (Hz) |
|---|---:|---:|---:|
| DS30-0016, `c = 0` | 109 | 1.644 | 109.375 |
| DS30-0016, fitted `c` | 109 | 1.662 | 109.479 |
| North far, `c = 0` | 228 | 52.455 | 37.951 |
| North far, fitted `c` | 228 | 52.491 | 37.533 |

The saved comparisons matched the numerical decisions, owner maps, endpoints, objective replay, position paths, trims, shortlists, and all 179 physical or 137 northern grid points after dropping timing fields. The northern endpoints still publish a false fix on the offered boundary. Reference locations were used for scoring only. These saved replays stop at the selected figure packet. [Physical reference](../location-audit/README.md) · [Simulated reference scores](../regional-release/blind-scores.csv)

## Reproduce

Each run used a fresh release interpreter, identical saved detections and offer, the same causal archive, coarse salvage statistics, and unchanged recovery-pair reuse. The control ran first at both sites. Read the input hashes and paths from the measurement receipt. [Trial runner](solver_gc_trial.py) · [Input pins and measurements](measurements/solver-gc.json)

```sh
work=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
for mode in control deferred; do
  options=()
  if [ "$mode" = deferred ]; then options=(--defer-preparation); fi
  flock "$work/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_gc_trial.py "${options[@]}" \
    "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
done
```
