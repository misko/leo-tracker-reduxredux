# How much could receiver height move the mirrored-region estimates?

Assigning both public simulated receivers a height of 100 m above the ellipsoid moved the fixed-owner positions about 78–86 m east. That brings each estimate closer to the receiver along the relevant face normal. All four still miss the ±100 m across-face accuracy needed to classify both shifted offers at their site. The public generator draws heights from 25 to 110 m. The exact heights were neither read nor estimated. [Mirrored-offer errors](mirrored-regions.md) · [Public generator](../../../tools/pipeline_eval/qualification/waveform_site_model.py)

| Public site | Calibration | East shift | North shift | Signed inward bias before | Projected signed inward bias at 100 m |
|---|---|---:|---:|---:|---:|
| North | Fixed zero | +85.6 m | −146.1 m | −741.0 m | −655.4 m |
| North | Fitted | +84.3 m | −144.3 m | −682.5 m | −598.2 m |
| South | Fixed zero | +79.1 m | −75.2 m | +344.8 m | +265.7 m |
| South | Fitted | +78.3 m | −83.4 m | +285.9 m | +207.6 m |

Positive inward bias points east in the north and west in the south. At the sampled 25 m and 110 m heights, the east shifts were approximately 20–21 m and 86–94 m, respectively. The 110 m perturbation still leaves the northern biases at −647 m and −590 m and the southern biases at +258 m and +200 m, in fixed-zero and fitted order. This is a local sensitivity check at three common heights within the public generator range. It supports height as a partial contributor under this fixed likelihood. It provides no bound on how a different orbital association or a full height-aware fit would behave.

## Measurement boundary

I replayed the original containing offer for each saved waveform at zero height. Each replay reproduced both published positions, frequency RMS values and owner digests. The north had 302 published observations with 285 curved points and two predictive tracks. The south had 266 curved observations and no predictive tracks. Each arm retained its own original calibration treatment and the same observations, satellite owners, aliases, phase expansion epochs, orbit priors, screening and search square across heights. The diagnostic changes ellipsoid height in the selected objective's nominal Doppler, elevation, phase derivative and physical orbital modes. It re-evaluates the radio, orbit and noise nuisance terms at each trial coordinate. [Northern publication](measurements/north-baseline-first.json) · [Southern publication](measurements/south-shared.json) · [Diagnostic runner](mirrored_height_trial.py)

For each arm I computed the horizontal gradient of the profiled objective at the archived point at zero and assigned height, and applied the negative gradient difference through the inverse zero-height Hessian. The resulting displacement is a local projection with no new horizontal optimization. The original and projected points are interior to the containing square. Horizontal differentiation steps of 25 m and 50 m agreed to within 0.002 m. Catalogue screening, association and phase refresh stayed frozen at their released zero-height settings. The calculation lacks any additional atmospheric or site-specific term and does not identify the planted height or isolate the remaining source of error.

Curved-point RMS at the original zero-height point and at the projected 100 m point was 5.380 → 5.393 Hz in the north and 6.503 → 6.500 Hz in the south with fixed-zero calibration. With fitted calibration it was 5.173 → 5.186 Hz and 6.392 → 6.379 Hz. These are frequency diagnostics on the fitted observations. The measured across-face comparison above uses the published scorer outputs after projection.

The runner needs only a digest-matched saved detection file, the public capture-era TLE archive, and the installed release assets. It verifies the archived regional receipt and never reads the scoring key. The two runs took 6.69 and 6.16 CPU seconds, respectively, including the zero-height owner replay. [Component tests](../../../tests/pipeline_eval/test_mirrored_height_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/mirrored_height_trial.py \
  "$site" "$saved_detections" "$public_archive" "$release/assets"
```
