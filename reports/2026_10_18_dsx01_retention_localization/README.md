# DSX01: retaining long tracks and evaluating independent position

Six model structures were evaluated across all five scans with paired c=0 and fitted-c runs. Every fitted position was saved before the supplied GPS entered this reporter. The new search used zero hardware initialization, raw-curved calibration only, and shared bounded geographic proposals. The historical standard pipeline is a recorded reference with different inference/search settings, not a matched rerun.

## Measured findings

The full 80-point S01 target can be retained without deleting its tail. Penalized subdivision associates two pieces to candidate 62811 at 138.5 Hz RMS; the correlated-noise model keeps one curve at 203.9 Hz native RMS and 120.2 Hz innovation RMS. Both retain the same independently fitted S01 location as the shared-phase baseline: 4.160 km error. They do not establish independent truth for the satellite identity.

Across DSX01, subdivision raises coverage from 63.33% to 65.34%. Correlated noise raises it to 81.21%, or 16,310 of 20,084 raw GLRT points. Its median scan error is 4.160 km, equal to the fitted-c baseline median, while its worst scan error is 13.332 km versus 9.963 km. More associated points do not consistently imply a better independent position.

Correlated noise gives the best simple five-scan consensus here at 1.508 km, but none of the independent scan estimates from any method/arm is within 500 m. The family-rate, orbital and receiver-smooth extensions increase coverage while worsening median scan accuracy relative to fitted-c shared phase. These bounded prototypes expose a remaining localization/parameter-identifiability problem; they do not solve it.

The c ablation is mixed. For correlated noise, c=0 yields 81.50% coverage versus 81.21% with fitted c, the same 4.160 km median and 1.508 km consensus, and a smaller worst error (10.484 versus 13.332 km). There is no consistent evidence here for enabling the RF-dependent c term merely to improve fit.

For conservative immediate retention, subdivision preserves the existing white-residual requirement within each piece, with the explicit limitation that the pieces can have different constants. Correlated noise is the strongest coverage prototype and warrants further shared-error diagnosis; it changes the requirement to white innovations, so native residual structure remains a modeled hypothesis. The next useful experiment is joint multiscan inference with shared physical error sources and explicit position/nuisance identifiability diagnostics, rather than selecting a model by in-sample coverage alone.

## Position error by scan

Values are kilometers; each cell is **c=0 / fitted c**.

| Approach | S01 | S02 | S03 | S04 | S05 |
| --- | --- | --- | --- | --- | --- |
| Shared phase | 4.160 / 4.160 | 11.842 / 9.963 | 2.931 / 3.119 | 4.792 / 3.597 | 9.189 / 9.189 |
| Satellite family rate | 5.688 / 5.499 | 11.715 / 14.880 | 3.384 / 3.384 | 5.899 / 5.921 | 14.115 / 14.888 |
| Orbital MAP / soft EM | 5.808 / 5.243 | 9.963 / 9.963 | 2.283 / 2.743 | 5.899 / 5.921 | 10.056 / 10.056 |
| Penalized subdivision | 4.160 / 4.160 | 11.842 / 9.963 | 2.743 / 2.931 | 5.162 / 3.597 | 10.176 / 10.176 |
| Correlated-noise likelihood | 4.160 / 4.160 | 10.484 / 13.332 | 2.283 / 2.283 | 2.938 / 2.938 | 7.169 / 7.169 |
| Receiver smooth error | 6.560 / 6.599 | 10.484 / 11.020 | 3.399 / 3.399 | 5.899 / 5.921 | 8.618 / 8.618 |

Historical recorded standard: S01 132.176 km, S02 133.790 km, S03 5.239 km, S04 258.655 km, S05 7.443 km.

## Coverage at the estimated position

