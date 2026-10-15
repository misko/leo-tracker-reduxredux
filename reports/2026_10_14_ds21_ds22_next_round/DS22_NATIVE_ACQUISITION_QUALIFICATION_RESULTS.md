# Detector-conditioned native model passes actual-data qualification

Both prespecified cases pass the acquisition-field and nested-model checks. This clears the implementation for the matched predictive experiment; it is **not a localization result**. No optimizer, position-reference comparison, original held-set evaluation or new RF collection was used.

| Case | Assigned observations | Training fold counts | Objective evaluations | Recorded elapsed seconds | Largest directional FD discrepancy |
|---|---:|---:|---:|---:|---:|
| DS22-109 | 2703 | 1512 / 1191 | 42 | 35.114 | 3.64e-7 |
| DS22-131 | 2911 | 1458 / 1453 | 42 | 39.916 | 3.72e-7 |

Every assigned selected margin is positive and matches the public native candidate with the same candidate identity, receive time, receiver, channel, RF and measured CFO. The margin is the selected candidate's recorded fractional exact-minus-control statistic, not a fitted responsibility or maximum over replacement alternatives. This is a conditional detector covariate, not a calibrated detection probability.

Whole 20-second blocks are deterministically split into two folds using seed 20261014. Each transform centers log margin and divides by its own training-fold population standard deviation. Those standard deviations are 0.380999/0.354761 for109 and 0.363948/0.422489 for131. The test fold does not set these parameters. Original discovery, candidate banks, frames and starting states were derived from full training data; subsequent prediction therefore remains conditional development evidence rather than untouched validation.

At both complete low-origin and high-origin states, beta zero reproduces the original full band model's objective, physical and old nuisance gradients, NLL, responsibilities, clutter probabilities and prediction gradients. Masked baseline/extension comparisons also nest in both folds. At beta0.2, actual finite differences check the beta coordinate, one deterministic physical-vector direction and one deterministic propensity direction. The table reports the maximum discrepancy over these checks; it does not claim an actual-data coordinate-by-coordinate audit. Component tests separately cover all coordinates on synthetic fixtures. The source batch passed13 tests and Ruff; an independent SOL review found no blocking normalization, prior or fold-isolation issue.

## Measured motivation and counterevidence

At zero beta, all eight case/origin/fold total beta gradients are positive. A negative beta would initially increase signal odds for higher-margin observations. The covariate therefore carries some information about the fitted signal/clutter distinction, but that does not prove correct satellite identities or improved positions.

The distinction is not consistent across every receiver/band. In131's lower band on RX0, the low-origin state's signal-weighted margin means are0.502/0.564 versus clutter-weighted0.490/0.457 across the two folds. The high-origin state instead has signal means0.470/0.548 versus clutter0.501/0.565. A common coefficient could favor one assignment pattern over another, but it could also reinforce a geographically worse solution. Neither an initial gradient nor a better acquisition-conditioned likelihood establishes localization accuracy.

The next experiment retains both source geographies and fits baseline versus one-coefficient models in both folds:16 fixed-position calls across two cases. Beta has the prespecified unit Gaussian prior and bounds±2, shared across receivers and bands. Existing calibration, timing and band-propensity priors remain once-counted. Each arm uses the same wrapper and budget. All outcomes must be sealed before opposite-fold scoring; direct density-substitution effects must be separated from parameter-fitting effects. Failed outcomes remain unavailable, and no new geographic accuracy curve follows from this fixed-position experiment alone.

## Source, cost and receipts

[Protocol](DS22_NATIVE_ACQUISITION_PROTOCOL.md), source `4518559cc`; [density component qualification](NATIVE_ACQUISITION_DENSITY_COMPONENT_RESULTS.md), source `649f83fe7`. The new wrapper predicts native orbits once per objective; the old band wrapper predicts twice. Both new comparison arms use the same one-prediction wrapper. Each band-density call performs baseline validation followed by the log-space modified density calculation. These costs are explicit rather than hidden extra fits.

The recorded internal elapsed times begin after the initial source guard. External135-second TERM/140-second KILL bounds were applied; the internal120-second check alone should not be described as proof of a whole-process120-second bound. Both processes terminated successfully with42 objectives and zero fits. Future fit runners must include source checks in their whole-process elapsed accounting.

Bulk namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-acquisition-qualified-v1`. Each case preserves `run/field.json`, `folds.json`, `result.json` and `termination.json`. Result SHA256:109 `15f26c40b49cca15c4802e4d8e82758ce8b091f7a1f9549df2bf161807ff9143`;131 `3227e57062e8d07adbdf84cfac4ef6c51a950af0d1fffd09ab65550e16d5ed27`. Original numerical states, reference coordinates and full-cohort metrics remain unchanged.
