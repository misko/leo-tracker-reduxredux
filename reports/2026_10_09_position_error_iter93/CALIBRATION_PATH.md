# Confirmed region loss and bounded prefit diagnostic

The lowest-score ordinary retained baseline region, `point:-47.5:-62.5`, was
sampled at5km spacing and then lost at calibration in all three B7 regional
separation passes. Its stored coarse score is40696.314623, ahead of the next
retained scores41191.083007 and41589.307191. Selection of this diagnostic region
uses that ordinary score and the calibration failure, not its reference error.

Its shared coarse receipt reports solver success but independent stationarity
0.001535439, above the unchanged0.001 acceptance threshold. It used167 evaluations
in0.438seconds and was not qualified. The standard calibration path retries a
nonconverged coarse state once with the legacy fixed-position fitter, allowing
20seconds/600iterations, then raises `V16 calibration prefit did not converge`
if it remains unqualified. Only that exception was saved for the calibration
retry; its returned/terminal vector and precise failure reason were not retained.
The original retry's exact numerical outcome therefore remains unproven until
the frozen replay, and replay equivalence itself must be checked rather than
assumed.

The existing [bounded recovery policy](../../src/leo/application/hard60_recovery.py)
collects failed points only at the initial40km spacing. Calibration recovery is
then attempted only for retained keys in that collected set. The5km failed
retained point cannot enter this recovery path. This is a specific coverage gap
in recovery eligibility, not evidence that relaxing the stationarity threshold
or simply increasing time would fix the scan.

The final published B7 estimate instead comes from the sep50 pass. Both c arms
qualified through every joint stage, and their final gradients are comfortably
below threshold. This rules out a final-stage timeout or failed convergence as
the recorded mechanism. It does not prove that restoring the omitted region
will improve model-selected localization.

## Verified evidence

[verified-checkpoints.json](verified-checkpoints.json) preserves the shared coarse
receipt and three calibration failures. Extraction used only the public
`RegionalCheckpointStore.get` port, which verifies binding, key, value digest and
canonical encoding. The extraction command and source/publication hashes are
recorded. No production checkpoint was mutated and no fit ran during extraction.

## Four-fit diagnostic before any larger replay

Freeze source, native kernel, input bindings and checkpoint receipts. Rebuild the
same ordinary observation set, causal TLE bank and hypothesis prior, checking
digests, satellite order and the stored coarse objective within1e-6 first.

Compare the legacy and existing bounded-timing fitters from the same saved coarse
vector, then from that vector with timing terms set to zero. All four attempts
hold the same sampled position fixed, use the same bank/observations/priors,
hard±60Hz/s affine slope bounds and20second/600iteration allowance. Production
calibration prefit is fitted-c/shared; this first diagnostic reproduces that
scope rather than falsely labeling it a full c ablation. There is no90second
variant or threshold relaxation.

Persist each attempt's fit, optimizer receipt and returned/terminal gradient
audit. The latter identifies the largest scaled projected-gradient coordinate
and checks its raw derivative with feasible finite differences at three small
steps; raw and active-constraint-projected derivatives are explicitly distinct.
All attempts are append-only. Failures stay visible.

Stop after these four prefits. If calibration recovery is supported, separately
freeze a downstream association/final replay with matched c0/fitted-c observations,
candidate banks, priors and budgets, retaining the original ordinary candidates
and selecting only by qualified comparable model score. Until that evaluation,
no rescued position or accuracy improvement is claimed. Known coordinates remain
evaluation-only throughout, and production B7 remains unchanged.