| Approach / c arm | Associated GLRT | Associated % | Segments | GLRT / segment | Median position error, km | Worst error, km |
| --- | --- | --- | --- | --- | --- | --- |
| Shared phase / c0 | 12747 | 63.47 | 494 | 25.8 | 4.792 | 11.842 |
| Shared phase / fitted_c | 12719 | 63.33 | 492 | 25.9 | 4.160 | 9.963 |
| Satellite family rate / c0 | 13746 | 68.44 | 514 | 26.7 | 5.899 | 14.115 |
| Satellite family rate / fitted_c | 14034 | 69.88 | 513 | 27.4 | 5.921 | 14.888 |
| Orbital MAP / soft EM / c0 | 14377 | 71.58 | 527 | 27.3 | 5.899 | 10.056 |
| Orbital MAP / soft EM / fitted_c | 14286 | 71.13 | 523 | 27.3 | 5.921 | 10.056 |
| Penalized subdivision / c0 | 13185 | 65.65 | 507 | 26.0 | 5.162 | 11.842 |
| Penalized subdivision / fitted_c | 13122 | 65.34 | 506 | 25.9 | 4.160 | 10.176 |
| Correlated-noise likelihood / c0 | 16369 | 81.50 | 595 | 27.5 | 4.160 | 10.484 |
| Correlated-noise likelihood / fitted_c | 16310 | 81.21 | 587 | 27.8 | 4.160 | 13.332 |
| Receiver smooth error / c0 | 14592 | 72.65 | 531 | 27.5 | 6.560 | 10.484 |
| Receiver smooth error / fitted_c | 14621 | 72.80 | 533 | 27.4 | 6.599 | 11.020 |

![Position and coverage](position_and_coverage.png)

![Matched RF calibration ablation](c_ablation_and_accuracy.png)

## Per-scan coverage and track size

Each cell is **associated percentage / association segments / GLRT per segment**, fitted c. The full paired runs, parent counts and native/innovation RMS are in `per_scan.csv`.

| Approach | S01 | S02 | S03 | S04 | S05 |
| --- | --- | --- | --- | --- | --- |
| Shared phase | 63.6% / 126 / 24.2 | 61.0% / 82 / 26.2 | 74.1% / 111 / 26.6 | 66.6% / 88 / 28.1 | 51.5% / 85 / 24.6 |
| Satellite family rate | 74.0% / 135 / 26.3 | 65.5% / 82 / 28.1 | 79.8% / 117 / 27.2 | 70.5% / 88 / 29.8 | 58.5% / 91 / 26.1 |
| Orbital MAP / soft EM | 74.1% / 138 / 25.8 | 70.2% / 89 / 27.8 | 79.0% / 116 / 27.2 | 67.4% / 85 / 29.5 | 64.1% / 95 / 27.3 |
| Penalized subdivision | 65.2% / 128 / 24.4 | 61.0% / 82 / 26.2 | 77.5% / 117 / 26.4 | 66.6% / 88 / 28.1 | 56.1% / 91 / 25.0 |
| Correlated-noise likelihood | 85.6% / 152 / 27.0 | 70.4% / 84 / 29.5 | 86.8% / 127 / 27.3 | 82.5% / 104 / 29.5 | 78.8% / 120 / 26.6 |
| Receiver smooth error | 73.7% / 136 / 26.0 | 67.1% / 85 / 27.8 | 80.2% / 116 / 27.6 | 73.9% / 95 / 28.9 | 68.3% / 101 / 27.4 |

## Five-scan position fusion

A coordinate-wise median of the five independently fitted positions was saved before GPS evaluation. This is a simple robust position consensus, not a joint-likelihood refit, and the association counts above remain those at the independent scan positions.

| Approach | c=0 error, km | Fitted c error, km |
| --- | --- | --- |
| Shared phase | 2.657 | 2.619 |
| Satellite family rate | 3.384 | 2.583 |
| Orbital MAP / soft EM | 5.344 | 5.202 |
| Penalized subdivision | 2.619 | 2.619 |
| Correlated-noise likelihood | 1.508 | 1.508 |
| Receiver smooth error | 3.965 | 3.772 |

## Model definitions

