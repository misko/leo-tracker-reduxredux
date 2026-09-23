# Frozen 24-hour validation protocol

Window: capture starts in [2026-09-22 15:15, 2026-09-23 15:15) UTC. Exclude every
session in the previous sixteen-scan experiment. Freeze availability at inventory
creation; subsequent worker completions do not change this cohort. No reference
error, residual score or preferred satellite identity enters cohort selection.

The inventory contains 116 eligible recordings (3,741 tracks; 98,082 observations),
16 excluded development recordings, and three unavailable positioning products.
Two publication-index boundary candidates are outside the capture-start window.

## A. Conditional method repeatability

Use all 116 eligible scans as seven chronological nonoverlapping groups of sixteen
and one separate four-scan remainder. The fourth group spans the gap left by removing
the development scans. These are new groups relative to this experiment, not a claim
that no historical researcher has ever inspected their recordings.

Refit each group independently with the previous bounded joint algorithm: group-only
Sacramento/Reno blind-prior seeds, group-specific published candidate union, fixed
randomized observation masks, integer timing in [-5,+5] seconds, capped duration
score, preserved incumbents and 35 evaluations per basin. Compare coordinate means
and the same predeclared timing/loss/association variants where supported. Do not seed
from the old 314 m answer or select any configuration by reference error.

This still conditions on published candidate discovery that used evaluation samples.
It measures repeatability of the conditional method and actual-error distribution,
not an untouched predictive frequency test. Keep the four-scan remainder out of the
headline sixteen-scan distribution. Report every group, including failures.

## B. Frozen-position frequency prediction

Use the sixteen time-spanning eligible indices in `holdout_protocol.json`. Preserve
the five original geographic hypotheses exactly. No new geographic optimization.
Search the full causal catalogue at these hypotheses, selecting identity, integer
timing and frequency offset from the existing randomized training mask only. Seal
training decisions before scoring complementary evaluation frequencies. Do not use
production-selected candidate IDs for this arm. Track construction/support is
conditioned upon; this is not an end-to-end raw-IQ discovery test.

Benchmark compute without tuning scientific settings. Process all sixteen frozen
sessions with bounded memory and parallelism. If additional fractional/robust variants
use training-selected top-K support, label that approximation and its limits; never
silently substitute it for the full-catalogue integer baseline. Test that arbitrary
changes to evaluation frequencies cannot change training selections.

Show all five held-out scores and paired whole-scan stability/uncertainty. A descriptive
best score does not authorize retraining or claiming a calibrated horizontal radius.
Keep candidate-count, propagation-failure, unmatched-track, and nuisance-bound counts.

## Reporting

Reference coordinates are used only after estimates are sealed. Compare median,
range, sub-kilometre success count and errors by group, not just the best answer.
Record source/cache/protocol hashes, runtime, tests and reproduction commands.
Publish completed report artifacts to main under existing user authorization, with
normal integration of concurrent commits. No radio collection or production deployment.
