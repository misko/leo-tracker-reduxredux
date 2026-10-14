# B053/B059 sealed failure diagnosis

This training-only diagnostic uses current coverage cached-v2 parents for DS21-053 and DS21-059. It freezes original source/input/cache/initialization/call authority and the new adapter before preparation. Original runners, candidates, observations, frames, likelihood, priors and fitted-c states remain unchanged. No reference or held data is read and no optimizer runs.

Each case replays all/low/high selected winners through the existing physical fusion audit (three objective calls), then decomposes the unchanged all-band likelihood at all six full endpoints, including rejected endpoints (six objective calls). The pair therefore requires exactly 18 objective calls and zero fits. The pair has an internal 120-second bound including authority checks and preparation, external TERM at 135 seconds and KILL at 140 seconds, one worker, and an exclusive launch claim with no retry.

The fusion component evaluates each frozen calibration function at the exact same timestamps/RFs in its original frame. Its orbital block includes geography and common/relative satellite timing. Hybrid scores diagnose coupled predictions, are not calibrated-model evidence, and do not claim feasible transferred calibration states. Priors are separate. Component calibration differences are gauge-dependent; total correction differences are physical. Band window counts accompany summed likelihoods.

The adapter records every original full endpoint's proposal/disk, stationarity, objective/NLL/prior gaps to the training-selected winner, fitted c, timing and calibration summaries. A better frequency fit is not evidence of better position accuracy. No coefficient copying, candidate reselection, reference seed, new drift parameter or prior relaxation occurs.

Run `tools/ds21_model_b_later_failure_audit_v2.py freeze --parents <coverage-053-cached-v2> <coverage-059-cached-v2> --output <fresh-bulk-directory>`, followed by `timeout --signal=TERM --kill-after=5s 135s` around the same module's `run --output <directory>` under the pinned research environment. Source freezing is metadata work, not zero preparation cost. Completed receipts and exact source bindings must be inspected before proposing any fit experiment.

The initial v1 source freeze was never launched: review found the assignment-comparison helper absent from its source closure. Its files remain unchanged. V2 binds that helper explicitly before any preparation and uses a fresh namespace; equations and the 18-objective policy are unchanged.