- Shared phase: four RX/band offsets and small linear drifts, optional RF coefficient c, one phase per satellite, Gaussian whole-curve constants and strict raw-residual gates.
- Satellite family rate: one additional shared frequency rate per satellite, sigma 10 Hz/s and bound 20 Hz/s. Two accepted curved channels must own a correction.
- Orbital MAP / soft EM: shared phase plus two eccentricity-vector adjustments, sigma 1e-4 and component bounds 5e-4; whole-curve signal/clutter responsibilities drive MAP proposals. Each satellite prior is charged once. These are heuristic sensitivity priors, not calibrated orbit covariance.
- Penalized subdivision: at most two individually raw-curved pieces, each retaining all of its observations; Gaussian constants per piece plus 12+log(n) split cost. Pieces are counted separately and do not establish a continuous carrier identity across the boundary.
- Correlated noise: all points retained with white sigma 150 Hz plus an exponential-covariance component of sigma 150 Hz and correlation time 10 s. Covariance volume is included. Structure gates apply to whitened innovations; native residuals can remain correlated.
- Receiver smooth error: eleven smooth columns per receiver, projected off scan-wide constant/linear components, sigma 200 Hz. At least two curved satellite nominees must support a receiver. Four separate RX/band affine calibrations remain in the model.

The satellite-rate and orbital models are common-harness localization implementations of the earlier fixed-site approaches, not a reuse of their ground-truth-position labels or coefficients. Priors, initializer and optimizer budget are stated here because their results need not be numerically identical to the earlier fixed-site association experiments.
The overall selection objectives combine likelihood terms, explicit clutter costs, structure gates and complexity penalties. They are research composite scores, not normalized identity probabilities; position error is measured separately.

## Target capability versus blind outcome

The separate `target_frozen_state_prototypes.json` is explicitly a known-site diagnostic and was never used for geographic search. At that frozen state, the 80-point target fails the white model at 201 Hz RMS; penalized subdivision retains all 80 points as two pieces at 140 Hz combined RMS; the correlated-noise model retains the full curve with native RMS 202 Hz and approximately 120 Hz innovation RMS. Actual outcomes at each independently fitted S01 position are in `target_blind_outcomes.json`.

| Approach / c arm | Target points associated | Tested NORAD | Pieces | Native RMS, Hz | Innovation RMS, Hz |
| --- | --- | --- | --- | --- | --- |
| Shared phase / c0 | 0 | 62811 | 1 | 197.8 | 197.8 |
| Satellite family rate / c0 | 0 | 62811 | 1 | 151.6 | 151.6 |
| Orbital MAP / soft EM / c0 | 0 | 62811 | 1 | 154.5 | 154.5 |
| Penalized subdivision / c0 | 80 | 62811 | 2 | 138.4 | 138.4 |
| Correlated-noise likelihood / c0 | 80 | 62811 | 1 | 203.9 | 120.2 |
| Receiver smooth error / c0 | 0 | 62811 | 1 | 158.6 | 158.6 |
| Shared phase / fitted_c | 0 | 62811 | 1 | 197.8 | 197.8 |
| Satellite family rate / fitted_c | 0 | 62811 | 1 | 150.6 | 150.6 |
| Orbital MAP / soft EM / fitted_c | 0 | 62811 | 1 | 154.8 | 154.8 |
| Penalized subdivision / fitted_c | 80 | 62811 | 2 | 138.5 | 138.5 |
| Correlated-noise likelihood / fitted_c | 80 | 62811 | 1 | 203.9 | 120.2 |
| Receiver smooth error / fitted_c | 0 | 62811 | 1 | 160.2 | 160.2 |

![Target retention at a frozen state](target_retention_prototypes.png)

![Target residuals at independently estimated positions](target_blind_residuals.png)

## Controls and limitations

The raw denominator is 20,084 GLRT points. Points outside retained graph polynomials remain explicitly unassociated; no observation is silently deleted. Counts are polynomial fragments or association segments, not authenticated emitters or newly merged carrier tracks. Satellite identities have no independent ground truth here.

Changing every linear fragment's CFO by a large nonaffine perturbation left calibration parameters and scores exactly unchanged in all twelve model/c-arm combinations at the regional center (`linear_influence_control.json`). The prior inherited initializer was rejected because its older calibration used linear-sided pairs; its incomplete outputs remain explicitly superseded and never enter evaluation.

