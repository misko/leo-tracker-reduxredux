# Roof dual-receiver geometry experiments

Frozen design, 2026-09-27 01:01:48 UTC. User requested design and SOL evaluation on existing recent roof recordings. No acquisition or production changes are part of this experiment.

## Question and evidence limits

Does relative reception across the two tilted receivers carry useful arrival-direction information beyond receiver/channel sensitivity differences, and can that information improve candidate discrimination or geographic accuracy?

Use the capture-linked pose companions and verify their source manifest, authority, and binding digests. The current authority is operator-supplied WGS84 roof position, not a verified GPS survey/receiver fix; elevation, RF phase centers and world tilt are unknown, and software-to-physical receiver mapping is provisional. Nominal tilt is 10 degrees outward per receiver, giving a nominal 20-degree separation. Do not equate that separation with beamwidth or infer a measured world-frame phase-center baseline.

The absolute roof position may label calibration scans and score holdout error. It must not define holdout search candidates, center/radius, shortlist, scoring hyperparameters, selection of promising scans, or satellite candidate sharing between geographic priors. Relative geometry is permissible model input. Ground-truth association fits are diagnostic hypotheses, not decoded satellite IDs.

## Frozen corpus

Select at most the newest 12 pose-bound completed recordings at cutoff 01:01:48 UTC, independent of detection quality. There are eight companion files at design time:

1. scan-fw-2e6b78f0cd0cbbbc
2. scan-fw-3221795d82a1c7ec
3. scan-fw-195bdbb87ad09b7f
4. scan-fw-60d9d1e77c14da0a
5. scan-fw-cd6a029d633dcc0e
6. scan-fw-c78fb2dba2465361
7. scan-fw-c7e37f65ae9e08b0
8. scan-fw-5eaaa2a8f8c995b3

Verify capture order and completeness from the store, not filenames or modification time. First five are calibration; final three are holdout. The previously studied 00:00 scan stays in calibration. Exclusions require integrity/readiness reasons recorded before scoring, with no outcome-based replacement. New arrivals after cutoff are reserved for a later test. Preserve invalid/unavailable cases in accounting.

Pre-scoring metadata audit identified an existing hardware confound: `reports/2026_09_26_rx0_floor/README.md` documents RX0 near-floor input at 23:30, and `repair-verification.md` verifies recovered raw input at 00:00 and 00:05 after coax repair. Keep all eight in inventory and full descriptive results; label the first three as pre-recovery/uncertain unless contemporaneous evidence establishes otherwise. Add a predeclared calibration sensitivity using only the two verified recovered calibration scans, with the same latest-three holdout. Do not interpret a hardware-state transition as beam information. Two recovered calibration scans may be insufficient to identify a beam response, which is an acceptable failed gate.

## Experiment 1: observation opportunity and signal matching

Build a table of genuinely simultaneous dual-RX observations on matching RF channels, edges, and valid sample intervals. Record both-observed/both-detected, RX0-only, RX1-only, neither, missing analysis and clipped/invalid cases separately. Unobserved or invalid data are not nondetections.

Matching must use timing/pilot identity evidence, with frequency consistency allowing receiver bias. Do not pair each receiver's strongest peak by default or pair by an assumed geographic solution. Record ambiguity/multiple possible matches and compare pair rates to deliberate mismatches. Establish thresholds using calibration only, or fixed acquisition tolerances justified before inspecting holdout outcomes. Persist every tolerance and its provenance.

A common pilot pattern or a single coincident epoch is not a satellite identifier. Where available, require consistency of epoch evolution and receiver-offset-corrected frequency trajectory across repeated observations. A one-probe match remains a tentative common-signal match until these controls pass. Compare consecutive detection-conditioned strengths cautiously: two independently maximized peak scores have winner-selection bias. A future power replay should evaluate both receivers at matched signal hypotheses, including the weaker receiver below its discovery threshold.

Extract per-receiver noise/SNR or matched pilot power if available. GLRT exact/control/margin outputs may be used in a clearly labelled proxy experiment, never called calibrated power or interpreted as dB antenna gain. Distinguish measured timing resolution from matching tolerances and calibration-derived tuning.

## Experiment 2: receiver bias and repeatability

Fit a receiver/channel intercept-only baseline on calibration scans for relative reception and detection probability. Evaluate on holdout without refitting. Check whether relative reception persists across consecutive matched observations and whether it survives excluding saturation, strong asymmetry in noise floor, and ambiguous matches.

Controls: within-channel time-shifted/mismatched pairs, receiver-label swap, and channel-preserving time shuffle with fixed random seed 20260927. Use scan or contiguous time blocks for uncertainty; do not treat all frames as independent. A proxy association or stable hardware gain difference is not directional evidence.

## Experiment 3: incremental directional evidence

Only if paired observations and direction hypotheses are available, compare calibration-fitted models:

- M0: receiver/channel sensitivity only.
- M1: M0 plus signed east/west component of candidate arrival direction, marginalized over uncertain satellite identity.
- M2: nominal opposing tilted-axis response, with calibration-fitted common response width/gain and bounded orientation uncertainty. Without identifiable beamwidth/elevation, report M2 unavailable rather than inventing them.

Prefer the smallest M1 that tests the hypothesis before M2. Fit association hypotheses using frequency/timing observations, not the power outcome being predicted. Use separate calibration folds or explicit cross-fitting when fitting directions and response on the same scans. Require holdout predictive improvement over M0 and controls. Report reversed-mapping sensitivity; do not select physical mapping from holdout GPS wins. Keep RF power and detection likelihoods separate to avoid counting the same evidence twice.

For missing reception, condition on the receiver actually observing the signal's channel/time and its measured detection threshold; use a censored likelihood where supported. Strong dual detection indicates overlapping coverage, not necessarily zenith.

## Experiment 4: position consequence (gated)

If Experiment 3 demonstrates identifiable directional information, freeze its parameters and compare Doppler-only versus Doppler-plus-reception at independent Sacramento- and Reno-derived candidates. Each geographic branch generates its own satellite candidates; no union of truth/other-branch candidates. Ground truth is scored afterward. Candidate-position ranking is not a geographic accuracy result. A geographic claim requires independently rerunning the location search and measuring error against the roof coordinate.

Report all holdout cases, score deltas, receiver/scan consistency, and uncertainty. Three holdout scans support a feasibility result, not a calibrated population accuracy claim. If a gate fails, explain the missing observable and report results of completed stages instead of manufacturing a geometry score.

## Deliverables

Inventory with source and pose digest verification; matched opportunity/pair tables and pairing protocol; frozen calibration parameters; holdout and null-control metrics; explicit missing-data and failed-gate accounting; a SOL-authored report with numerical evidence. Use bounded re-analysis of existing recordings. Any IQ replay must have a declared small subset and computational budget, and no new capture is authorized. Tests should cover scientific invariants such as missing-versus-nondetection and truth/holdout exclusion from fitting.
