# Full-arc pilot phase across the two public boundaries

Measured carrier predicts the saved 36 s pilot-code arcs to **0.079 and 0.091 samples RMS** on the held support. Positive causal geometry beats the reflected and clock-only controls, but its best face fit leaves **38.77 and 30.62 samples** of error. Both sites select the outer western probe and remain unresolved under the prespecified rule. [Held scores and offer-classification receipt](measurements/full-arc-code.json)

This experiment fits the wrapped pilot arrival phase over each continuous arc. The public short-increment test used adjacent visits, with independent fitted rates inside each track. The earlier physical full-arc experiment used offsets of 2 and 25 km. The current check uses the same frozen frequency-only owners as the public 200 m study and a constrained common ADC rate. The receiver has an unknown transmit phase for each emitter and fixed RF. Phase and clock rate are fitted on the first two-thirds of each arc only. [Prespecified protocol](full-arc-code-protocol.md) · [Earlier public increments](mirrored-arrival.md) · [Earlier physical circular fit](../../../tools/pipeline_eval/qualification/range_epoch_trial.py)

The released waveform generator draws the transmit frame phase **once per emitter**, then reuses it in every visit's emission tick and arrival computation. It computes a locally Doppler-adjusted pulse period for each window. The changing carrier phase is an independent per-window IQ rotation. The pilot code retains its scheduled transmit frame phase across visits. The two receiver outputs share the same emitter and simulated station, and the second lane has a fixed delay. Aligning their phases circularly and averaging folds that fixed lane delay into the fitted intercept. [Emitter and arrival construction](../../../tools/pipeline_eval/qualification/waveform_site_model.py#L107) · [Per-window IQ phase](../../../tools/pipeline_eval/qualification/waveform_site_model.py#L57) · [Absolute timing authority](absolute-timing-authority.md)

The fit uses the nominal 13,333⅓-sample frame modulo and splits arcs at gaps above 2.5 s. No integer frame sequence across excluded gaps is inferred. Each orbit contributes equally to held error. The geometric delay uses only capture-causal TLEs. The common rate is bounded at ±3.5 samples/s, corresponding to the simulator's ±0.35 ppm. The fit absorbs constant transmitter phase, but does not re-estimate receive UTC or orbital error. Measured-carrier closure integrates the two folded frequency measurements after alignment and unfolding within the same repeat period. It fits a separate affine offset and slope per arc to absorb frequency biases, so it serves as a geographic-free check. The free rate absorbs a constant fitted RF calibration term on a fixed RF. The geometric code fit does not take the fitted RF term as input.

## Held comparisons

| Public waveform | 36 s arcs / training / held epochs | Positive A / B RMS, samples | Reflected A / B RMS | Clock only RMS | Measured carrier, positive / reflected RMS | Held 200 m separation after fitting phase and clock |
|---|---:|---:|---:|---:|---:|---:|
| North | 10 / 121 / 69 | 38.772 / 38.819 | 3376.144 / 3376.399 | 1767.730 | 0.079 / 745.220 | 0.390 |
| South | 9 / 109 / 62 | 30.619 / 30.660 | 3850.469 / 3850.309 | 2174.262 | 0.091 / 713.619 | 0.471 |

The held geometric separation uses one causal template as a noiseless observation and measures the other after the same training phase and rate fit. It measures retained model shape. The observed carrier closure stays below this separation. Causal geometry has much larger out-of-sample residuals and includes orbit, time, height and fixed-association errors. The experiment cannot identify their individual contributions. The large per-arc slopes in positive carrier closure also include carrier aliases. Removing the nearest integer alias slope for display gives residual slopes of −0.39 to +1.33 samples/s in the north and −0.78 to +0.40 in the south. No alias branch chosen this way enters either model or its geographic score. [Sealed per-orbit scores, fitted slopes and leave-out results](measurements/full-arc-code-prediction.json.gz)

The full sample chose face A in both hemispheres. That corresponds to the containing offer's face in the north and the omitted offer's face in the south. The actual receiver lies between the faces, so this preference alone does not resolve either membership decision. The extended fit's best sampled point was 200 m west of A at both sites. The extrapolation reached the search extent and is unresolved under the fixed rule. Its signed clearances were −200 and −400 m in the northern containing and omitted squares, and +400 and +200 m in their southern counterparts.

All ten northern leave-one-satellite-out fits preferred A and selected the western extent. The southern A/B loss difference could change sign, from −3.268 to +7.231 samples². Six southern leave-out fits chose the western extent, two chose the eastern extent and one chose face A. Neither site produced a valid separation on any leave-out fit. The positive measured-carrier closure establishes long-arc timing coherence on these simulations. The causal orbit templates still fail the 100 m membership test. The earlier physical code sign control remains a separate constraint. [Physical code–carrier sign](arrival-observability.md)

## Reproduce

The first stage reads pinned public detections, the unlabeled coordinates, track support and causal archive. The second verifies the held-score digest before opening the released offer conditions. Neither stage reads a later orbit or an unreleased scoring key.

~~~bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
archive=/tmp/leo-regional-qZJKBw4W/public/tle
trial=$(mktemp -d "$bench/full-arc-code.XXXXXXXX")
module=reports.ALGO08.single-core-2x.full_arc_code_trial
python="$release/venv/bin/python"
north=("$bench"/covariance-north-inside/baseline/fast-scan-automatic-work/*/detections.json)
south=("$bench"/covariance-south-inside/baseline/fast-scan-automatic-work/*/detections.json)
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD:$release/src:$release"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" predict "${north[0]}" "${south[0]}" \
  "$archive" "$release/assets/tracks.json" "$trial/prediction.json" > "$trial/prediction.sha256"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" score "$trial/prediction.json" "$(cat "$trial/prediction.sha256")" \
  > "$trial/result.json"
~~~

The prediction lock expands to SHA-256 `945ead8ab2521a8e0b8fa62d0c83b0930fc0c39e4ce5bbec696795c297666102`. Both stages used one low-priority Gauss core. Ten component tests passed. [Runner](full_arc_code_trial.py) · [Component tests](../../../tests/pipeline_eval/test_full_arc_code_trial.py)
