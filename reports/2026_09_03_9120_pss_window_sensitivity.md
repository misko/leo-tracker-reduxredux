# Native-25 PSS window/stride sensitivity for `9120aba2922e`

## Conclusion

For this recording, the **62.5 ms window / 31.25 ms stride** variant is the best of the
three.  It preserves the same 12.46 s dominant track and the same approximately
+2.556 kHz/s phase-derived frequency rate, while doubling timing cadence, slightly
reducing quadratic RMS residual, increasing blind-anchor yield, and producing the most
stable rate when the 50%-overlapped observations are split into two non-overlapping
parities.  The 250/125 ms variant gives no RMS improvement and has only 66 dominant-track
points.

This is evidence for promoting 62.5/31.25 ms to a broader replay candidate, not yet for
changing the global default: this is one strong PSS event in a partial recording with
583,000,000 missing samples and 20 non-empty continuity segments.

## What the current setting means

The production setting is a **125 ms complete-IQ block with 62.5 ms stride**, hence 50%
overlap.  At 25 MS/s that is 3,125,000 complex input samples per block.  It contains about
93.75 nominal 750 Hz PSS opportunities (the observed median frame support here is 94).
This is an evidence-aggregation block, not the duration of the PSS waveform itself.

The blind acquisition layer samples the complete-block grid at an independent 0.5 s
anchor cadence.  After it acquires a track, the refinement pass searches every complete
block on the configured 62.5 ms grid inside the acquired span.  The sensitivity replay
changed the complete block and refinement stride together while leaving the 0.5 s blind
anchor policy and all detector/association thresholds fixed.

Within a block the detector searches the same frequency hypotheses, folds matched-filter
evidence over the periodic PSS opportunities, gates candidates by peak/median and robust-z
criteria, and derives a frame-phase mode.  Associated per-block modes are then fitted with
an unweighted quadratic: every retained mode has equal fit weight.  Because adjacent
blocks overlap by 50%, twice as many points do not mean twice as many independent points.

## Replay geometry

| Variant | Window | Stride | Input samples | Nominal PSS opportunities | Overlap |
|---|---:|---:|---:|---:|---:|
| Half | 62.5 ms | 31.25 ms | 1,562,500 | 46.875 | 50% |
| Current | 125 ms | 62.5 ms | 3,125,000 | 93.75 | 50% |
| Double | 250 ms | 125 ms | 6,250,000 | 187.5 | 50% |

The normal 4,194,304-sample safety cap would silently cap a native-25 250 ms request.  The
double-window replay raised only this mechanical cap to 6,250,000 samples.  Every emitted
block was checked to have the exact requested size; no clipped blocks were used.

## Results

| Metric | 62.5/31.25 ms | 125/62.5 ms | 250/125 ms |
|---|---:|---:|---:|
| Dominant-track points | **270** | 134 | 66 |
| Dominant-track span | 12.46 s | 12.46 s | 12.46 s |
| Quadratic RMS residual | **0.03782 µs** | 0.03955 µs | 0.03822 µs |
| Maximum absolute residual | 0.10399 µs | 0.09898 µs | **0.08484 µs** |
| Phase-derived rate | 2.554584 kHz/s | 2.556487 kHz/s | 2.556827 kHz/s |
| Rate delta from current | -1.902 Hz/s (-0.0744%) | — | +0.340 Hz/s (+0.0133%) |
| Blind anchors with candidates | **33/76 (43.4%)** | 24/74 (32.4%) | 22/73 (30.1%) |
| Refined tracking blocks with candidates | 270/270 (100%) | 134/134 (100%) | 66/66 (100%) |
| Median robust-z on dominant track | 25.36 | **26.60** | 24.52 |
| Strong local-window fraction | 100.000% | 99.992% | 99.976% |
| Non-overlap parity rate spread | **0.072 Hz/s** | 0.253 Hz/s | 9.758 Hz/s |

All three results agree on the scientifically important trajectory.  The half-size result
does not pay an observable precision penalty on this strong signal: its RMS is marginally
lower and its two interleaved, non-overlapping fits agree most closely.  The larger window
does reduce the single largest residual, but does not reduce RMS, lowers cadence, and its
two non-overlapping parities are less stable because much less timing support remains.

The blind-anchor candidate fractions are useful empirical yield measures but are not a
pure SNR comparison: changing block duration also changes the folded-score distribution
and slightly shifts the anchor centers.  The locked-region result is cleaner—every dense
tracking block succeeds for all three variants.

## Method and provenance

- Recording: `cap-20260903T004006-9120aba2922e`, native 25 MS/s
  `radio_pluto_19f2/RX1` path.
- Exact path binding: `sha256:955dc197082d54231da6208fb890f2fb933cb41bc9d5b14d30d22e84fe5f2268`.
- Release-matching implementation: `2524936bd8bd6fee417cfcedcdb6b44ed6bd9a7f`.
- The current 125/62.5 ms result was loaded from its persisted production product.  The
  half and double variants were recomputed from the same immutable IQ and binding.
- Raw compressed and uncompressed shard digests were verified when each shard was first
  loaded.  A small decompression cache changed only I/O cost, not detector inputs.
- No new RF was collected, and production products were not modified.

## Artifacts

- `comparison.png`: three-way timing residual and frequency-rate visualization.
- `comparison.json` and `comparison.csv`: exact summary and rate deltas.
- `pss-half-62.5ms-31.25ms.json` and `pss-double-250ms-125ms.json`: validated full PSS
  products.
- `run_window_sensitivity.py`: reproducible recording-specific replay driver.
