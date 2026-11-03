# Prospective known-pilot frequency protocol

Freeze DS11 session `scan-fw-a32c07775a887379` and the two exact scan-0 tracks
conditionally assigned to NORAD 65512 by the original-IID training fit at
confidence 1.0.  Select every observation whose already-frozen localization
training mask is true: 46 plus 65, for a complete denominator of 111.  Order by
track ID then observation index.  Do not select or filter using IQ, pilot score,
frequency correction, localization-held value, or reference coordinate.

Preparation reconstructs the public trajectory without reading IQ and requires
exact track identity, visit sequence, support-center timestamp, receiver, RF,
channel, candidate rank, raw and analysis manifest bindings.  For each row,
freeze the raw acquisition candidate, native cached CFO, exported canonical
dealiased frequency, and its integral alias relation:

```
native_dealiased = exported_measured_hz * actual_rf_hz / 11.2e9
additive_alias = (native_dealiased - raw_cached_cfo_hz) * 4.4e-6
```

The additive alias must be integral within `1e-8`; it is the negative of the
deployed relative alias index.  Preserve this alias and the original
support-center timestamp.  A fitted native residual maps back as
`residual_hz * 11.2e9 / actual_rf_hz`; it does not trigger alias re-estimation.

For each frozen row, use the public read-only IQ store to read its existing
visit, isolate the exact 20 ms probe for receiver 0, and save it with a digest.
Checkpoint every terminal row atomically.  Keep chunk-read, binding, shape and
demodulation failures in the 111-row denominator without replacement or retry.
Run at most three sequential extraction processes, each capped at 120 seconds,
with one thread.  The source store and every QNAP path remain read-only.

For each readable excerpt, reuse the established native-rate known-pilot
demodulator, deterministic upconversion phase correction, and frequency
estimator.  Demodulate the first eight complete frames and compare exactly three
arms:

1. cached acquisition frequency: native residual 0 Hz;
2. short pilot: fit symbols 2–65;
3. long pilot: fit symbols 22–221.

The short and long fits use the fixed `[-1500, 1500]` Hz search, 25-Hz grid and
bounded scalar refinement already used by the prior assay.  For all arms,
calibrate independent frame/carrier gains on symbols 22–221 and evaluate only
symbols 222–301.  Report per-frame NMSE, residuals, search-bound hits, carrier
coverage, mapped canonical corrections, and every weak or failed result.  The
within-excerpt held symbols do not select an arm or row.

The frozen observations document is loaded, and its full visit, timestamp and
mask metadata are checked.  Do not read IQ or use measured-frequency values for
the 65 localization-held observations, and do not replace or modify them.  Do
not fit position, score geography, alter candidate identity, extrapolate a
correction to another visit, or filter by waveform quality.  Run at most one
180-second numerical process with one BLAS thread and checkpoint each terminal
row.  Preserve timeout and partial coverage as results.  Any later geographic
experiment requires a separate prospective protocol and review.
