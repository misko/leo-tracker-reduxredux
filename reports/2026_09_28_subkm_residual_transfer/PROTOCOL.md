# Full88 fixed-prediction streaming diagnostic

Purpose: select the next localization model from predictive residual evidence,
not from reference-coordinate error. The old full88 audit failed when an
independent estimate hit a boundary. This is a new diagnostic with different
qualification handling, not a replacement or retry of that sealed attempt.

Use the original sealed full88 joint request/response and independent-response
index in exact order. Verify all 264 input artifact hashes and every response
seal. Load one recording bank at a time. Do not refit geographic position,
timing, candidate bank, held masks or scientific hyperparameters. Reuse the
original training-only per-track offset/profile and Student-t predictive audit.

Report the joint model on all 88 recordings. Compare with independent estimates
only when their original status is qualified. Retain every unqualified record
with its joint diagnostics, original flags and explicit null comparison; do not
call the 87-record paired subset an all88 independent result. No new geographic
score or accuracy claim is produced. The original model's inherited DS6 prior
remains a limitation even though reference coordinates are not read for this audit.

Predeclared summaries: training/held scores, observation-weighted RMS, per-record
joint-minus-independent held density, eleven chronological eight-record groups,
and receiver/channel residual slopes fitted separately on train and held for
diagnosis only. Any drift correction remains a future training-only shadow model;
these descriptive slopes may not be fitted to held data and then called prediction.

Bound the full diagnostic to 300 seconds, 4 GiB, one numerical thread and nice19.
Persist each completed recording before proceeding. Preserve partial output on
failure and do not silently restart. No new RF, IQ processing, propagation or
QNAP mutation. Component tests must verify full denominator retention, explicit
boundary qualification and streaming one-bank loading.

DS8/DS9 extension requires independently bound observation/bank exports with the
same frequency conventions and masks. Their capture/analysis completeness alone
does not establish baseline-model readiness or sub-kilometer position performance.
