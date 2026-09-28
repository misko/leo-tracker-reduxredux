# DS7 wave-two exact baseline solver

This directory contains reference-free, unscored solver evidence. The wave-two
adapter changes only the execution of the frozen stationary Student-t4 offset
profiler: fixed-point iterations for candidates of a track are batched, while
the starts, stopping rule, root brackets, Brent solves, loss selection,
objective, finite-difference gradient, masks, candidates, bounds, and optimizer
remain unchanged.

On the real frozen prefix-two inputs, three objective/gradient probes matched
the wave-one implementation exactly. Objective-call speedups were 2.53x to
3.69x. Sealed end-to-end single runs took 19.45 and 17.65 seconds, compared
with 24.34 seconds in wave one. The sealed prefix-two fit took 32.98 seconds,
compared with 56.97 seconds. End-to-end timings include the training RF RMS.

The repeated single and prefix-two scientific responses match their wave-one
responses exactly after excluding the newly declared RMS fields. No scores or
reference coordinates were read or produced.

RF RMS is pooled over training observations after choosing each track's visible
training-MAP candidate and subtracting its stationary training offset. It is a
training-conditional aggregation control; catalogue ambiguity is not resolved
with held-out or reference information.

The first prefix-four launch exposed a frozen-loader coverage error: the bank
exporter intentionally requires at least two training observations and one
held-out observation, but the old loader required bank entries for all exported
observation tracks. The active wave-two loader now enforces the exporter's exact
eligibility rule, rejects missing eligible, duplicate, unexpected, or ineligible
bank tracks, and reports exclusions by ID and reason. The prior fast source is
preserved under `frozen-source/` at its original hash. A deterministic single
remained exactly unchanged apart from the new exclusion diagnostic. Prefix-four
then converged in 84.93 seconds; exactly one input track was legitimately
excluded because it had seven training and zero held-out observations.

The measured runtimes support the declared 300-second per-unit cap for the
bounded prefix-1/2/4/8 panel. The first wave-two tranche is restricted to that
panel and eight independent singles, with at most 1800 total adapter-seconds.

All eight independent fits converged without boundary hits. The first-eight
joint fit also converged without a boundary hit in 170.30 seconds. Across its
eight inputs, 486 tracks were eligible and two were explicitly excluded by the
frozen mask rule. The first-eight scan-estimate index is
`scan-estimate-index-first8-v1.json`; it contains only independent, qualified
training-side estimates for the predeclared aggregation controls.

One final historical-style initialization control used two starts: the
spherical equal mean of the eight qualified independent positions with each
recording's independently fitted timing offset, and the donor-center position
with those same timing offsets. Historical DS6 supplied independent timing
offsets and tried a zero-position start; the spherical equal-mean position is a
declared wave-two addition. The exact objective, banks, optimizer settings, and
bounds were unchanged, but this two-start control is not a matched-call
comparison with the three-start baseline. It converged without a boundary hit
in 120.53 seconds and 43 total objective/gradient evaluations.

The executed historical-style adapter and arm are preserved under
`frozen-source/` at hashes `eb770005...` and `c3e499f1...`. The later ready-v2
arm and active adapter add provenance hardening only: every source request and
response must be present in its run seal, and its session must match the joint
document order. The executed first group passed that audit; it was not rerun.

All attempted wave-two solver adapter processes, including regressions and the early
1.59-second loader-gate failure, consumed 623.583 adapter-seconds of the
authorized 1800-second lease. No further scientific runs were made.
