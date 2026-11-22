# Causal phase and carrier proposals

The tracking experiment tests whether recent waveform measurements can replace a full timing scout on a repeatedly visited RF lane. Each replay starts with empty state and processes every eligible saved visit on both antennas in capture order. The detector uses no station coordinates, orbit data, antenna-to-antenna hints or site-trained frequency cuts. This is a chronological Gauss development test.

Earlier timing hints recovered several known waveforms but worsened both fresh position comparisons. One short folded-frequency scout also lost four other gated pilots while saving just 2.60% of its coarse tap operations. Whole-visit duty cycling in this study admitted fewer than one-third of the original post-continuation factors and caused a simulated position withhold. Measurements on every visit and retention of weak secondary evidence are required for the new route. [Earlier receiver evidence](../single-core-directions.md) · [Duty-cycle comparison](cadence.md)

## Chronological receiver result

DS30-0016 yielded 116 eligible visits and 232 independent lane calls. The prototype saved **16.8–17.2%** of whole receiver CPU against the frozen fast exact receiver. It lost **30 of 152** verified factors and **9 of 53** post-continuation selections. This ruled out the tested route for the paired publication candidate. [Per-repeat timings and every lost factor](receiver-tracking-results.json)

| Matched outcome | Exact receiver | Tracking prototype |
| --- | ---: | ---: |
| Receiver CPU, first repeat (s) | 0.8295 | 0.6904 |
| Receiver CPU, reverse repeat (s) | 0.8371 | 0.6932 |
| Verified factors | 152 | 122 |
| Distinct returned second-scan factors | 41 | 28 matched |
| Lower-margin factors on two-factor lanes | 41 | 28 matched |
| Post-continuation selections | 53 | 44 matched |

Matching is one-to-one within two wrapped samples and 250 Hz of signed CFO. The 122 matching factors differed by at most 0.00164 samples and 16.93 Hz. Factor tuples agreed exactly on 194 of 232 lanes. Every lost selection withheld where the exact receiver selected a factor. Among the 30 lost factors, 29 had no compatible causal timing and signed-CFO proposal even when the same rule was applied to the exact receiver's past outputs. That group includes cold and interrupted evidence as well as potential new births. The comparison found zero near-epoch replacements at approximately 750 Hz or 227.27 kHz spacing. Each candidate factor matched an exact receiver factor.

The prototype attempted narrow prediction on 36 first scans. The first scan used the full scout on 111 lanes, including 23 fallback reacquisitions. The two shortened stages ran 131 first scans and 44 residual scans. A matched two-scan replacement needs a discovery test with higher recall on unforecasted signals while preserving the original residual verifier. The observed throughput improvement is small relative to the additional physical publication budget, even before position accuracy is checked. No position solver ran on the truncated receiver output.

## Frozen rule

1. Keep the last two measured visits separately for each antenna, stream generation, pilot edge and capture RF lane. Pair past emissions by signed carrier, require both time gaps to be at most two seconds, reject slopes above 8,000 Hz/s or frame-phase drift above 1,000 samples/s, and extrapolate the paired carrier and phase. Phase uses hardware sample counters in thirds of a sample and the exact 40,000-third frame period. The slope bounds constrain the proposal only.
2. Run the original two scans on the first two eligible visits of a lane and every fourth eligible visit thereafter. On other visits, test predicted phases and carrier frequencies on the current raw samples. A narrow proposal must refine within the nine-sample timing aperture, with interior support and no more than 1,250 Hz displacement, and pass the independent frame-group pilot gate before it can replace the first full scout. When no proposal confirms, a separate shortened blind search covers the full allowed carrier band.
3. Every confirmed first proposal still receives cancellation and an independent residual scout spanning the full allowed band. The shortened scout uses two of the eight original lag correlations, keeps three timing maxima instead of twelve, and refines two blind carrier seeds instead of four. A forecast for an additional distinct pilot can compete with these seeds. The receiver verifies both proposals against the original samples with the original exact versus rolled-control fractional GLRT. If any forecast lacks a verified factor within five samples and 1,600 Hz, repeat both full scans on that visit. Continue updating the lane from its own verified measurements.

The shortened scout is a coverage hypothesis. It searches every timing offset with fewer lag correlations and tests fewer shortlisted proposals. A weaker unexpected carrier can fall outside that shortlist even when a tracked carrier confirms. Periodic full scouts and lost-forecast fallback limit elapsed time to a fresh search. They leave gaps when a new signal is transient or lies outside the blind shortlist.

Two component tests passed. One checks fractional frame-period and signed frequency extrapolation with large absolute counters, startup and a gap. The other admits a planted weaker second carrier through the independent residual path when the first pilot was forecast, and forces a full reacquisition when the forecasted pilot disappears into noise. Both returned synthetic carriers pass the rolled-control margin.

## Reproduce

The comparator was the frozen faster exact receiver, SHA-256 `107909cc17e994950f7ffb2dce215114959565d5874122d958a6480132c242a5`. Its default build matched the frozen binary byte for byte after adding the opt-in tracking build. The first 128 scheduled visits of saved DS30-0016 were fixed before running the variant. Both arms honor the existing quality rules and use independent, empty histories. Two repeats reverse arm order. CPU timing starts at each lane before factor acquisition and ends after the causal continuation update, including the prototype's forecasting and fallback. I/Q reading and subsequent localization are outside this clock.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_venv=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s "$@"
}

algo08_lock "$algo08_venv" -m "$algo08_native.receiver_build" "$algo08_work/receiver-tracking.so" --tracking
algo08_lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python -m "$algo08_native.receiver_tracking" \
  "$algo08_work/receiver-final-candidate.so" "$algo08_work/receiver-tracking.so" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json \
  --bulk /srv/bulk --assets /opt/leo-algo08/current/assets --visits 128
algo08_lock env PYTHONPATH=src "$algo08_venv" -m pytest -q tests/pipeline_eval/test_experimental_receiver_tracking.py
```
