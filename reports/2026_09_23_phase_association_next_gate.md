# Phase-assisted association next gate: labeled-corpus blocker

## Decision

Do not run another saved-IQ phase association replay on the current corpus. The
independently labeled comparison population was not found in the
audited artifacts listed below. Existing data can test common waveform support, conditional
catalog compatibility, or synthetic recovery, but cannot measure whether phase
improves real same-source versus different-source track joining.

This is a metadata-only audit. It opened no IQ, ran no optimizer, and collected
no RF. The failed 100 microsecond coefficient-phase replay is not the reason for
the stop: longer integrations already show useful conditional phase coherence.
The blocker is missing label authority and calibration.

## What is available

The random phase-link experiment has the right within-dwell validation mechanics:
seed 20260923, random whole 20 ms groups, held frequency-set prediction, retained
abstentions, and wrong-group controls. It reports support in 2/8 selected 2.5
MS/s dwells, 7/8 at 10 MS/s, and 6/8 at 15 MS/s. Its own artifact correctly
labels the result “capture-level common-waveform evidence only.” Every candidate
that asserts the same capture link receives the same phase weight. The
wrong-group permutation is a signal-control construction; a group from another
time is not independently known to contain a different emitter.

The long-track tables have many GLRT trajectories and conditional TLE names,
but those names are outcomes of the Doppler/catalog scorer, not truth labels.
The tracking synthesis explicitly claims zero secure NORAD identities. Even its
two strongest long arcs are described as conditional catalogue labels, and the
150802 common-orbit audit ultimately fails the identity gate. Using those labels
to judge a phase feature would make the GLRT baseline define its own truth.

The 150802 cross-receiver replay supplies strong local same-emitter evidence
through common frame timing and Doppler slope. It contributes one conditional
positive episode, not a population of labeled joins, and has no independently
labeled different-emitter counterpart. Splitting its correlated frames or bins
would not create independent whole-track labels.

The paired Qin injection corpus has known truth, but only three background pairs.
Its arms distinguish injected catalogue-orbit and radio-polynomial frequency
families; they do not define same-source and different-source track joins with a
dual-receiver phase transfer function. It can test implementation on synthetic
signals, not answer whether phase improves association in the observed sky.

## The executable test once labels exist

Build the population before inspecting phase: an initial engineering target is
twelve independently labeled join units, each a whole pair of nonoverlapping
track fragments. This is not a statistical sample-size guarantee; required
precision and class balance must determine the final population size. Positive
units must share a source identity established without the tested phase feature;
negative units must have independently established different identities. A
decoded transmitter identifier, controlled dual-source RF replay through both
receiver chains, or another external identity authority is sufficient. A TLE
winner, nearest-time match, shared capture, or wrong-time permutation is not.

Freeze a seeded random whole-unit outer split, keeping all receivers, fragments,
candidate aliases, and failures together. On outer training only, calibrate the
receiver/channel phase transfer and fit one fixed incremental phase score. On
outer held units compare the existing GLRT join score with GLRT plus phase using
the identical candidate pairs. Report a paired discrimination metric such as
held log loss and AUROC, plus coverage and every abstention. Require improvement
over GLRT alone without reduced labeled-unit coverage; do not select a threshold
or phase scale on held units.

For the present public corpus, this protocol cannot be instantiated truthfully:
there are insufficient independently labeled positives, zero independently
labeled real negative joins located by this audit, and no capture-bound
source-specific dual-receiver phase calibration. Synthetic injection is the
only immediately executable known-truth route, but it would qualify the method,
not provide the requested real association result.

## Scale interpretation

This blocker applies to the proposed supervised track-join accuracy test. It
does not prove that independently labeled satellite identities are necessary
for every positioning method. A latent-association position estimator could be
evaluated against surveyed receiver positions with independent recordings;
the prior phase-versus-GLRT position comparison did not establish improvement
([independent results](2026_09_23_independent_phase_v2_results.md)). Synthetic
replay also remains useful for method qualification, provided it is not reported
as an improvement on real recordings.

The 100 microsecond failure used only 218 guarded samples while fitting sixteen
local complex coefficients, so it does not prove that 1–20 ms estimates fail.
An optimistic independent-noise extrapolation scales its 1.30 rad error to
about 0.092 rad over 20 ms, but the retained artifact lacks pilot energy and
noise covariance needed to justify that scaling. Even 0.092 rad is roughly
45,000 times the audited 2.045 microradian curvature left after fitting local
phase and rate on the 8 cm baseline scenario.
The existing random phase results already demonstrate that longer coherent
windows can pass an internal waveform gate. That fact does not repair the label
gap. Nor does longer integration supply geometric association by itself: free
per-dwell phase and rate absorb the direction/rate observable, while the short
mechanical baseline makes post-nuisance orbital curvature much smaller than the
measured phase noise. The next useful work is label/calibration acquisition, not
another estimator iteration over the same unlabeled responses.

## Audited sources

- [Random phase association](2026_09_23_random_phase_association.md)
- [Source-seeded phase qualification](2026_09_23_source_seeded_phase.md)
- [Satellite identity recovery v2](2026_08_25_satellite_identity_recovery_v2.md)
- [Satellite tracking synthesis evidence](figures/2026_08_27_satellite_tracking_synthesis/satellite-tracking-synthesis-evidence.json)
- [Paired known-truth injection](2026_08_27_satellite_pnt_cross_family_injection_attempt2_results.md)
- [Differential-phase observability](2026_09_23_differential_phase_observability.md)
