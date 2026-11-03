# Prospective scan-16 known-pilot replication

Freeze scan index 16, DS11-F045 session `scan-fw-6a8bd0ca578b58eb`, and the
three tracks in the pre-existing `target_selection.json`.  That artifact applies
the reference-free rule “largest exact IID source-deletion east/north movement
among all 18 qualified folds; ties lowest NORAD” and selects conditional NORAD
67103.  Use all and only the 124 observations whose original localization mask
is training.  Preserve all 81 localization-held values and do not open their IQ.

Order rows by the target-selection track ID order and then observation index.
Repeated visit numbers are valid.  Freeze and check the full track visit/time/mask
sequence plus each row's exact visit, receiver, probe index, candidate rank,
support-center timestamp, RF, channel and acquisition candidate.  Record
repeated visit groups and repeated exact acquisition-identity groups explicitly;
do not require 124 unique visits and do not deduplicate rows.

Use the same alias convention as the scan-0 pilot:

```
native_dealiased = exported_measured_hz * actual_rf_hz / 11.2e9
additive_alias = (native_dealiased - raw_cached_cfo_hz) * 4.4e-6
```

Require the alias to be integral within `1e-8`.  A fitted native residual maps
to canonical Hz by multiplication with `11.2e9 / actual_rf_hz`; preserve the
original alias.

Read existing IQ through the public store in read-only mode.  Before each read,
checkpoint the row as active.  Save the exact 20-ms excerpt for the frozen
receiver, and checkpoint every success or failure.  A killed active row becomes
an interrupted failure and is never retried.  Continue untouched rows for at
most three sequential extraction processes capped at 120 seconds each, with one
thread.  Remaining rows after the process budget stay in the full denominator
as not attempted.  Never mutate a QNAP path and collect no RF.

For every readable excerpt, reuse the proven demodulator, phase convention and
frequency estimator.  Demodulate eight frames and carry all three fixed arms:
cached acquisition CFO, symbols 2–65, and symbols 22–221.  Both fitted arms use
the established `[-1500,1500]` Hz search.  Calibrate gains on symbols 22–221 and
evaluate symbols 222–301 only.  Held symbols do not select an arm or row.  Keep
all weak estimates, search-bound hits, demodulation failures and unavailable
rows.  Use one numerical process capped at 180 seconds and one thread.

This directory performs measurement only.  It does not select a waveform arm,
change candidate states or timestamps, fit position, inspect the roof reference,
or make a promotion claim.  A separately frozen matched positioning protocol
may carry both complete arms after review.