Causal TLEs reproduce every frozen scan bank exactly at checked epochs (`tle_parity.json`). No post-observation TLE enters these fits. Matched c-arm frequency effects on common associated points are reported separately in `c_ablation.csv`; a better score or RMS is not a position-accuracy claim.
Final orbital-model assignments were rechecked using actual perturbed SGP4 elements at their frozen fitted positions (`exact_orbit_validation.json`). The final coverage uses exact residuals and conservatively rejects any assignment that fails this check, followed by removal of assignments whose curved calibration support disappeared. The original tangent-based search endpoints and position estimates remain unchanged. No previously rejected assignment is promoted during this audit. All final accepted rows pass the exact frequency, visibility and residual-structure checks.
One assignment was removed by that audit: the 57-point S01 RX2 CH6 T000 under fitted-c orbital MAP. Its maximum residual difference was only 0.142 Hz, but its trend BIC gain crossed the limit of 10 to 10.0068. There were no support-cascade losses. This illustrates the sensitivity of binary gate counts near a boundary; the gate was kept fixed.

The geographic search is bounded and not proof of a global optimum. Regional discovery may use free constants and per-curve phases only to propose locations; final fits enforce their stated shared model. All observations are fitted, with no withheld points. Prototype choices were informed by the S01 diagnosis, so these five scans are an exploratory comparison rather than independent generalization evidence.

Each scan directory records the initial and refinement geographic candidates, scores, nuisance histories, final parameter states and protocol. The supplied GPS is confined to this post-fit reporting program. `evaluation_validation.json` binds all reported endpoints by SHA-256.

## Implementation and verification

The numerical component is `src/leo/analysis/research/retained_track_likelihood.py`; the common fitter is `tools/compare_dsx01_retention_localization.py`, with geographic continuation in `tools/refine_dsx01_retention_localization.py`. Source snapshots and hashes are recorded in `run_sources/` and `source_manifest.json`.

Nineteen focused scientific tests passed, including five component-owned tests covering native alias parity, Gaussian covariance whitening, affine-free smooth basis, exact Gaussian constant elimination and invalid repeated timestamps. Ruff checks passed for the new component, tests and comparison/report tools. The final accepted rows also pass the independent observation-binding, ownership and residual audits recorded in `evaluation_validation.json`.

To regenerate the evaluation and figures from sealed endpoints, run `tools/validate_dsx01_retention_orbits.py`, then `tools/fuse_dsx01_retention_positions.py`, then `tools/report_dsx01_retention_localization.py`, using the repository virtual environment with `PYTHONPATH=src:tools`. Search candidates and all endpoint states are persisted, so the numerical evaluations at those locations can be replayed without rerunning geographic discovery. Inference and reporting are research tools; no production pipeline or persisted public contract was changed.

## Methodological background and next prototypes

Penalized changepoint likelihood motivates the subdivision test; the current implementation exhaustively searches one break among three shortlisted satellites, rather than implementing PELT or claiming its complexity guarantees. A useful extension would connect pieces with a continuity prior and allow rate changes only when supported. [Killick, Fearnhead and Eckley, optimal changepoint detection](https://arxiv.org/abs/1101.1438).

The correlated-noise model uses a Gaussian covariance and includes its log determinant, so increasing model flexibility has a volume cost. The present fixed covariance is a hypothesis about frequency error, not evidence of its physical origin. A useful next test would share the correlated process across simultaneous channels and contrast receiver-shared versus satellite-shared error. [Rasmussen and Williams, Gaussian Processes for Machine Learning](https://gaussianprocess.org/gpml/chapters/).

Soft assignment followed by shared parameter updates is motivated by EM. Our finite proposals, structure gates and composite selection criterion do not establish classical EM monotonicity or posterior calibration. The next inference experiment should use one consistent joint signal/clutter likelihood with explicit identifiability checks on position, phase, receiver drift and orbit correction. [Dempster, Laird and Rubin, the EM algorithm](https://academic.oup.com/jrsssb/article/39/1/1/7027539).

A fourth unimplemented retention option is to retain a reliable prefix for orbital calibration while preserving the remaining points as an explicitly uncalibrated continuation. This would avoid discarding their existence without letting the problematic tail steer position. It must be reported separately from a full satellite association.
