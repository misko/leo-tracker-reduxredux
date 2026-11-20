# One physical receiver with ordinary native GLRT

The native C detector takes one physical lane at a time through its existing single-input ABI. We kept the 10 MHz sample clock, all eight channels and every scheduled visit on DS26-0036 and DS29-0082. Each valid visit still supplies two probe identities to v5, with the candidates in the unmeasured RX1 slot empty. The fresh IQ experiment reads the original dual-interleaved archive and copies its RX0 lane into a contiguous 800,000-byte buffer per 20 ms. The dual context processes 1,600,000 bytes. No hardware was changed and the archive bytes read in both cases are the same. [Protocol](PROTOCOL.md)

## Authenticated IQ and detector cost

The paired benchmark ran the same library and templates on one pinned host E-core. It decoded windows 0–7 of segments 0 and 8, and recorded five invalid visits on DS29. On the 27 valid visits, all 215 distinct ranked RX0 candidates agreed exactly between single and dual C calls. The receiver-row fields agreed on all 81 repeated comparisons. Complete fractional factors also matched the prior native replay on the sampled IQ. Wall throughput starts with decoded IQ and includes the single-lane copy, detector and binding handoff. [Complete waveform receipts](waveform.json.gz)

| Recording | Valid / scheduled | Ranked RX0 candidates | Median detector CPU, dual → RX0 | Median paired CPU speedup | Detector throughput, dual → RX0 |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 16/16 | 127 | 25.82 → 14.57 ms | 1.82× | 31.7 → 62.6 windows/s |
| DS29-0082 | 11/16 | 88 | 25.84 → 14.12 ms | 1.80× | 35.3 → 68.8 windows/s |

In separate single-context processes, current RSS grew by approximately 37.3 MiB from immediately before context construction to the end of detection with dual input, and by 31.9 MiB with RX0 input, a reduction of 5.4 MiB. Peak process RSS was 137.8 → 137.6 MiB on DS26, where parsing archived factors set the high-water mark, and 130.1 → 124.6 MiB on DS29. Context initialization was 13.6–17.7 ms of CPU across the standalone processes. The main reduction was per-window detector work.

## Position from stored factors

The capture-era RX0 projection worsened both positions compared with the frozen two-receiver no-repair control. Projecting the archived ordinary native factors to RX0 worsened DS26 by almost 6 km and improved DS29 by about 0.5 km against the matching ordinary dual native control. The latter still had more than twice the error of the capture-era RX0 projection. Both recordings came from the same roof installation. [Capture-era RX0 predictions](archive-positions.jsonl.gz) · [Ordinary native RX0 factor predictions](ordinary-factor-positions.jsonl.gz) · [Dual control position errors](../../2026_11_18_pipeline_eval/evidence/full-iq/scorer-errors.csv)

| Recording | Factors | Error at `c = 0` | Error at fitted `c` | Native observations / tracks |
|---|---|---:|---:|---:|
| DS26-0036 | Capture-era dual | 1.278 km | 1.208 km | |
| DS26-0036 | Capture-era RX0 | 1.527 km | 1.535 km | 2,104 / 58 |
| DS26-0036 | Ordinary native dual | 0.231 km | 0.186 km | 3,610 / 104 |
| DS26-0036 | Ordinary native RX0 | 6.066 km | 6.008 km | 2,358 / 66 |
| DS29-0082 | Capture-era dual | 0.567 km | 0.517 km | |
| DS29-0082 | Capture-era RX0 | 0.860 km | 1.147 km | 1,147 / 38 |
| DS29-0082 | Ordinary native dual | 2.802 km | 2.662 km | 2,044 / 70 |
| DS29-0082 | Ordinary native RX0 | 2.302 km | 2.157 km | 1,313 / 45 |

The paired calibration fits used the same factor document and v5 search settings. For capture-era RX0, fitting `c` changed conditional RF RMS from 91.177 to 91.184 Hz on DS26 and from 120.073 to 120.066 Hz on DS29. DS29's position error rose by 0.287 km despite the slight RMS decrease. For ordinary native RX0 the changes were 104.169 → 104.040 Hz on DS26 and 99.914 → 99.932 Hz on DS29, accompanying position improvements of 0.058 and 0.145 km. The fitted frequency score increased in all four RX0 factor experiments. [Capture-era RX0 frequency fits](archive-positions.jsonl.gz) · [Ordinary native RX0 frequency fits](ordinary-factor-positions.jsonl.gz)

## Complete single-input IQ replay

Both full replays recovered the ordinary native dual detector's RX0 fractional candidates exactly on each valid visit. The recorded clocks, capture exclusions, visit order and both original probe identities matched the dual archive. The fresh positions reproduced the corresponding archived native RX0 positions exactly in both calibration arms. [Full single-input receipts](full-positions.jsonl.gz) · [Scored positions and conditional RF fits](scores.json)

| Recording | Valid / scheduled visits | Complete RX0 candidates | Raw and assembly | v5 | Total wall / recorded span | Fresh error `c = 0` / fitted `c` |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 6,765 / 6,769 | 31,970 | 161.12 s | 195.81 s | 356.95 / 299.97 s | 6.066 / 6.008 km |
| DS29-0082 | 4,868 / 6,772 | 22,699 | 104.07 s | 120.49 s | 224.58 / 300.00 s | 2.302 / 2.157 km |

Total detector CPU fell from the earlier ordinary dual runs' 171.48 to 108.06 seconds on DS26 and 134.14 to 78.29 seconds on DS29. End-to-end wall times fell from 371.30 to 356.95 seconds and from 228.39 to 224.58 seconds. The full runs took place separately on the shared host. The paired detector timings above control for run order and host conditions more directly. DS26 exceeded its recorded duration and the fitted error increased from 0.186 to 6.008 km against dual ordinary native. DS29 completed within its recorded duration and the fitted error fell from 2.662 to 2.157 km against that same control. The frozen capture-era dual error was lower on DS29 at 0.517 km. [Earlier dual runs](../../2026_11_18_pipeline_eval/evidence/full-iq)

## Reproduction

Use the archive host, a local output directory and a pinned CPU. `CASE` is either DS26-0036 or DS29-0082. Run `waveform` in `paired`, `dual` and `rx0` modes in separate processes for the combined timing and standalone memory comparisons.

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
  .venv/bin/python -m tools.pipeline_eval.qualification.single_chain_trial \
  --case "$CASE" --out "$OUT/waveform-$MODE.json" waveform --mode "$MODE"

env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
  .venv/bin/python -m tools.pipeline_eval.qualification.single_chain_trial \
  --case "$CASE" --out "$OUT/factors" factors capture-era-rx0 ordinary-native-rx0

.venv/bin/python -m tools.pipeline_eval.qualification.recording_to_v5 \
  --replay "$OUT/raw" --case "$CASE" --cpus "$CPU0" "$CPU1" --detector single-rx0

.venv/bin/python -m tools.pipeline_eval.qualification.single_chain_trial \
  --case "$CASE" --out "$OUT/fresh-prediction.json" collect-raw \
  "$OUT/raw" "$OUT/factors/ordinary-native-rx0/prediction.json"
```
