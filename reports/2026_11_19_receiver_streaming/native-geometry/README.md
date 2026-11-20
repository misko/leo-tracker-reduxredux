# Native full-reference acquisition on 20 ms survey IQ

The wideband interval C wrapper reproduced all 64 candidates within the predeclared rank-by-rank tolerances on four recorded 20 ms windows. It took 2.82–5.52 CPU seconds per window, exceeding the two-core, 15-minute detector budget by roughly 11× on DS26-0036 and 15× on DS29-0082. Positioning was unmeasured.

| Case and visit | Historical fractionally complete candidates | Historical positives | Wideband CPU s | Capture producer CPU s | Ordinary native CPU s |
|---|---:|---:|---:|---:|---:|
| DS26-0036 / 0 | 11 | 5 | 2.824 | 2.258 | 0.035 |
| DS26-0036 / 2 | 8 | 4 | 2.985 | 2.215 | 0.028 |
| DS29-0082 / 0 | 10 | 1 | 5.433 | 4.237 | 0.035 |
| DS29-0082 / 2 | 9 | 5 | 5.525 | 4.156 | 0.029 |

The hash-verified capture producer reproduced the historical v5 probe values exactly for 8 of 8 receiver rows. The wideband comparison includes all 64 retained candidates, including 26 without a complete fractional answer. Integer epoch, fractional status and both margin gates agreed by rank. Maximum absolute differences were 2.86e-9 Hz in CFO, 2.54e-13 samples in fractional epoch offset and 7.08e-14 in score or margin. All 15 passing fractional candidates matched one-to-one. The ordinary native comparison matched 13 of the 15, missed two and added 20 other passing candidates. [DS26-0036](DS26-0036.json) · [DS29-0082](DS29-0082.json)

The pinned producers evaluate a folded 80 kHz coarse CFO grid, retain eight basins with 5-sample and 10 kHz separation, refine CFO and perform conditioned integer and fractional GLRT. The geometry observed at the deployed wrapper was 200,000 dual-RX sample times, a 0 Hz receiver center and residual bounds of ±800 kHz, yielding 21 coarse frequencies for each visit. The templates came from the pinned producer's exact and rolled-control frame generators for the recorded pilot edge. DS29 visits 0 and 2 triggered the same 22-anchor retry on RX1 in both the deployed and wideband detectors.

Both unmodified C research libraries returned `LEO_NATIVE_GLRT_INVALID` for the true 20 ms layout. The maintained 12-slot version also returned `LEO_NATIVE_GLRT_INVALID` for the recorded 1.6 MHz span. The older 22-slot research library accepted the span. Its adapted build added a 20 ms dwell with a 20 ms stride in the layout predicate and read the exact 1,600,000-byte CI16 input on every call. The corrected profile bridge admits 7.5 MS/s, so it was bypassed in favor of the wideband replay contract. [Layout patch](short-dwell.patch) · [Original wideband qualification](../../2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research/README.md)

The archives contain 6,765 and 4,868 valid visits respectively. The detector CPU budgets were 0.266 and 0.370 seconds per visit. With two fully utilized cores, the observed mean detector times alone would take approximately 2.73 and 3.70 hours. Those are extrapolations from two visits per recording and exclude archive I/O and positioning. [Stage-only prediction records](positions.jsonl.gz)

A subsequent matched run used the FP64 scalar wideband wrapper on the same four inputs. Its complete native candidate payloads equaled the interval wrapper’s on all eight receiver rows. Scalar calls took 3.05–3.25 CPU seconds on DS26-0036 and 5.79–5.89 on DS29-0082. [Scalar timing and equality checks](scalar-control.json)

## Reproduction

Build the maintained research library and the short-dwell wideband wrapper in a local scratch directory. `FFTW_PREFIX` supplies `include/fftw3.h` and `lib/libfftw3f.a` as required by the native build.

```sh
scratch=$(mktemp -d)
report=reports/2026_11_19_receiver_streaming/native-geometry
wideband=reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1/wideband-research
cp -a "$wideband/source/native/adaptive/detector" "$scratch/detector"
patch --fuzz=0 -d "$scratch/detector" -p1 < "$report/short-dwell.patch"
python3 native/adaptive/detector/build.py --enable-server-reference \
  --output-dir "$scratch/maintained" --work-dir "$scratch/work-maintained" \
  --compiler /usr/bin/gcc --archiver /usr/bin/gcc-ar --fftw-prefix "$FFTW_PREFIX" --target host
python3 "$scratch/detector/build.py" --enable-server-reference \
  --output-dir "$scratch/wideband-short" --work-dir "$scratch/work-wideband" \
  --compiler /usr/bin/gcc --archiver /usr/bin/gcc-ar --fftw-prefix "$FFTW_PREFIX" --target host
```

Run each case with its `producer.root` as `PYTHONPATH` and a capture-compatible Python environment. The recorded run used `/opt/leo-fast-graph/7cafccaced18e6b0fa9266bd18339d61f0f9c1f4/venv/bin/python` with CPUs 10 and 11. The CLI verifies the installed producer’s run identity before replay. Substitute the desired CPU, case ID, producer path and output path.

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$CAPTURE_PRODUCER" \
  taskset -c "$CPU" "$CAPTURE_PYTHON" -B -m tools.pipeline_eval.qualification.native_geometry_trial \
  --case "$CASE" --maintained "$scratch/maintained/libleo-adaptive-detector.so" \
  --wideband-replay "$scratch/wideband-short/leo-native-adaptive-replay" --out "$OUTPUT"
```

Add `--scalar-control` for the FP64 wrapper comparison. With both per-case JSON reports in one directory, `native_geometry_trial.write_predictions(directory)` writes the two stage-only prediction rows.
