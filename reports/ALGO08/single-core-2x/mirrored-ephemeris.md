# Orbit and radio scales at the public mirrored boundaries

## Matched diagnostic

Earlier checks measured conditional horizontal curvature, a common 100 m height perturbation and held timing increments. This check keeps the same public 200 m face pairs and changes the orbit model in a noiseless comparison. It also measures simultaneous receiver differences from the saved waveforms as a lower-scope radio precision proxy. [Horizontal curvature](mirrored-uncertainty.md) · [Height perturbation](mirrored-height.md) · [Held pilot arrival](mirrored-arrival.md)

Use the earlier frequency-only owner map from the public containing offer and the same symmetric face-coordinate construction as the timing check. Retain the same matched NORADs, track times and measured RFs. Project the causal and later generator TLEs through the same retarded Doppler routine at nominal zero height. The later TLEs enter the offline comparison after fixing the causal owner map and projection design. Use no scorer key or original planted position. The later model is an oracle only for the two noiseless synthetic alternatives evaluated at the already supplied face coordinates.

Remove one common offset per track, one linear time term per receiver, and one causal along-orbit phase tangent per NORAD. Use this same fixed column space to remove nuisance terms from every geometric difference and comparable measured residual. Allowing a constant per fixed-RF track absorbs the fitted RF calibration term, so the diagnostic has the same values in both calibration gauges. Compare the projected 200 m signature with the causal-versus-later error. Score noiseless later-model observations at each face against both causal hypotheses. Also compare simultaneous saved receiver differences after the same compatible nuisance subtraction. Equal differences cancel common signal and orbit effects and do not measure common radio error. A fitted residual against either nominal orbit model can still contain position, timing or height mismatch.

## Orbit mismatch alone can invert either boundary test

The correct later-model face has zero mismatch in each noiseless control. Under the causal model, **both noiseless positions select A at both sites**. A receiver at B would therefore cross the decision to the wrong side with no radio noise present. The effect of changing the orbit catalogue has a component along the 200 m spatial signature that exceeds the half-separation at both sites. [Numerical and orbit authority receipts](measurements/mirrored-ephemeris.json)

| Public site | Saved points / simultaneous pairs / satellites | Projected 200 m signature, causal / later | Projected orbit-update RMS at midpoint | Orbit-update component along A → B | Paired receiver differential RMS |
|---|---:|---:|---:|---:|---:|
| North | 450 / 224 / 12 | 0.818 / 0.755 Hz | 6.740 Hz | −1,118 m | 5.132 Hz |
| South | 423 / 208 / 13 | 1.226 / 1.224 Hz | 1.731 Hz | −200 m | 6.627 Hz |

| Public site | Noiseless source | Score against causal A / B, Hz RMS | Preferred face |
|---|---|---:|---|
| North | Later A | 6.696 / 7.281 | A |
| North | Later B | 6.251 / 6.785 | A |
| South | Later A | 1.727 / 2.739 | A |
| South | Later B | 1.223 / 1.736 | A |

The signed distance is the least-squares component of the later-minus-causal Doppler difference along the later model's projected A-to-B change, scaled by 200 m. It is a one-axis diagnostic at fixed points. The table uses the same selected tracks and nuisance design for both models. Every assigned NORAD had an eligible causal and later element set. The later archive is the generator's source, and its collection time follows both captures. The oracle calculates only these fixed, noiseless alternatives and does not recover the original planted receiver or rerun owner selection.

The stereo differential is the within-epoch difference for the same satellite and channel divided by \(\sqrt{2}\), with the corresponding nuisance columns removed. Its RMS exceeds the per-point 200 m signal in both recordings. It gives no effective independent sample count and cancels common errors. Against the saved measured tracks, changing the model at the midpoint reduces projected residual RMS from 9.045 to 5.238 Hz in the north and from 9.271 to 9.172 Hz in the south. This leaves both radio precision and remaining model errors relevant. Their shares of the full localization error are unmeasured. The two deterministic counterfactuals establish that improved radio precision alone would leave one error at each site under this causal predictor. [Retarded simulator projection](../../../tools/pipeline_eval/qualification/cold_scenes.py) · [Published generator](../regional-release/blind_panel.py)

Run the same diagnostic separately for each public saved capture with its digest-verified public archive and installed track configuration. The runner reads the generator's already archived later element object and never opens initial waveform samples or a scoring key. Six tests passed across common nuisance projection, noiseless inversion, simultaneous receiver matching and the earlier arrival controls. [Runner](mirrored_ephemeris_trial.py) · [Tests](../../../tests/pipeline_eval/test_mirrored_ephemeris_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/mirrored_ephemeris_trial.py \
  "$site" "$saved_detections" "$public_archive" "$release/assets/tracks.json"
```
