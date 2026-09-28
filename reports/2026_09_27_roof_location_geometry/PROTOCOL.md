# Independent-prior roof location experiment

Goal: determine whether adding RX geometry reduces geographic distance error, not merely reception loss or nominal grid spacing. Prior conversational explanation alone was no progress toward that goal; this experiment performs actual independent location searches.

## Frozen inputs

Use the four held-out scans already fixed in `../2026_09_27_roof_direction_subset/evaluation_manifest.json`: 00ff81…, 898b70…, 3ebf35…, 851486…. Do not select scans by the new geographic result. Public tracking caches are digest-verified; the causal on-disk TLE catalogue is selected through the public input-preparation API.

Reuse exactly the six-scan reception calibration from the preceding experiment. Verify fitted coefficients against its saved result. Estimate the conditional log-margin-ratio variance using those calibration observations only, with equal total calibration weight per track. Strip all held-out truth-derived direction and satellite-ID fields from reception observations before search. The search API receives no ground-truth position. Ground truth is read only by a separate error-scoring step after search output is finalized.

## Geographic search

Sacramento origin 38.5816,-121.4944, radius250km; Reno origin39.5296,-119.8138, radius500km. Preserve these independently defined regional priors. Each point independently considers the full eligible causal satellite catalogue; no truth/Sacramento/Reno fitted candidate unions or coordinate sharing. Immutable full-catalogue orbital propagation may be reused because it contains no fitted branch information.

Both primary arms use identical best-first search settings: 1,000km box, grid levels100/50/25/12.5/6.25/3.125/1.5625km, initial budget160 points per arm. This is a bounded research search, not the deployed 400-point/12.5km search. Select the global best evaluated objective, report frontier/budget incompleteness, and preserve traces. A finer grid alone is not evidence that geometry helps. Within each prior, also rescore the union of both arms' evaluated coordinates to separate objective effects from unequal search coverage. Never combine coordinates between priors.

## Matched objective comparison

At each point/track: zero timing shift, fit constant CFO on the fixed Doppler-training mask, retain training-only top3 satellite hypotheses at100Hz Gaussian scale. No reception or reserved-frequency residual chooses candidates. Frequency score D is the mean reserved-observation Gaussian-mixture NLL, including normalization. This deliberately matches the zero-time direction calibration and is not claimed to implement full TLE timing uncertainty yet.

Geometry uses the calibrated Bernoulli likelihood of a compatible counterpart plus the conditional Gaussian likelihood of log(RX1/RX0 GLRT margin) for matched observations. Nondetections contribute zero to the conditional ratio term; normalization is over all reception observations. Candidate direction is the training-Doppler-weighted east component, recomputed at each searched location. Both likelihood coefficients are fixed at1, without geographic tuning. These terms form a composite observational model, not an assertion of complete independence from upstream detection/track selection.

Primary arms: D versus D+geometry. Track scores have common linear occupied-second-bin weights. Report D+detection and reversed-mapping scores on the same-prior common inventory as diagnostic ablations, not independent full searches. No RMS cap, truth-guided shortlist, fitted test mapping, or test-tuned likelihood weight.

## Evidence required

For all four scans and both priors: selected coordinates, distance to metadata truth, delta against the matched Doppler-only search, boundary/budget status, and common-inventory ablation. Published production estimates are contextual baselines only because they use a different capped, evaluation-selected identity objective and coarser search.

Improvement remains unproven until these geographic results exist. If the outcome fails or is inconsistent, retain that result and continue investigating; do not change the definition of success to improved reception prediction. Do not claim general population accuracy from four nearby scans, or survey-level resolution from operator-supplied coordinates/provisional RX orientation. No new RF collection or production/source-data modification.
