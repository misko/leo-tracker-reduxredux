# Early confirmation before cache acceptance

**Development outcome: quality fails.** Complete-call CPU improves well beyond
10x, but this version retains only 65/79 reference receiver identities versus
the original native baseline's 67/79. It removes two unmatched 5 MS/s outputs
while also losing two previously retained identities. It is not a qualified
small-loss replacement and does not supersede the earlier rescue result.

| Rate | Application mean CPU | Candidate mean CPU | CPU speedup | Baseline → candidate identities | Baseline → candidate unmatched |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1488.92 ms | 13.18 ms | 112.97x | 33/37 → 32/37 | 3 → 3 |
| 5 MS/s | 3998.47 ms | 23.20 ms | 172.35x | 34/42 → 33/42 | 2 → 0 |

All reference-positive visits retain an associated receiver, but receiver-level
loss fails the 3% band at both rates. Candidate maximum wall times are 18.13 ms
and 35.61 ms, with no calls over 120 ms. These fast results exclude rescue by
design; they must not be confused with a result retaining the earlier rescue
variant's 78/79 development identities.

At 2.5 MS/s visit 1089 RX1 changes from retained to missed after guided failure
and unsuccessful blind fallback. At 5 MS/s visit 1104 RX0 changes from retained
to missed on cold discovery; unmatched RX0 outputs at visits 1087 and 1101
become inactive. These receipts identify changed decisions, not the precise
cause (integer timing, score margin, CFO trust, or pair compatibility). Do not
attribute the new misses solely to rounding without testing those alternatives.

Additional confirmation calls total 184 at 2.5 MS/s and 199 at 5 MS/s. Guided
routes are accepted on 13 and 20 receiver visits, respectively. The complete
replay finishes in 179.31 seconds, sources stable and inputs unchanged. Timing
includes conversion and added confirmations, with CPU0 and numerical threads=1.
Methods rotate within each visit and use separate state. See
`results.reporting_fix.real.json` and `reporting_fix_lock.json`.

The next bounded diagnostic should inspect all acquired candidates at the two
newly missed development receivers, scoring the predicted integer and adjacent
integer timings, and compare margin/CFO/pair gates separately. Preserve this
failed result. A new variant must still address the wider proposal-coverage
problem; restoring these two identities alone would only recover the original
native baseline's insufficient 67/79 retention. No new holdout was opened.

The new adapter keeps the original nuisance-aware native discovery, then
requires a fresh raw early-symbol native score at rounded integer timing before
pairing or cache establishment. Guided reuse requires both fresh original
guided evidence and fresh early-symbol confirmation. Rejected confirmation
falls back to discovery; failed discovery clears the track. This is a separate
candidate, with no changes to frozen implementations or production code.

## Constructed control gate

All 132 required receiver policies pass across 42 original control cases and
24 original/swapped negative executions: 52 truth-associated positives and 80
correct negatives. The run completed in 2.72 seconds, with 508 additional raw
confirmation calls, stable source hashes and unchanged input arrays. Each
control execution starts with fresh state. This is not evidence of a rare
field false-alarm rate.

Three controller tests pass: nuisance-rejected proposals cannot be resurrected
by raw scores; integer confirmation preserves discovery-fit provenance while
guided timing stays unfitted; failed fresh confirmation plus failed fallback
clears an established track. Native point numerical qualification is separately
recorded in `../native_early_profile/REPORT.md`.

The original controller counters omit the added confirmations; evaluation
receipts record them separately and include their cost in whole-call timing.
No same-receiver rescue or broader temporal discovery is present in this
version. Suppressing extras alone cannot qualify it as a small-loss replacement.

Recorded development evaluation is governed by `REAL_DESIGN.md`. Final
qualification requires a complete quality/compute comparison and fresh
disjoint recorded validation. Earlier failed holdout results remain unchanged.

## Reporting correction

The first recorded replay completed 64 visits but failed in summary construction:
the direct assessment API exposes scientific outcomes without the convenience
flags expected by the runner. No final result was saved. The traceback and
disposition are recorded in `reporting_failure.json`. A separately pinned
adapter derives only these reporting flags, preserves assessment progress, and
repeats the unchanged detector/membership under the same timing protocol.
Five tests cover all reference-association outcome classes, including an active
wrong identity counting as both a miss and an unmatched output. Together with
the controller tests, eight local tests pass. The failed attempt is not a second
independent scientific replication.
