# Causal freshness confirmation: no transferred position gain

The frozen five-scan confirmation gate **fails**. All five baseline/fresh pairs
qualify. Three banks have no changed candidate records and reuse their exact
baseline outputs. The two changed banks move reference error by less than
one metre; neither improves it.

| Full-manifest index | Original error | Fresh error | Change |
|---|---:|---:|---:|
|10|2408.557m|2408.557m|exact reuse|
|18|768.503m|768.503m|exact reuse|
|35|3799.611m|3799.654m|+0.043m|
|60|2275.352m|2275.352m|exact reuse|
|75|9620.020m|9620.312m|+0.292m|

Five-scan median remains2408.557m; mean changes3774.409m to3774.476m and
P90 changes7291.856m to7292.049m. The prospectively required index75 gain was
481.001m, the larger of100m or5% of its baseline error. No threshold is changed
after observing these results. No failed outputs or alternative starts are
removed from the comparison.

## Why this does not confirm the original gain

These five recordings were selected from the remaining43 solely by pre-capture
orbit metadata, before exporting candidates or inspecting position errors.
The earlier additional12 panel had no capture-window update at all. Among the
five new banks, only index75 contained a newer-epoch candidate: NORAD53505 in
thirteen track candidate lists. The historical-retention update for NORAD53480
occurred in none of the banks.

After both endpoints were selected, the [predictive diagnostic](predictive.json)
found that NORAD53505 was the training-MAP identity for **zero tracks**.
Its summed conditional probability across thirteen occurrences was1.97e-14
under the original fit and3.87e-38 under the fresh fit. Thus shortlist membership
did not supply an informative test of correcting an orbit for a source supported
by the measurements. These are model-conditional probabilities, not independently
authenticated satellite identities. The test fails to establish a transferred
gain; the sub-metre changes are not evidence of a meaningful accuracy loss.

For index75, fresh-bank held score at its refitted endpoint is-9881.416,
versus-9881.419 at the original endpoint. Original-bank held score is-9881.423
at the original endpoint and-9881.421 at the fresh endpoint. These differences
are negligible beside the unchanged9.62km reference error. CFO fitting uses
training points only; held points still share source/extraction errors.

The original-panel case remains an isolated, verified improvement from8052.49m
to4666.36m. Its original-orbit control reproduces the old result exactly. This
confirmation does not establish a dependable general DS11 replacement or lower
median error. All errors use the existing unsurveyed installation reference.

## Verification and retained evidence

All five cached-product exports passed in70.2–92.1seconds under180second caps.
Preparation patched0/0/736/0/634 candidate slots, retaining every byte-changed
record including same-epoch rounding; original-state replay was exactly zero
for position and velocity on every scan. Exact archive bytes and pre-capture
publication receipts bind all replacements. Original tracks, masks, identities,
candidate order, catalogue divisors and likelihoods remain unchanged.

The five baseline four-start fits took20.4–33.3seconds; the two changed-bank
fits took22.3–24.9seconds, below90second caps. The three no-op outputs are labeled
as reuse, not new optimizations or wins. Nine component tests pass. An independent
review and [pre-fit slot audit](patch-audit.json) verify complete candidate coverage,
array/declaration alignment, masks, record digests, proofs and no-op invariants.
[verification.json](verification.json) additionally checks every receipt's arm,
index and runner digest, frozen source hashes, identical fourth seeds, numerical
qualification, highest-qualified-score selection and exact no-op equality.

[assessment.json](assessment.json) contains the complete paired metrics and
unchanged gate. [FIT_PROTOCOL.md](FIT_PROTOCOL.md) predates all position fitting.
`runs/` preserves all starts and terminal receipts. No post-capture orbit input,
new RF collection, production change or original-bank modification was used.
