# Guided frequency-support boundary result

The isolated `1e-6 Hz` support-guard change passed this bounded numerical
qualification. The immutable result is `results.json`, SHA-256
`a8cbd047d7185dda1056dcf798db0597937d33f8e4752d8d4bafcc0c0099664a`.
Its source lock is SHA-256
`de43a9500bf40ba36f77d0150eb4e42f89069432c531f03659a7872588943f7b`.
All 93 source hashes remained stable, every input remained immutable, and the
run completed in 2.76 seconds inside the fixed 120-second CPU-0 budget.

## Direct reference points

Both APIs were called once at each of the 42 coordinates frozen by the earlier
reference-point diagnostic. On all 41 ordinary points, every scientific output
field was identical after excluding CPU and wall timing fields.

The one numerical-boundary point had an expected/scoring CFO separation only
`2.84e-9 Hz` beyond the original half-symbol-frequency support check. The
original API returned no observation. The guarded API returned a complete,
supported 14-frame observation with status zero, margin `0.3980`, zero timing
error, and `2.82e-9 Hz` physical-CFO error. This changed its supplied-reference
pair from rejected to accepted.

Across all fixed pairs, original acceptance was 19/21 and guarded acceptance
was 20/21. The remaining rejected pair was unchanged: one point returned status
2 and selected a physical CFO about 226.8 kHz from the supplied reference. The
guard therefore admitted the roundoff-boundary input without masking the real
physical-innovation failure.

## Causal controls

The unchanged tracking controller processed all 42 legacy control and sequence
occurrences with separate original and guarded engines. Both methods passed all
84 receiver truth policies. Their full scientific decisions were identical in
all 42 occurrences, including the selected identities and routes:

- 76 cold blind receiver calls
- 4 guided receiver calls
- 4 blind fallbacks after guided failure
- 52 active receiver decisions

## Scope

The direct-point result uses timing and frequency hypotheses supplied from a
previous full-application receipt. It shows that the new API admits one valid
floating-point boundary coordinate and otherwise preserves the tested native
science. It does not show that blind acquisition can discover that coordinate,
does not increase causal control detections in this set, and does not qualify
broader accuracy or end-to-end speed. Point and control timings in the receipt
are diagnostic only.

Before the source freeze, 15 owned runner and engine tests passed. No full
application rerun, validation or holdout access, RF collection, QNAP write, or
production change occurred.
