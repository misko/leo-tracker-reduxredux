# Wideband IQ acquisition through the complete v5 finish

The downstream experiment substitutes two measured wideband IQ windows per recording and runs a fresh fit for each full composite. Its matched control also runs a fresh fit, using the complete frozen capture-era GLRT archive. Both use the same compact v5 finish, including cavity, residual addition and final reassociation, and the original supplied roof tile. [Protocol](PROTOCOL.md)

The original wideband binary was re-run only on segment zero visits 0 and 2 of each case. The pinned control replay reproduced all four selected archive probe rows on each recording. The replacement used the original interval-mode binary, two real receiver channels, the capture-bound RF grid and the original exact/control templates. It reproduced the numerical comparison in the earlier stage report and retained all native floating-point differences. DS26 changed 12 fractional CFO values and 19 values each for epoch offset, exact score, control score and margin. DS29 changed 16 CFO values and 19 values in each of the other four fields. Each composite replaced exactly four probe rows. DS26 preserved the remaining 13,526 probe rows and DS29 preserved 9,732. The original capture clocks and exclusions were preserved for both. [DS26 measured factors](DS26-0036-factors.json.gz) · [DS29 measured factors](DS29-0082-factors.json.gz)

## Paired results

The archive control and the wideband splice published both calibration arms on each case. All four comparisons met the predeclared one-metre and 0.0001 Hz tolerances. DS29's coordinates and RF RMS were identical. DS26 changed by 9.02 µm in `c0` and 28.70 µm in `fitted_c`. The corresponding conditional RF RMS changes were 1.99e-9 Hz and 6.72e-9 Hz. [Matched comparison](comparison.json) · [Wideband positions](positions.jsonl.gz) · [Fresh archive controls](control-positions.jsonl.gz) · [Prediction lock](position-lock.json)

| Recording | Arm | Archive latitude, longitude | Wideband latitude, longitude | Archive RMS (Hz) | Wideband RMS (Hz) |
|---|---|---|---|---:|---:|
| DS26-0036 | `c0` | 37.853054831257, −122.499403040978 | 37.853054831294, −122.499403040886 | 74.76091584692 | 74.76091584493 |
| DS26-0036 | `fitted_c` | 37.852100070370, −122.498960650428 | 37.852100070160, −122.498960650617 | 74.68229751330 | 74.68229752001 |
| DS29-0082 | `c0` | 37.845496107002, −122.481132744465 | 37.845496107002, −122.481132744465 | 97.00356915095 | 97.00356915095 |
| DS29-0082 | `fitted_c` | 37.849671446478, −122.479915817189 | 37.849671446478, −122.479915817189 | 96.68362191875 | 96.68362191875 |

Wideband coordinate errors were 1.278 km and 1.208 km for DS26 and 0.567 km and 0.517 km for DS29, in `c0` and `fitted_c` order. The paired archive errors agree to the displayed precision. The comparison JSON records the conditional frequency scores and geographic errors separately.

| Recording | Capture-era two-window replay wall / CPU (s) | Wideband two-window replay wall / CPU (s) | Archive fit wall / CPU (s) | Wideband fit wall / CPU (s) |
|---|---:|---:|---:|---:|
| DS26-0036 | 4.63 / 4.35 | 5.50 / 5.33 | 191.43 / 181.70 | 181.54 / 177.59 |
| DS29-0082 | 8.55 / 7.86 | 11.28 / 11.14 | 138.68 / 134.81 | 148.42 / 139.48 |

Detector time measures the original and wideband calls on the selected windows. Fit time measures each fresh full position worker with both arms, through the final decision. The archive fit consumed the frozen full detector output. Its two-window control replay independently verified the archive inputs. The two measured fit orders were reversed across the cases.

The earlier wall-time and candidate-inventory findings apply to the detector stage on its bounded windows. The downstream supplement includes both calibration arms and the complete solver. Whole-recording wideband acquisition remains outside the measured scope. [Earlier detector report](../../2026_11_19_receiver_streaming/native-geometry/README.md)

## Reproduce

Use the binary hash in the measured receipts. With the original build still available at its scratch path, run one command per recording. The `--binary` option accepts another copy of the same executable.

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 10 .venv/bin/python -B -m tools.pipeline_eval.qualification.wideband_position \
  --case DS26-0036 --out "$NEW_OUTPUT_DIRECTORY"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 11 .venv/bin/python -B -m tools.pipeline_eval.qualification.wideband_position \
  --case DS29-0082 --out "$NEW_OUTPUT_DIRECTORY"
.venv/bin/python -B -m tools.pipeline_eval.qualification.wideband_position \
  --pack --out "$NEW_OUTPUT_DIRECTORY"
```
