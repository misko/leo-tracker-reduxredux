# Independent protocol and recovery review

Reviewed the frozen protocol (SHA-256
`d8aab4fda51e90ef46c0b259f875b96011a9aae1e1649ef10272bde665ad65ef`) and
the initial recovery helper (SHA-256
`f44fb39b53d2ef37913d806b62aa6639a8b65059b7c03c79c5d68d3620d7918d`).
This review did not access TEST data, run a fit, or inspect an effect estimate.
Ruff passes for the reviewed helper.

The protocol has the right scientific guardrails. It fixes TRAIN-only support,
treats candidate equality as provisional, requires a contemporaneous matched
pair plus independent time/frequency/lane gates, separates differential from
common residual terms, and uses whole scan/satellite bootstrap units. Its
interpretation correctly avoids treating age correlation as causal or using an
inconclusive result to introduce flexible timing, drift, or location terms.

The reported first-scan dry run is useful evidence that the public recovery
path can make exact joins: 93 tracks and 1,356 observations joined with zero
missing or ambiguous rows across the two receivers. Preserve that accounting
and its source/input bindings in the final recovery artifact.

The initial helper does **not yet implement enough of the frozen contract for
effect estimation**. It reads pooled group lists but does not assert their
exact 151-ID TRAIN membership or prove disjointness from VAL/TEST. It checks a
prepared-evidence observation-ID join but does not bind receipt/NPZ hashes,
the causal TLE input, or the sealed fixed `(track_id, candidate_id,
observation_id, session_id)` support. Its output has a stream ID and support
interval only; it does not recover channel, sideband, sample rate, or the
time/frequency samples needed to apply the prespecified overlap, 80-ms, and
2-kHz gates. Exceptions abort a worker map rather than leaving per-session
failure accounting.

Accordingly, the running full metadata recovery can establish feasibility of
the public graph join, but it should be labeled preliminary until a bound
artifact records the missing identities, lane/frequency inputs, causal
provenance, and every failure/rejection reason. No receiver-orbit conclusion
is supported at this stage.

## Preliminary result audit

The present `results/inference.json` is sealed internally (SHA-256
`3fd1b297f15df01ad35d8b50415ddcf28ae75b615b3dd20ff2e076727381f6a8`), but
it is **superseded** for scientific use. It was produced before the current
analyzer source (current SHA-256
`2f17ee11b5ba463207054e8f88211738c08b7deec58c1aaede7d8907179c5dc5`) and
does not bind an analyzer hash. It contains the earlier `tle_age_s` and age
quartiles derived from snapshot collection time, rather than per-candidate TLE
element age. The current source correctly reports element-age strata as
unavailable and adds an intercept to the centered-time polynomial. A direct
constant-offset check confirms its slope and quadratic terms are invariant to
an added constant.

The stale artifact has 486 passing pairs from 407 scan/candidate groups, but
73 groups contain multiple pair rows and one RX1 track is reused twice. Its
reported pooled differential slope, including the approximately -4.14 Hz/s
mean, must not be treated as evidence or a calibration input until a fresh
source-bound run reports this multiplicity, first/second TRAIN-group split, and
RF/lane-stratum consistency. Current source also uses training masks and no
held/reference path, and its exact 151-session/cache/observation support checks
are appropriate for the fresh run.

## Corrected result audit

The corrected result is source-bound and internally sealed: analyzer
`8f49f6372d092660aa51418893a21e70885dfdd8d42891525e9fe2cb532b5688`, result
`12a5906d2c9611799065d1e7fcb736f21de0ff0bb7b7d6ebb1a55fb6fdec65d1`.
The sidecar matches. Ruff and the three focused tests pass. The source now fits
an intercept, uses matched cache-relative seconds, verifies exact 151-session
TRAIN membership and fixed `(session, track, candidate)` support, and binds
analyzer, parent, cache, capture/analysis manifest, recovery, and causal
snapshot digests. It uses training masks only and records no held, validation,
TEST, reference, or position-refit use.

The output honestly labels snapshot *collection* age and marks per-candidate
element-age strata unavailable. It reports 486 passing pairs in 407
scan/candidate bootstrap groups, 6,281 matched samples, and one reused track
(at most two passing pairs per track). The group bootstrap therefore reflects
the intended scan/candidate unit, while the small reuse is disclosed.

The required consistency checks do not support a simple calibration claim.
The differential-slope estimate differs across the two TRAIN blocks: first-8h
mean -6.21 Hz/s (95% bootstrap interval -7.84 to -4.67) and second-8h mean
-2.49 Hz/s (-5.17 to +0.78). RF/lane strata also vary materially, including
both negative and positive estimates. The pooled differential mean -4.52 Hz/s
is a descriptive summary, not evidence of a stable receiver correction.
Common-mode terms cannot be attributed to orbit/propagation from this audit:
element epochs are absent and snapshot collection age is not a calibrated
orbital-error covariate. These results are suitable for hypothesis development
and further prespecified checks, not a calibration or localization change.
