# Proposed next gate: transferable receiver alignment

The completed census supports within-pair frequency coherence but rejects
assuming a common constant offset for most donor-eligible pairs. Do not use
those pairs as verified satellite labels or launch a shared-trajectory geographic
fit on that assumption. The next step should distinguish mechanisms using
frequency data independently of a chosen geographic position or satellite bank.

Compare a per-channel constant with two constrained alternatives: a shared
linear drift in time, and a small relative receiver time shift. To first order,
a relative shift changes a frequency difference in proportion to frequency
slope. A relationship between the pair offsets and their training-estimated
slopes is therefore testable without selecting a satellite. It would be evidence
for an alignment model, not proof of a hardware clock error: estimator group
delay, drift and incorrect associations can mimic such a relationship.

Use the already-selected pairs; do not retune their matching or shape thresholds
to improve this result. Fit donor coefficients with all target-pair frequency
differences removed. Derive any target slope/time features from its training
observations only. Score the same target held RX0 observations conditional on
the corresponding RX1 observations, and preserve targets without adequate
donors or a well-conditioned design. Account for RF/channel-specific offsets;
do not assert shared hardware behavior across channels merely to increase data.

Before execution, freeze feature definitions, coefficient bounds, conditioning
and donor-count requirements, fit weighting, controls and complete populations.
Test known injected offsets/drift/time shift, target-pair exclusion, held
isolation and rank deficiency. Compare models on matched targets with explicit
coverage, residual distributions and conditional scores. This remains an
exploratory comparison on previously used datasets, not an independent
confirmation or a measured time-of-arrival experiment.

Only a transferable correction would justify a separately tested geographic
model. That later model must retain unmatched/incorrect-pair alternatives,
normalize assignments and avoid duplicate observations. It must reproduce the
independent-track model at zero coupling before testing any location change.
No new RF collection is needed for the proposed alignment diagnostic.
