# Frozen recording-disjoint RX predictive test

Four recordings were chosen from the frozen DS6 metadata by lowest
SHA256(`20260928:session_id`) after excluding every member of prior RX manifests
and initial roof calibration/evaluation membership. Eligibility requires completed
tracking and attested source span. Selection precedes loading their observations
for this experiment. These recordings are unused by this RX development effort,
not claimed universally unseen across other DS6 research. Do not replace failed
or unfavorable recordings; report unavailable/unsupported cases explicitly.

Use full-six frozen calibration for frequency Student-t parameters, feature
scalers, reception coefficients, and shared detection/ratio effects. Validate
that selected recordings are absent from all training/calibration memberships,
including receiver-pairing calibration. No refitting or parameter selection on
these four recordings. The reference is operator-supplied, not surveyed GPS.

For each recording, use the grouped-rebuild procedure: seed 20260927, 10-second
UTC blocks joined across raw-window overlap, receiver opportunities and physical
pairs; 50% X / 50% Y from the deterministic group hash. Require at least three
observations in each partition, reporting unsupported tracks. Independently
refit full-visible-catalogue shortlist and CFO on X and Y; rebuild directions
for the selected candidates. No old per-track fits or cross-prior sharing.

Frequency-only baseline is 50% training frequency posterior plus 50% uniform
over its own three-candidate shortlist. Primary RX posterior is 50% training
frequency-plus-RX posterior plus 50% the same uniform. Conditioning frequency
is counted once. Integrate the shared reception effects with accepted numerical
checks. Include reversed orientation and candidate-independent null. Hold one
candidate common across each held block. Score both reciprocal directions,
keeping their dependence explicit.

Report all per-recording gains, occupied-second-weighted and equal-recording
means, counts and exclusions. Do not tune mixture weight, grouping width, seed,
orientation, or eligibility using outcomes. Gate for a geographic follow-up:
normal RX must have positive pooled and equal-recording gain in both directions,
improve at least three of four recordings in each direction, and beat reversed
orientation in both pooled directions. This is a bounded progression criterion,
not a significance test or proof of physical ID correctness.

The final goal still requires measured improvement in geographic resolution.
Only if the predictive gate passes should this frozen model proceed to matched
location searches, preserving independent Sacramento/Reno candidates. No RF
collection, production changes, or broad reanalysis campaign is authorized.
