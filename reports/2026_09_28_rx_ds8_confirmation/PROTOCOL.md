# Fixed DS8 receiver-geometry assessment

## Membership and scope

Use exactly the four recordings in the sealed
`../2026_09_28_rx_causal_refit/ds8-readiness.json`: earliest DS8 capture at each
of 2.5, 5, 7.5 and 10 Msps. Preserve membership regardless of qualification or
association outcomes; report exclusions and failures rather than replacing rows.
The panel is disjoint from the current 14-record geometry study. Earlier metadata
and rate-validation exposure is disclosed in the readiness receipt; it is not
claimed historically untouched.

Load only existing persisted public TrackingInput and capture/pose contracts.
Validate qualification, sealed input and analysis hashes, rate, complete visits,
unique probes and paired receiver identity/timing. Write exclusive local caches and
an evaluation-only inventory with pose/snapshot authority. No IQ read, detector run,
RF collection or QNAP modification is authorized by this execution plan.

## Model freeze

Before inspecting DS8 association outcomes, fit two full-calibration families on
the original six calibration recordings' reception windows only. Physically remove
all held/evaluation windows before preparation. Fit one shared joint count model
and feature scaler using those training windows. Keep sigma 500 Hz, existing within
geometry centering, nomination priors, coefficient priors, two-start optimizer,
parameter bounds, and all causal-frequency defaults unchanged.

Fit D/E/S/T under (a) the uniform phase reference and (b) the causal phase reference.
Use the existing fitter and neutral D seed [-2,0,0]. Freeze both families and their
receipts; do not select one using either the reused later windows or DS8 outcomes.
DS8 is not an input to the fitting tool.

## Recording-specific nominees and scoring

Use the existing causal-prefix pipeline unchanged: metadata-based overlap-connected
60/20/20 train/reception/held partition with embargo, training-only alias/RX mapping,
whole-catalogue prefix candidate ranking and top-three candidates per retained
prefix track. Bind exact analysis/input hashes and the persisted snapshot authority.
Use each recording's own existing snapshot if available; do not silently substitute
an unrelated snapshot. Freeze any necessary integration correction before scoring.

Keep every eligible receiver opportunity, including empty candidate sets. Apply the
existing exact-lane eligibility criteria and report all exclusions. Nomination and
CFO fitting may use the recording's training prefix only. Geometry model parameters
and causal-predictor defaults may not use any DS8 observation.

Score both model families against the same causal frequency reference, with D/E/S/T,
T receiver-swap and geometry-reversal controls, and quarter-period-shifted frequency
controls. The causal frequency reference itself uses past observations only and
does not reset at the reception/held boundary. Report uniform-reference comparison
for attribution of frequency-continuity gains. Primary results are equal-record
later-period scores; report each recording and denominator, not only means.

Retain the distinction between target presence and satellite identity. Positive
geometry contrasts alone do not establish direction, physical identity or sub-km
position accuracy. Report both families without post-outcome model selection.

## Bounded execution

Freeze source/input/protocol hashes per stage. Cache packaging is bounded to 120
seconds; full-calibration fitting to 180 seconds; each existing derived-data pipeline
stage to 180 seconds, one numerical thread and 4 GiB. Preserve failed and incomplete
receipts; do not silently retry with changed settings. No multi-hour campaign.
Run component tests and independent provenance/isolation/score audits. If a required
persisted authority is unavailable, document that exact prerequisite and continue
independent preparation rather than inventing provenance.
