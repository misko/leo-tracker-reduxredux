# Exact source-holdout eight-scan screen

Status: prospective protocol. The input context and plan builder must be
reviewed and frozen before the one-time plan is emitted. This document does not
authorize plan generation or fits.

Use exactly original DS11 indices `0,4,8,12,16,20,24,28` and four existing
qualified full-data endpoints in fixed tie order: original IID Student-t4/100,
`source_receiver_equal`, robust Student-t8/100, and robust Student-t4/200.
Freeze each scan's memberships from its original same-scan IID endpoint using
training observations only and the digest-bound candidate-ID-to-NORAD map. A
physical-NORAD fold contains every receiver and RF track assigned at conditional
probability at least 0.90 and is eligible at two or more tracks. Ambiguous tracks
remain in all retained objectives. Candidate mixtures stay complete.

For every family and eligible source, delete that source and perform one exact
local refit from the family's existing full endpoint. `source_receiver_equal`
uses full-scan weights subset without renormalization. Keep the existing bounds,
optimizer settings and qualification gates. Score omitted tracks with original
IID Student-t4/100: profile each candidate CFO on that track's training values,
then compute joint-minus-training log mixture density with the same CFO.

The immutable plan may cache only exact qualified results whose full endpoint,
membership, observation coverage, source weights where applicable, model,
scorer, input artifacts and source hashes match the newly frozen scan context.
Cache all 56 proven index-0 folds: 28 completed family folds, four earlier exact
audit folds and 24 atomic folds. Cache the eight qualified index-16 exact-audit
folds. All other jobs start pending. Failed influence approximations provide no
cache status; only their independently qualified exact fits can be reused.

Run one scan index at a time, with at most three one-fold processes concurrently.
Every atomic fold has one BLAS thread and a 90-second cap. Preserve every
terminal failure. Do not retry, add starts, filter folds or replace a failed
source. If the current scan cannot produce all qualified folds with identical
coverage across the four families, mark that scan unselectable and do not
attempt later indices: the fixed full-eight gate has already failed. Preserve
all eight indices in the denominator and mark later ones not attempted.

For a selectable scan, choose the family with maximum sum of common held score
over all eligible folds; exact ties use the fixed family order. Seal every
reference-free selection before computing any geographic error. Advancement
requires 8/8 selectable scans, at least five selected-position wins over IID,
at least 10% median geographic-error reduction and nonworse P90. Only then may
the frozen additional confirmation panel run, without tuning.

Plan preparation is a training-only numerical pass, not a fit. Run it once
after review with one BLAS thread, one worker and a 180-second process cap. It
must emit jobs in index order, then family order, then ascending NORAD.

