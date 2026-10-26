# Original-window detector parity is established for one window

The first DS24-0011 paired 20 ms window replays exactly using its historical
detector implementation and environment. All ten exported candidates, five
per receiver, have identical ranks, integer/fractional epochs, CFOs, scores
and fractional-margin decisions. Maximum numerical difference is zero. This
qualifies one unchanged-window replay, not corpus-wide detector accuracy or
the interpretation of any candidate as a satellite.

![Archived versus replayed candidates](replay_candidates.png)

The window was fixed by recording order in the preceding availability study.
It was not selected for detector agreement or signal strength. The public
catalogue read port reports the original run succeeded; its code digest
`124afbbc81870a4079b272bd828d4a99f716e54624a073d9cb13acc2a1b7fe16`
and environment digest match the deployed implementation. The replay used
that deployment, not the workspace's unrelated acquisition edits. Both digests
were checked before and after processing, and the original tracking contract
matches its frozen dataset hash. No service state, database record or source
implementation was changed.

The public bounded reader was exhausted. It verified 77,511,985 compressed
bytes, all 64 individual window hashes, and 102,400,000 uncompressed bytes with
the final chunk digest. Only sequence 0 was retained in memory for detector
processing: 200,000 complex samples per receiver at 10 MS/s. No IQ was copied
to the report or processed from any other chunk.

The original native V2 policy bypasses the 2.5 MS/s predictor. Replaying the
full `analyze_window` port returned `processed`, matching the original sample
counter and receiver IDs. Applying the original tracking adapter's fractional
completion filter gives five candidates per receiver. All 82 declared field
checks pass. Three comparator tests establish that missing candidates, changed
identities/gates, nonfinite values and out-of-tolerance CFOs cannot pass parity.

The replay took 3.987 s including imports and chunk verification, of which
1.709 s preceded detector execution. The read-only historical-authority query
took 0.990 s. These are host preparation timings, not an embedded benchmark.
The invocation stayed within its 90 s wall cap and was not repeated. An earlier
metadata helper's default 64 MiB bound was increased for the already measured
119,545,966-byte dataset manifest before any IQ processing; its input and
source selection were unchanged.

Both raw power summaries label the window quiet under their aggregate digital
threshold, yet RX1 contains an exported GLRT candidate with margin about .206,
above the .025 detector gate. Therefore the power label does not establish a
noise-only window. No signal injection, bias estimate, association decision or
position fit follows from this parity result. A later clean/weak/crossing
experiment still needs a declared waveform, realistic background treatment,
known injected identities and evaluation of the actual selection/track stage.

The frozen [protocol](REPLAY_PROTOCOL.md), [replay source](replay_one_window.py),
[owned tests](test_replay_one_window.py), [complete comparison](replay_one_window.json),
[historical authority](replay_authority.json), [authority reader](replay_authority.py)
and [metadata extraction](replay_metadata.json) preserve the evidence. The
original IQ remains an external read-only dependency. Existing service-account
read permissions were used; no permissions were changed and no new RF was
collected. Secrets from the existing database configuration were never logged
or written to the report.
