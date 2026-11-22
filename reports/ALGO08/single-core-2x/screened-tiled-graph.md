# Native Graph path in the guarded solver

Adding the reviewed native Graph ABI reduced the saved DS30-0374 solve from **23.150 to 21.955 CPU seconds** and **23.665 to 22.383 elapsed seconds**. The two fixes, carrier residuals, owners, and all numerical evidence fingerprints matched the guarded control. Even if the full observed reductions carried through to raw publication, the measured physical pair would still be **0.911 CPU seconds and 2.521 elapsed seconds above half-time**. [Saved measurements](measurements/screened-tiled-graph-saved.json) · [Physical publication](screened-tiled-publication.md)

The isolated `e279026b…` bundle adds the exact Python adapter, C source and checked ABI binary from `2a55dcaa…`. Every existing source pin and non-Graph option agrees with screened-tiled `c803a300…`, including the receiver, orbit preparation, initial search, guarded salvage, paired calibration, regional veto, grid and renderer. The normal experimental launcher binds the native implementation. The existing saved-solver worker substitutes verified detections and measures through the complete selected evidence packet. DS30-0374 uses the same saved worker as its archived solver clock. The saved detection document and causal archive also match the subsequent full physical pair. The India control used a different trace wrapper, and its guarded salvage hooks were idle. [Frozen bundle and source pins](measurements/screened-tiled-graph-freeze.json) · [Reference Graph ABI](graph-native-path.md) · [India containing reference](screened-stock-salvage.md)

| Saved input | Guarded → native CPU | Guarded → native elapsed | Native paths | Native packing and search CPU |
|---|---:|---:|---:|---:|
| DS30-0374 | 23.150 → 21.955 s | 23.665 → 22.383 s | 131 | 11.413 ms |
| India containing simulation | 5.652 → 5.566 s | 5.777 → 5.665 s | 40 | 2.411 ms |

On both inputs the terminal status and nullable reason, orbit policy, fixed-zero and fitted endpoints, Doppler RMS, owner hashes, observation counts, numerical grid, optimizer path and objective replay matched exactly. DS30-0374 retained 2,905 owners per arm and 101.535913 / 101.519803 Hz RMS. India retained 517 owners per arm and 15.536351 / 15.305842 Hz RMS, with the same 1.017 / 0.751 km horizontal errors. Numerical evidence digests exclude transport binding and elapsed time fields. [Per-input receipt](measurements/screened-tiled-graph-saved.json)

The timing comparison uses one new solve per input and archived controls, so it cannot isolate repeat variability from the complete-solve savings. The earlier paired profile measured approximately half a CPU second of direct Graph path savings on dense DS30-0008 and 8 ms on the northern simulation. This trial measured no raw publication, receiver acquisition or PNG timings. Applying the entire observed DS30-0374 solver gain would reduce the full publication estimate to 65.266 CPU seconds and 70.119 elapsed seconds. The measured half-time targets were 64.355 and 67.598 seconds. [Prior paired Graph measurements](graph-native-path.md#cpu-on-gauss) · [Measured physical pair](measurements/screened-tiled-ds30-stage.json)

## Reproduction

Use the project Python environment and fresh output directories. The runner verifies both parent freezes and uses the sealed DS30-0374 candidate detection document and the released India containing offer. It runs one saved solve for each.

```sh
bench=/tmp/leo-algo08v2-2x-bench
pair=/tmp/ds30-v2-stage-covariance-375895/DS30-0374/pair.json
python_bin=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$python_bin" -BPs -m reports.ALGO08.single-core-2x.screened_tiled_graph_trial \
  "$bench" "$pair" "$bench/integration-screened-tiled-graph-next" \
  "$bench/screened-tiled-graph-saved-next"
```
