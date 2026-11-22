# All-track regional evidence with location-specific satellite assignments

On eight public offers for two simulated sites, the frozen sign would have withheld all four wrong-region fixes and **one valid fix**. The incorrect withholding occurs with the southern receiver 100 m inside its offer. The pooled score is slightly higher outside, and the two receiver groups disagree. The sign was frozen after the northern near-edge and two far-omission cases and before checking the other five offers.

## Matched observations and causal alternatives

The trial starts from the exact saved detections and builds the same native Graph tracks. Every complete track enters the diagnostic, including tracks the production fit left unassociated. Each point uses the same original observation denominator. Observations outside all Graph tracks contribute the fixed outlier baseline. The number of observations or possible owners never renormalizes a probe score. The observations are also partitioned by physical receiver and scored independently. The partitions share the capture and orbital hypotheses.

Each point can assign a different causal catalogue satellite to each track. The full original causal catalogue supplies a common prior denominator. Every visible alternative is marginalized with equal catalogue weight and the same prior odds against a uniform native-period contrast null. A geometric upper bound on elevation at the first time of each track screens the usable propagated orbits for visibility at any probe. The retained orbits are projected from capture-time SGP4 states, and track likelihoods require visibility throughout the track. A phase-tangent Gaussian integrates the same nominal one-second phase prior and uses the native white noise scale. The within-track differences remove any constant additive term on that track's fixed RF, including `c`. The diagnostic consequently gives identical fixed-zero and fitted-`c` scores by construction. It has no estimate of either calibration arm's position. [Model](../../../tools/pipeline_eval/variants/experimental/regional_reassignment.py) · [Saved-detection runner](regional_reassignment_trial.py)

The 48 inside and 48 exterior positions use the same four face normals and the same three lateral offsets, `−1/5`, `0` and `1/5` of the offered width. Inside radii are `1/8`, `1/4`, `3/8` and `1/2 − 1/256` widths. Exterior radii are `1/2 + 1/256`, `5/8`, `3/2` and `5/2` widths. The frozen diagnostic subtracts the highest inside pooled score from the highest exterior pooled score. A strictly positive gain would withhold a published fix. Zero and negative gains retain it. The receiver-specific maxima are descriptive. This is a retrospective comparison with the existing simulation publications and does not alter any decision.

The preceding exterior-profile trial fixed the publication's assignments and could therefore retain an implausible owner at a better location. Earlier regional methods include disjoint-orbit fits, a score from eight sampled points on selected tracks with shuffled-time controls, and forecasts on reciprocal held blocks. The present comparison uses each complete Graph track and a common per-observation denominator while resumming orbital alternatives at every probe. [Fixed-owner experiment](exterior-profile.md) · [Orbit split](../../../tools/pipeline_eval/variants/region_halo.py) · [Track-time null](../../../tools/pipeline_eval/variants/region_null.py) · [Held extrapolation](../../../tools/pipeline_eval/variants/outside_predictive.py)

## Public simulated development offers

| Simulated offer | Original / Graph observations | Pooled gain | RX1 gain | RX2 gain | Frozen sign outcome |
|---|---:|---:|---:|---:|---|
| North, centered | 456 / 450 | −0.062761 | −0.065298 | −0.060224 | Retains valid fix |
| North, 100 m inside | 456 / 450 | −0.000545 | −0.000638 | −0.000451 | Retains valid fix |
| North, 1.5 km outside | 456 / 450 | +0.000271 | +0.000171 | +0.000372 | Correctly withholds |
| North, far omission | 456 / 450 | +1.276956 | +1.421316 | +1.132595 | Correctly withholds |
| South, centered | 456 / 423 | −0.067846 | −0.064240 | −0.071451 | Retains valid fix |
| South, 100 m inside | 456 / 423 | +0.000047 | −0.000067 | +0.000160 | Falsely withholds |
| South, 1.5 km outside | 456 / 423 | +0.000931 | +0.001047 | +0.000815 | Correctly withholds |
| South, far omission | 456 / 423 | +0.812992 | +0.808568 | +0.817415 | Correctly withholds |

Each receiver contributes 228 original observations at every probe. The eight earlier solves all published both calibration arms. The simulated decision totals per calibration arm are three retained valid fixes, one false withholding, four correct withholds and zero retained false fixes. The withheld valid southern positions were 817 m from the receiver with fixed-zero calibration and 1,101 m with fitted calibration. [Pointwise scores, owners and decision receipts](measurements/regional-reassignment.json.gz) · [Prior publications](../regional-release/README.md) · [Near-edge construction](edge-trial.md)

The best pooled inside and exterior probes switch the highest supported satellite on 18 tracks in each far-omission case. Two more southern tracks favor the satellite mixture over the null only at the best exterior probe. The northern near-edge comparison changes no reported track owner. The best exterior probes on the two far-omission controls lie 2.50 km from the receivers, compared with 52.79–52.80 km for the best inside probes. These are locations on the diagnostic grid. Preprocessing and scoring take 2.92–3.05 CPU seconds per offer on one low-priority core, including roughly 1.3–1.5 seconds for orbit geometry and probes. The inputs consist of saved detections.

The southern near-edge false withholding appears when the best inside and exterior probes sit just 97.7 m on either side of the same face. The two receivers share the same physical event and sky, so corroborating signs provide a consistency check. The source data consist of two public simulated captures with several offers each. The mixture score assumes independent track contrasts under a simplified noise model, and its magnitude lacks calibrated geographic uncertainty. The sign is insufficient for a withholding policy.

## Reproduction

The trial uses the release's track configuration and the causal archive from the public simulations. The SHA-256 binds the saved detection bytes. Six component tests cover the probe symmetry and counts, dense contrast-covariance equivalence, additive calibration cancellation, the common outlier and catalogue denominator, the conservative horizon screen, observation accounting and the frozen sign.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/regional_reassignment_trial.py \
  "$saved_detections" "$tle_archive_root" "$release/assets/tracks.json" "$offer" "$detector_digest"
```
