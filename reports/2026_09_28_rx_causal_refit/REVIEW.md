# Independent review: causal-reference geometry refit

## Isolation and model contract

Each fold must physically construct its training document from the other five calibration
recordings' reception windows before raw feature extraction, within centering, reference
attachment, or causal-history construction. A mask applied after preparing the complete dataset
would be insufficient for this protocol. Histories start independently for every lane and receiver
and never cross recordings. The omitted recording alone may carry its causal history from reception
into held-frequency scoring.

The implementation reuses each original fold's training-only joint count model and feature scaler,
checking its membership, row count and hash. It then refits D/E/S/T beta, occupancy and persistence
with the same fitter, priors, bounds, null fallback and two starts. D's nested start is the fixed
neutral `[-2,0,0]`; later arms inherit only the preceding fit in the fixed nested ladder. No held or
evaluation outcome supplies a start, hyperparameter, centering value, background, or causal
predictor setting.

Omitted-record controls share exactly the same observational causal density. Their satellite
emissions and presence filters remain separate. A quarter-period control shifts only the satellite
forecast; swap/reversal change only the frozen geometry features. Every score is computed before
the current observation updates either causal frequency history or the presence state.

## Required source gates

Before launch, require exact six-fold input lists without duplicate overwrite, exact other-five
memberships, and the six-record/twelve-lane dataset population. Prepared training rows must export
the exact other-five reception source IDs and no held/evaluation IDs. The reception preparer does
not itself add source indices, but the intervening reference attachment does; the reviewed chain
therefore supplies the sequential indices required by causal attachment.

Checkpoint fingerprints must bind the experiment seal, all three input hashes, all imported
likelihood/preparation/fitting sources, settings, fold membership and held session. Resume must
reject any mismatch. Each completed fold must retain both optimizer starts, convergence receipts,
selected null status, training diagnostics and omitted-record per-window scores.

This is still reused development evidence. A causal training-only refit makes arm comparisons
fairer under the new reference, but it does not create an untouched confirmation cohort or prove
satellite identity, receiver direction, or position accuracy.

## Final source gate

The finalized source closes the duplicate-fold and population checks: it requires exactly six raw
rows in both input fold lists, six unique matching recording IDs, exact other-five memberships and
12 calibration lanes. Training documents are copied with only other-record reception windows before
feature preparation or causal attachment. Reference attachment supplies sequential source indices,
and every lane/receiver gets a fresh causal predictor.

The launcher verifies preceding evidence, hashes the dataset, original CV result, frozen causal
transfer, protocol, launcher, implementation and tests into one experiment seal, and requires a
fresh checkpoint directory. Each checkpoint additionally binds that seal, all input hashes, source
fingerprints, settings, held session and training membership. Ruff passes on the finalized source
and launcher. I find no remaining source-level blocker to the bounded fit after the focused
installed-environment tests pass.

## Outcome audit

The six-fold run completed with exit code 0 in 135.84 seconds and 263,184 KiB peak resident
memory. All 48 optimizer-start receipts report convergence; no arm selected the absent-model null.
Twenty-two of 24 selected arm/fold fits place persistence at the frozen 10-second upper bound, so
the fitted timescale remains boundary-constrained and should not be interpreted as a measured
physical persistence constant.

The independent audit verifies every fold's exact other-five reception source-window set before
reconstructing its causal training arrays. Across folds this covers 6,780 receiver-independent
training window memberships, with no held, omitted-record or evaluation source ID. It recomputes
each selected arm's calibration relative evidence through the forward likelihood, checks selection
against both optimizer receipts and the null, verifies omitted-record full/per-window arithmetic,
all equal-record means and signs, and exact equality of each of the six checkpoint payloads to its
published result fold. The audit passes and binds results digest
`bcb53dfc0ae1bde3330f072af825a026b305140a6b3fef4f7dca773d95f8ba06` plus every checkpoint digest.

A supplemental score audit closes two narrower gaps in that first audit. It independently sums
every exported window into role denominators and relative/reference/full totals for all 60
fold/evaluation cells. It reconstructs all 54 aggregate comparison rows from fold evaluations,
including refit-minus-frozen contrasts from the separately bound frozen result. It also recomputes
all 24 selected MAP penalties from the fixed beta, occupancy-logit and log-tau priors and verifies
`map_gain = calibration evidence - penalty`. The supplemental audit passes and is preserved as
`audit-scores.json`; both bound result hashes agree with the earlier receipts.

On held-frequency windows, refitted T is `+0.007308` nats/window relative to the causal reference
and positive in two of six records. T-minus-D is `+0.0222050537` with five positive records and one
negative (`39ac...` is `-0.0016167`); T-minus-S is `+0.0204116862`, also with five positive and one
negative. T exceeds swapped geometry by `+0.0268443485` and reversed geometry by `+0.0094293807`,
both positive in all six records. T-minus-quarter-period-shift is `+0.0209480544`, with four
positive and two negative records (`4c56...` and `c559...` are negative).

Refitting does not improve held full density over the preceding frozen-parameter transfer: refit T
minus frozen T is `-0.004775` nats/window, negative in all six records, and the analogous S change
is `-0.006121`, also negative in all six. Thus removing the reference mismatch leaves a small,
consistent within-panel T contrast but does not create broad positive association evidence against
the causal reference. The large predictive improvement remains attributable to generic causal
frequency continuity. These reused development records cannot establish identity or direction;
confirmation must use a metadata-selected recording cohort that did not shape this model sequence.
