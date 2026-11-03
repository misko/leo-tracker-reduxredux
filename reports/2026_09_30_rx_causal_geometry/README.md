# Geometry corrections fail above a causal receiver baseline

Adding nominal geometry to a predictor of changing receiver occupancy worsens later prediction. All 18 numerical fits qualify, but the predeclared direction gate fails. Do not advance this formulation to a new confirmation panel or location fit.

| Comparison | Equal-record later gain, nats/window | Positive recordings |
|---|---:|---:|
| Constant reception corrections P − causal baseline | +0.006757 | 4/6 |
| Unsigned geometry U − causal baseline | −0.199394 | 2/6 |
| Signed geometry O − causal baseline | −0.254024 | 2/6 |
| O − U | −0.054631 | 1/6 |
| O − P | −0.260782 | 2/6 |
| O − receiver-sign swap | −0.049969 | 3/6 |
| O − signed trajectory reversal | −0.004450 | 3/6 |
| O − candidate permutation | −0.018754 | 2/6 |

The P/U/O labels denote the new corrections in this experiment, not the parameterizations of the older HMM models. The small P gain supports modest calibration of the causal baseline in this development sample; it does not establish geographic accuracy or justify selecting parameters from reference distance.

## Model and evaluation

The [protocol](PROTOCOL.md) was written before execution. The [causal response predictor](../2026_09_30_rx_causal_response/README.md) supplies normalized category probabilities before every observation. Its training-selected decay times and shrinkage remain fixed. A multinomial correction adds common-reception and receiver-imbalance intercepts (P), then unsigned geometry (U), then a nonnegative signed geometry coefficient (O). All coefficients are fitted on the other five recordings' reception windows only, with fixed Gaussian priors and bounds.

Nominee geometry is averaged with original candidate prior mass and visibility, retaining omitted mass as zero contribution rather than renormalizing it away. No current or later detection updates these candidate weights. This differs from the earlier latent-identity HMM and may lose useful mixture structure; a negative result rejects this formulation, not every geometry-aware model. Signed controls preserve unsigned features and causal probabilities. They are feature controls, not complete alternative orbital trajectories.

Each omitted record is evaluated on its original later windows, using actual prior reception outcomes to update the causal baseline. Scores refer to receiver categories, even though the saved role is named `held_frequency`. No frequency residual or location measurement is evaluated. All six previously explored calibration recordings remain in every aggregate; this is reused development evidence.

## Verification and decision

[core.py](core.py) implements normalized log probabilities and analytic objective gradients. Three tests pass: finite-difference gradient agreement, exact baseline recovery with zero corrections, and unsigned-feature preservation under signed controls. All 18 fits report optimizer success and projected gradients below 1e-4. [run.py](run.py) reproduces each original causal later score within 1e-10 before comparisons. [results.json](results.json) retains coefficients, qualification receipts, all per-record contrasts and source hashes. The bounded run finishes in under a second with one BLAS thread and a 120-second cap.

The recent static-calibration, persistence and causal-control tests now reject several simple explanations for the geometry failures. Stop extending these nominal mean-feature response models without new evidence. The remaining geometry work needs independently supported pointing/RX mapping, better candidate identity, or a materially different physical observation model, followed by a held frequency test that avoids counting detection evidence twice. No new geographic improvement is established.

No RF collection, IQ processing, production change or remote publication occurred.
