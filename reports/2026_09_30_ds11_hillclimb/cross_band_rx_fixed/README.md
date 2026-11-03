# Fixed-position drift allocation: only RX1-fixed passes

At the original eight training-selected IID positions, correcting RX0 while
leaving RX1 unchanged improves conditional held prediction on6/8 scans. The
other two allocations fail the declared fixed-position advancement gate.
No new positions or geographic errors were computed.

| Allocation | Positive scans | Total held gain, nats | Median scan gain, nats | Gate |
|---|---:|---:|---:|---|
|RX1 unchanged; correct RX0|6/8|152.196|4.321|Pass|
|Symmetric|4/8|-3.510|-0.722|Fail|
|RX0 unchanged; correct RX1|1/8|-214.011|-20.603|Fail|

The native RX1-minus-RX0 drift prediction comes from the frozen leave-NORAD
cross-band model. The proposed differential correction subtracts each target's
constant training prediction from its fitted line; it is zero outside the
donor-center interval. Allocation preserves that differential correction while
changing the assumed common receiver drift. Convert to canonical11.2GHz Hz
only when modifying the observations. Original masks, timestamps, candidate
banks and all unpaired tracks remain unchanged.

Two overlapping pair rows in scan12 are excluded in full because they share
a track.128 eligible pairs remain across the screen. The verifier reconstructs
all15,462 per-observation corrections using scalar arithmetic and obtains exact
agreement. Every original training score replays exactly (0-nat discrepancy).
No conditional MAP candidate changes occur in any allocation on any scan.
The held score is the joint mixture normalizer minus the training mixture
normalizer with candidate CFOs fitted only to training observations.

Two tests pass for allocation signs/common-mode ambiguity, native-to-canonical
units, held-frequency isolation and outside-interval fallback. Source bindings,
correction uniqueness, conflict exclusions and score aggregation verify. The
verifier independently replays corrections, not the candidate likelihood. The
single-thread run completes with exit0 under the90second cap; no retries,
position fitting, reference use, IQ reads or orbit updates occur.

The RX1-fixed result passes a necessary check for a bounded geographic
comparison; it does not establish a physically stable receiver or a lower
position error. Any geographic experiment should retain all three allocations,
select optimizer starts only by training objective, preserve the unchanged
baseline, and report all failures and reference errors. The preferred allocation
must not be chosen after examining geographic truth. Earlier DS7–9 drift
experiments also showed allocation-dependent held gains without dependable
geographic improvement.
