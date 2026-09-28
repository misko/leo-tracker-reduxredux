# Fixed-position diagnosis: objective misranking and reception-driven identities

Completed the predeclared two-recording diagnostic in 71.9 and 72.1 seconds. All saved-position scores reproduced exactly (maximum absolute difference 0.0). Fifteen focused diagnostic/runner/attribution tests passed. Each position recomputed its own frequency shortlist; the independently evaluated roof reference supplied no candidates to either prior. No search, calibration, weight tuning, RF collection, or production change occurred.

The reference is an operator-supplied roof coordinate, not surveyed ground truth. This is outcome-selected diagnosis, not confirmation of improved resolution.

## The reference loses under the objective

Below is reference minus mixture-selected score. Positive means the estimator prefers its wrong location. Scores are occupied-second-weighted, per-reserve-observation negative log likelihoods, not kilometers or posterior odds.

| Recording | Prior | Doppler difference | Mixture joint difference |
|---|---|---:|---:|
| 53ce | Sacramento | +0.112577 | +0.086010 |
| 53ce | Reno | +0.111471 | +0.086224 |
| e76c | Sacramento | +0.038379 | +0.064726 |
| e76c | Reno | +0.040725 | +0.065199 |

The reference also loses against each D and mean-selected position under all three joint calibrations. Geometry partially offsets the Doppler preference against the reference on 53ce, but strengthens it on e76c. A search improvement alone cannot make this unchanged objective prefer the reference over these already-known alternatives. This does not exclude improvements elsewhere in the search domain.

## Association changes do not explain every regression

Compare the matched-mean selected point to the mixture-selected point, using the mixture objective at both:

| Recording | Tracks | Prior | Shortlist sets changed | Frequency MAP changed | Joint MAP changed |
|---|---:|---|---:|---:|---:|
| 53ce | 62 | Sacramento | 0 | 0 | 0 |
| 53ce | 62 | Reno | 0 | 0 | 0 |
| e76c | 59 | Sacramento | 3 | 2 | 3 |
| e76c | 59 | Reno | 3 | 2 | 3 |

Even when the MAP is stable between positions, reception can favor a different identity than frequency alone. On 53ce this happens for eight tracks at each position; on e76c, five. These are model associations, not verified satellite identities. Stable MAP does not imply unchanged posterior probabilities.

The three changing-joint-MAP tracks on e76c contribute -0.004806 (Sacramento) and -0.004655 (Reno) to the joint score change. Unchanged-MAP tracks contribute a further -0.002056 and -0.001652. Negative favors the farther, mixture-selected position. This is an additive accounting, not a counterfactual proof that identity changes caused that share of the regression.

## Which reception terms favor the bad shifts?

| Recording | Prior | Doppler change | Detection increment change | Conditional ratio increment change | Joint change |
|---|---|---:|---:|---:|---:|
| 53ce | Sacramento | +0.000639 | -0.001347 | -0.000918 | -0.001626 |
| 53ce | Reno | +0.001302 | -0.001675 | -0.000539 | -0.000912 |
| e76c | Sacramento | +0.007467 | -0.002883 | -0.011446 | -0.006862 |
| e76c | Reno | +0.004929 | -0.002102 | -0.009134 | -0.006307 |

These are telescoping shared-identity likelihood increments, not separately marginalized reception scores.

Largest reception drivers, identified by track-hash prefix:

- **53ce `4d3d82fb7ab8`**, 24 occupied seconds: frequency MAP 65450, joint MAP 66900 at both positions. Its reception increment changes by approximately -0.002280 (Sacramento) and -0.002269 (Reno). Track `fb3f2634abc1`, 26 seconds, similarly favors joint ID 66900 over frequency ID 60071.
- **e76c `e35267c64df2`**, 27 seconds: frequency MAP 45212, joint MAP 67497 at both positions. Its conditional ratio increment changes by -0.005663 (Sacramento) and -0.003961 (Reno).
- **e76c `479b1a278615`**, 26 seconds: also changes frequency-to-joint identity from 45212 to 67497, with substantial detection and ratio preferences for the bad shift.
- **e76c `89d50bcfc2cb`**, 16 seconds: joint MAP changes between positions from 61853 to 67182, with a ratio increment change of -0.002648 / -0.002728.

Thus a few short tracks with strong reception-induced identity preferences deserve inspection. This does not authorize dropping them, fixing identities to the reference, or choosing an outcome-tuned weight.

## Next scientific test

Inspect the detection/margin measurements, candidate posterior probabilities, and fitted antenna-response predictions on these identified tracks. In particular, determine whether repeated temporally correlated reception observations produce excessive identity certainty, or whether the response mean/variance is systematically wrong. Both remain hypotheses; the present diagnostics do not distinguish them.

A defensible next model would need calibration-only evidence for its uncertainty/correlation treatment, then independent location validation. The current results do not prove improved resolution and do not support promoting the mixture geometry model.

Artifacts: `mixture-track-diagnostic-scan-fw-53ce822d78d476ba.json`, `mixture-track-diagnostic-scan-fw-e76c229e9dc498b3.json`, and `mixture-track-attribution.json`. Reproduction: `score_mixture_track_diagnostic.py` validates frozen source/code bindings and reconstructs weighted score changes, refusing output overwrite.
