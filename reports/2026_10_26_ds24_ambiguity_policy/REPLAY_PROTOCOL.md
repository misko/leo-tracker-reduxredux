# One unchanged original IQ window

Use DS24-0011, segment 0, sequence 0, chosen by recording order before detector
outcomes. This extends the prior metadata-only availability check. It does not
select a favorable signal, declare a noise-only window or perform an injection.

The public read-only catalogue port finds the sealed run succeeded and its
implementation/environment digests exactly match the deployed
`native-scope64-v2-3460060352b364a9` source and Python environment. Both digests
are asserted before and after replay. Existing workspace acquisition changes
are not used. The original tracking contract hash must match the dataset
authority. No database or service state changes.

Exhaust `ShortWindowReader.windows(start_sequence=0, stop_sequence=1)`, verifying
the entire containing chunk's compressed bytes, all 64 window hashes and final
uncompressed digest. Retain one paired 20 ms window in memory and run the
original `analyze_window` port with the persisted native-rate V2 policy. No IQ
payload is copied to the report. Convert the result with the same public-field
filter as the original tracking adapter.

For both receivers, require identical ordered candidate counts, ranks, integer
epochs and fractional-margin decisions. Require absolute differences no larger
than 1e-6 Hz CFO, 1e-9 sample fractional epoch, and 1e-10 for exact/control/margin
scores. Keep all differences and failures; do not retune tolerance after the
result. Three owned comparator tests precede replay. Limit this one invocation
to 90 s wall time plus a five-second termination grace, one BLAS thread; do not
launch another window on failure. A matching window proves this replay only,
not corpus-wide detector correctness or realistic synthetic-waveform closure.
