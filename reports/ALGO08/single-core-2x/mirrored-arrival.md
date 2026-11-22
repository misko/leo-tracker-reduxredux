# Held pilot arrival increments across the mirrored boundary

## Predeclared check

Use the same saved northern and southern simulated detections, original Graph membership and capture-time TLE archive as the earlier arrival audit. The two location hypotheses are the corresponding faces of the two supplied squares, 200 m apart. Label them A and B in coordinate order before scoring. Keep the frequency-only owner map from the previous centered regional score, selected by its best inside frequency score, identical for both hypotheses. This is a conditional timing test on archived frequency associations, with the earlier supplied area as an optimistic source of ownership. No reference coordinates, timing sign labels or per-site sign fit enter the scores. [Existing sensitivity check](arrival-observability.md) · [Pilot epoch join](arrival_observability_trial.py)

Use exact native fractional epochs and consecutive same-track increments up to the existing 2.5 s limit. Keep only intervals whose two endpoints are in the same 8 s block on the recording clock. Within each NORAD group, randomly permute its occupied blocks with seed `750200` and the numeric NORAD, then alternate their fold assignments. Each block stays together across all of that satellite's tracks and both receivers. Fit a separate constant rate per track and hypothesis from the opposite fold with the existing wrapped robust fit. Use a fold only with at least four rate-training and two held intervals on that track. Score both fold directions where available. Preserve all held observations across hypotheses and report block and satellite counts. Adjacent intervals and the two receivers do not count as independent replications.

The primary predictor is the physically positive causal TLE range increment in samples. Controls are a rate with no range and the same geometry with the sign reversed. Also report the original integrated-carrier positive and reflected closure on the same held support to identify the effect of replacing a measured carrier with the nominal orbit. Keep observer height at zero and nominal orbit phase fixed. The rates absorb any constant `c` per fixed-RF track, giving the same timing comparison in the fixed-zero and fitted calibration gauges.

For each hypothesis, average held squared residuals within each NORAD and then average the NORAD means with equal weight. Report the A versus B loss difference, votes per NORAD and its leave-one-NORAD-out range. Treat correct geography as supported on this panel only if the physically positive predictor selects the containing hypothesis at both sites, beats rate-only and both reflected hypotheses at each site, and retains its geographic preference after dropping any one held satellite. Withhold a geographic decision if these conditions fail. Join the known public offer labels after scoring. Use the previously measured physical DS30-0016 code–carrier sign test as the transfer control, with no new physical replay or access to any reserved input.

## Held timing detects range motion but does not resolve the mirrored offers

The physically positive nominal orbit model beats the no-range and sign-reversed controls on both public waveforms. Its smaller of the two held errors belongs to the omitted face at both sites. Dropping one satellite can flip either preference. The rule frozen in `b62bff5ca` withholds a geographic decision at both sites. These results apply to both calibration gauges on the fixed tracks. [Fold assignments and held scores](measurements/mirrored-arrival.json)

| Public site | Tracks / held intervals / blocks / satellites | A, B truth | A RMS | B RMS | Loss B − A, samples² | A / B satellites | Leave-one-satellite-out loss B − A |
|---|---:|---|---:|---:|---:|---:|---:|
| North | 19 / 237 / 46 / 10 | Containing, omitted | 0.428356 | 0.426965 | −0.001190 | 4 / 6 | −0.002235 to +0.000784 |
| South | 19 / 210 / 41 / 10 | Omitted, containing | 0.154421 | 0.154434 | +0.0000041 | 5 / 5 | −0.000382 to +0.000298 |

The RMS is the square root of the satellite-weighted mean squared held residual, in samples at 10 MS/s. For each waveform the corresponding faces were picked in the direction of its archived frequency-only anchor, then ordered by their geographic coordinates. The two fold directions hold an interval at most once. Cross-boundary intervals are discarded, and the same NORAD and clock-block fold applies across both receivers. The archived Graph and orbit owners were derived from the whole frequency record. Only the timing rate fit was cross-validated here.

| Public site | Rate only RMS | Reversed nominal range A / B | Measured carrier, positive / reversed |
|---|---:|---:|---:|
| North | 53.144 | 105.500 / 105.474 | 0.093 / 105.909 |
| South | 42.387 | 84.886 / 84.887 | 0.102 / 84.829 |

The much tighter code–carrier closure on the same held intervals shows the distinction between tracking range motion and forecasting it with nominal, uncorrected orbits. The timing observations favor the large common range signal. The 200 m preference remains smaller than the variation across assigned satellites. The two simulations give no calibrated evidence that this nominal-orbit method can add geographic discrimination at a face. An estimator that also accounts for orbit phase and clock changes remains untested here.

The physical DS30-0016 closure had RMS **52.257 samples with positive sign, 25.953 with rate alone, and 1.748 with reversed sign** under the earlier chronological test. The reflected result appeared on both receiver paths. It leaves the physical transfer of the timing observable uncalibrated. This audit preserves the physical sign for both simulated sites, without choosing a receiver-specific polarity or re-running the DS30 recording. [Physical timing control](arrival-observability.md)

Run the digest-pinned trial separately on the northern and southern public saved detections. It uses the public TLE archive and the installed tracking configuration. [Runner](mirrored_arrival_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_arrival_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/mirrored_arrival_trial.py \
  "$site" "$saved_detections" "$public_archive" "$release/assets/tracks.json"
```
