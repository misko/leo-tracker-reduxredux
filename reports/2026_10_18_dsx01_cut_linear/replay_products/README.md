# DSX01: linear geometry with calibration from curved tracks

**The independent all-five sub-1 km goal remains open.** These prototypes add information from previously unused shorter or near-linear graph fragments. Calibration at every trial position uses the original curved observations only. Satellite identities remain hypotheses.

The baseline is the previous per-point-noise Gaussian-prior control. Three transfer variants use: (1) joint predictive covariance and a 1,000 Hz independent fragment offset; (2) a 1,000,000 Hz offset to nearly remove constant-frequency information; (3) only same RX/channel continuations within 10 seconds. Shared calibration uncertainty is integrated jointly across the new fragments. A factorized variational curved posterior is approximated as Gaussian for prediction; this is a modular research score, not an exactly marginalized joint posterior or calibrated probability.

Each search uses the 25 × 25 km Mill Valley box, 25 grid nodes plus the previous blind endpoint, three starts chosen by c0 and shared with fitted c, and at most 24 bounded iterations per start. Candidate labels, aliases and nominated fragments are frozen at the previous blind c0 endpoint. All original curved observations remain. Linear measurements retain their original CFO and 150 Hz noise; they were not GLRT-300 remeasured. No observations are withheld. Evaluation GPS is used only after nomination and search. The phase reference is frozen from the preceding blind three-round curved search.

Nominations require a curved-supported receiver/band, a satellite with two accepted curved RX/channel owners, positive elevation, signal/background log odds ≥ log(99), and a best/runner-up identity log margin ≥ log(10). These conditional selection rules are exploratory and are not identity probabilities. The familiar residual, RMS, offset, alias and ownership gates are evaluated separately below; nomination alone is not an accepted association.

**Iteration: `white_joint`** retains only nominees passing all original gates at the preceding blind c0 endpoint, including two accepted curved RX/channel owners. This subset is frozen before the grid search and is identical in both c arms. The white-gate audit at the new endpoint is still required; passing at one position does not imply passing at every trial position.
The `white_shape` control uses exactly the same strict subset, with the offset-insensitive shape model. This separates subset screening from changing the fragment-offset prior.

| Method | S01 | S02 | S03 | S04 | S05 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.527 / 0.512 | 1.044 / 1.041 | 1.571 / 1.629 | 0.426 / 0.428 | 1.887 / 1.869 |
| joint | 0.523 / 0.503 | 1.150 / 1.145 | 1.738 / 1.764 | 0.570 / 0.582 | 0.907 / 0.906 |
| shape | 0.478 / 0.464 | 1.204 / 1.202 | 1.672 / 1.730 | 0.743 / 0.765 | 0.862 / 0.860 |
| continuation | 0.506 / 0.489 | 1.123 / 1.133 | 1.591 / 1.647 | 0.392 / 0.358 | 1.843 / 1.826 |
| white_joint | 0.482 / 0.469 | 1.150 / 1.145 | 1.738 / 1.764 | 0.756 / 0.769 | 1.210 / 1.207 |
| white_shape | 0.459 / 0.445 | 1.204 / 1.202 | 1.672 / 1.730 | 0.750 / 0.775 | 1.216 / 1.212 |

Errors are km, **c0 / fitted c**.

![Position errors](position_errors.png)

The new evidence improves S05 but worsens S02 and S03. At the old S05 c0 endpoint, the joint predictive linear score favors evaluation GPS by 12.03 units, outweighing the 10.12-unit curved-score preference for the displaced endpoint. S03 linears instead reinforce displacement. Those GPS comparisons diagnose behavior; they do not choose nominations, parameters or winners.

The stricter `white_joint` rerun reduces S05's fitted-c error to about 1.207 km, compared with 0.906 km for the identical offset prior and broader nominees. That joint-model sub-1 km result does not survive the baseline residual-screen control. The table separately reports the matched shape control. S03's additional nominees pass the baseline gates yet reinforce its displaced position.
The matched `white_shape` control gives 1.212 km on S05, compared with 0.860 km before screening. Neither broad-nominee sub-1 km result survives this control. Both strict variants improve S05 over the previous 1.869 km baseline, but remain above the target.

![Individual linear-fragment score drivers](linear_marginal_drivers.png)

These individual marginal diagnostics retain shared-posterior uncertainty, but their scores cannot be added: the actual search preserves cross-fragment covariance. Gray marks nominees excluded by baseline residual/support gates.

| Fitted-c method | Nominated linear points | Linear points passing all gates | Curved points passing gates | Curved accepted RMS (Hz) | Linear accepted RMS (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0 | 0 | 10,825 | 130.75 | 0.00 |
| joint | 3,009 | 2,783 | 10,860 | 130.88 | 136.46 |
| shape | 3,009 | 2,783 | 10,860 | 130.88 | 136.45 |
| continuation | 161 | 146 | 10,825 | 130.75 | 166.48 |
| white_joint | 2,769 | 2,769 | 10,860 | 130.88 | 136.77 |
| white_shape | 2,769 | 2,769 | 10,860 | 130.87 | 136.77 |

Frequency fit and position accuracy are distinct results. Accepted populations can differ; RMS here is descriptive, not a matched-population gain claim. [Common-population c controls](c_ablation.csv) retain both arms' shared points.

[Evaluation table](evaluation_summary.csv), [frequency and residual gates](frequency_details.json), [input bindings](evaluation_bindings.json).

The separation between geometry evidence and reported calibration is motivated by [modular inference and cutting feedback](https://arxiv.org/abs/2211.03274). This implementation uses its own conditional-predictive approximation; the cited framework does not validate our satellite identities or uncertainty scales.
