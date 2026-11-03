# DSX01: continuous localization from a Mill Valley grid

Three localization variants were tested on all six current graph-based physical models across all five scans: **180 independent fits**, including matched `c=0` and fitted-`c` arms. Subsequent support/prior ablations and joint-site fits investigate why several estimates remain displaced.

The strongest simple combined-site result is the arithmetic mean of the five continuous smooth-receiver estimates: **670 m with `c=0`; 680 m with fitted `c`**. This meets the numerical 1 km target for this exploratory five-scan combination. It does **not** establish reliable sub-1 km localization on individual scans: their errors remain 1.24–3.86 km for this model. Removing one scan from the arithmetic combination produces errors up to 1.33 km. The broader goal therefore remains open.

The preceding [known-position loss-surface report](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_18_s01_local_loss/README.md) was published separately at commit `00915da6e43ad6d95e06864ae156ff846b6a0d4b`. Its GPS-derived calibration states never initialize these new fits.

## Search and data controls

The predeclared regional centre is **37.906, −122.545**, a rounded Mill Valley town centre. A **25 × 25 km square** spans east/north offsets of ±12.5 km. Each variant evaluates the same 5 × 5 grid, with 6.25 km spacing. Three starts are chosen using only the `c=0` grid scores and reused by both `c` arms. Each receives at most 24 damped joint Gauss–Newton iterations with bounded parameters. Grid scores initially hold the centre nuisance fit fixed; continuous refinement then jointly adjusts position and nuisance terms. This is bounded multistart search, not a global-optimum proof.

The supplied evaluation GPS, **37.849061591561885, −122.48574968092912**, enters separate reporting/oracle-audit programs after endpoints are saved. There is no Gaussian attraction to GPS in the search. Algorithm design and exploratory comparisons are informed by this dataset and its evaluation; these results are not independent generalization evidence.

All methods reuse the existing radio-only graph partition and frozen, most-recent-causal TLE banks. No post-observation TLE enters inference. Only individually measured curved fragments calibrate or rank location; linear fragments can receive postfit associations. S01 has 4,797 raw GLRT observations, of which 4,486 lie in 170 retained polynomial fragments; the actively curved subset comprises 81 fragments. Across all five scans the denominator remains **20,084 raw GLRT observations**. No observations are withheld or silently removed from that denominator.

At Mill Valley centre, the existing curved-only fitter runs eight nuisance proposal rounds with zero hardware initialization. One candidate nomination and alias integer per curved fragment are then fixed from its `c=0` result, identically for both `c` arms. Every raw-curved fragment remains in the initial three variants' objective. Candidate identities are hypotheses, not verified emitters.

The six model columns retain their existing mechanisms: shared satellite phase; satellite frequency rate; orbital eccentricity-vector correction; penalized subdivision; correlated residual noise; and receiver-shared smooth frequency error. The orbital column uses its original EM-like centre initializer, followed by fixed-nomination continuous fitting; the continuous refinement itself is not an EM algorithm. Orbital corrections use tangent state sensitivities, not an exact repropagation audit of every new association.

## The three initial solutions

| Localization variant | Change and purpose |
| --- | --- |
| Continuous frequency fit | Jointly fit location, receiver/band offsets and drifts, satellite phase and the model's additional terms. Profile Gaussian curve constants, then use a smooth whole-curve `log(1 + energy)` cost. Remove binary residual-acceptance gates from geographic optimization. |
| Shape only | Project each curved fragment off an unpenalized constant and linear term before fitting position and satellite terms. Test whether radio affine calibration causes the displacement. Hardware is held at its centre initialization during this discovery fit. |
| Family balanced | Use the continuous objective but divide each fragment's weight by the number of curved nominations in its satellite family. Test domination by heavily represented families. |

Continuous fitting includes phase/drift/additional-term priors and a smooth visibility penalty. It is an exploratory robust composite objective, **not a calibrated probability**. Alias integers remain fixed during refinement. Shape-only projection removes the RF coefficient's constant contribution, so its paired `c` position results coincide as expected.

Strict frequency, visibility, residual-structure and ownership gates are reapplied after freezing each position. Direct-state association metrics for the shape-only variant precede a separate hardware recalibration and should not be interpreted as its optimized final coverage. The combined smooth-receiver result below does receive a dedicated final recalibration.

![Independent errors for three variants and both c arms](position_accuracy_matrix.png)

![S01 grid starts and continuous refinement paths](s01_blind_paths.png)

## Independent continuous-fit errors by scan

Errors are kilometres, **`c=0` / fitted `c`**. These use the continuous-frequency variant. The older 250 km regional search had different geography, initialization and optimizer settings, so its errors are historical references rather than a matched search ablation.

| Physical model | S01 | S02 | S03 | S04 | S05 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shared phase | 3.557 / 3.551 | 1.065 / 1.099 | 1.270 / 1.336 | 4.625 / 4.607 | 3.978 / 3.974 |
| Satellite family rate | 3.367 / 3.353 | 2.833 / 2.804 | 1.145 / 1.180 | 3.568 / 3.589 | 6.336 / 6.317 |
| Orbital model | 3.453 / 3.454 | **0.662 / 0.643** | 1.212 / 1.244 | 2.111 / 2.108 | 3.669 / 3.678 |
| Penalized subdivision | 3.501 / 3.496 | **0.879 / 0.916** | 1.774 / 1.852 | 2.643 / 2.616 | 4.856 / 4.854 |
| Correlated noise | 3.561 / 3.538 | 1.472 / 1.441 | 1.607 / 1.700 | 1.785 / 1.653 | 3.095 / 3.095 |
| Smooth receiver error | 3.864 / 3.855 | 1.260 / 1.239 | 2.326 / 2.353 | 2.641 / 2.614 | 2.625 / 2.624 |

Several starts converge to essentially the same displaced solution, so extra iterations within that nomination basin do not by themselves solve the error. The [full evaluation CSV](evaluation_summary.csv) separates position error, continuous objective, strict acceptance score, coverage, track size and native residual RMS.

## What drives the displacement?

The [gate attribution](oracle_gate_attribution.json) first revisits the sealed previous GPS-start diagnostic. For shared phase with fitted `c`, the total loss decreases by **4,479** on moving away from GPS. Tracks accepted at both locations contribute **+0.22**, a slight worsening; newly accepted tracks contribute **−4,479.21**. The same pattern dominates all six old GPS-start examples. Gate transitions can therefore overwhelm the local frequency-fit gradient.

Removing those transitions makes optimization continuous but leaves a separate physical/model/nomination bias. The [new S01 audit](DSX01-S01/oracle_continuous_bias.json) fixes the blind centre nominations and refits nuisance parameters separately at GPS and the blind endpoint. GPS is used only in this diagnostic. The following families provide the largest data-cost rewards for displacement; identities remain unverified.

| Model | Leading candidate-family data-cost changes, blind minus GPS |
| --- | --- |
| Shared phase | 69333: −76.4; 69523: −39.8; 69428: −23.2 |
| Satellite family rate | 69428: −24.8; 67658: −6.4 |
| Orbital model | 69428: −23.7; 67658: −6.5 |
| Penalized subdivision | 69333: −76.0; 69523: −42.6 |
| Correlated noise | 69333: −17.3; 69523: −3.8 |
| Smooth receiver error | 69333: −14.9; 65627: −11.8 |

For shared phase, the displaced fit gains 144.25 objective units, mostly through data fit rather than prior cost. Adding a satellite rate substantially reduces 69333's contribution, but other families then favour a different position. This is not simply one optimizer failing to find the same basin. Fixed incorrect nominations, unmodeled family/receiver effects and nuisance regularization remain competing explanations.

![Families rewarding the displaced S01 fits](s01_family_bias_attribution.png)

## Iteration: support and nuisance-prior controls

A fourth localization variant admits geographic calibration only from candidate families nominated on at least two distinct `(receiver, channel)` combinations at the blind centre. Unsupported fragments remain available for postfit association and in the raw denominator. This fixed support mask does not use GPS. It was tested across all six models and all five scans, with paired `c` arms.

S01 additionally tests phase prior sigma ×3, receiver/band drift sigma 2 Hz/s with bound ±5 Hz/s instead of 0.5 Hz/s and ±1 Hz/s, and supported families plus the wider phase prior. These are sensitivity controls, not validated uncertainty models. Fitted-`c` S01 errors, kilometres:

| Model | Continuous | Supported families | Wider phase prior | Wider drift | Support + wider phase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shared phase | 3.551 | 3.756 | 3.569 | **2.213** | 3.743 |
| Satellite family rate | 3.353 | 3.407 | 3.107 | 2.790 | 2.728 |
| Orbital model | 3.454 | 4.042 | 3.235 | 2.497 | 3.612 |
| Penalized subdivision | 3.496 | 3.628 | 3.553 | 2.277 | 3.641 |
| Correlated noise | 3.538 | 3.701 | 3.230 | 2.854 | 3.437 |
| Smooth receiver error | 3.855 | 4.491 | 3.454 | 2.734 | 4.189 |

The original S01 shared-phase fit reaches a receiver/band drift bound; widening it materially changes the estimated position. Phase-prior widening and simple family-support counts do not solve the remaining bias. More representation in a family is not sufficient evidence that it should steer position.

## Joint static-site fitting

All five scans were also fit jointly to one position, retaining separate hardware offsets/drifts for every scan. A control permits independent satellite phases; a second shares corrections only when both NORAD and the full causal TLE lines match. Priors for genuinely shared corrections would be charged once.

No observed candidate/full-TLE pair repeats across these scans' fixed nominations, so there are no satellite correction parameters to share in this test. The shared-TLE graph is exactly equivalent to its independent-phase control. Equivalent later cases reuse the identical numerical result and explicitly record that fact.

The fitted-`c` joint-site errors are 1.630 km shared phase, 2.188 km family rate, 2.152 km orbital, 1.677 km subdivision, 1.842 km correlated noise and 1.683 km smooth receiver. Joint frequency fitting therefore remains outside 1 km. It should not be confused with the simpler arithmetic combination below.

![Support, prior and pooled-site ablations](extended_position_accuracy.png)

## Simple five-scan position combination

Both arithmetic mean and coordinate-wise median were evaluated for every initial variant/model/`c` arm. These operations receive fitted positions, not GPS. They assume a stationary site and are **not joint frequency refits**. All rules are reported to avoid presenting a GPS-selected scan subset as the algorithm.

| Arithmetic combination | `c=0` error (m) | Fitted-`c` error (m) |
| --- | ---: | ---: |
| Continuous smooth receiver | **670** | **680** |
| Family-balanced subdivision | 847 | 854 |
| Family-balanced shared phase | 955 | 969 |

The continuous smooth-receiver combination is sensitive to contributing scans: its four-scan means range from 331 to 1,323 m for `c=0`, and 344 to 1,327 m with fitted `c`. This is a postfit sensitivity check; the main fits use all observations, with no held-out points.

![All combined-site results, including the poorer alternatives](consensus_accuracy.png)

## Frequency association at the frozen combined site

For the continuous smooth-receiver arithmetic combination, the site is frozen before final calibration. Each scan compares eight-round nuisance fits from its independent-scan state and from zero hardware initialization, then chooses the lower curved composite loss. Position never changes. This extra calibration step uses no evaluation GPS.

| Scan | Associated `c=0` | Associated fitted `c` | All GLRT | Associated %, `c=0` / fitted `c` |
| --- | ---: | ---: | ---: | ---: |
| S01 | 3,723 | 3,666 | 4,797 | 77.61 / 76.42 |
| S02 | 2,778 | 2,723 | 3,524 | 78.83 / 77.27 |
| S03 | 3,087 | 3,087 | 3,988 | 77.41 / 77.41 |
| S04 | 2,690 | 2,692 | 3,719 | 72.33 / 72.39 |
| S05 | 1,457 | 1,350 | 4,056 | 35.92 / 33.28 |
| **Total** | **13,735** | **13,518** | **20,084** | **68.39 / 67.31** |

The totals contain 516 / 497 association segments and 26.6 / 27.2 GLRT points per segment. Accepted residuals pass the existing model-specific gates. These are candidate associations, not independent satellite truth. S05 still has poor coverage despite the accurate combined site. A correct position alone does not eliminate calibration/association initialization failures.

At the same frozen sites, cold versus warm initialization changes S04 from 832 / 869 associated points to 2,690 / 2,692. This is direct evidence for another calibration basin; it is not a position improvement. More rounds within just the warm basin did not discover it.

The matched `c` comparison separates frequency effects from the 670 / 680 m position errors. Native RMS on common accepted observations is:

| Scan | Common points | Same candidate-label points | Native RMS `c=0` / fitted `c` (Hz) |
| --- | ---: | ---: | ---: |
| S01 | 3,666 | 3,666 | 118.9 / 118.9 |
| S02 | 2,723 | 2,723 | 154.2 / 154.2 |
| S03 | 3,087 | 3,087 | 144.6 / 144.6 |
| S04 | 2,644 | 2,566 | 140.8 / 141.5 |
| S05 | 758 | 758 | 199.8 / 196.7 |

The [full paired frequency data](consensus_calibration/mean_continuous_receiver_smooth/c_ablation.json) additionally include innovation RMS. S04 changes some labels, so that row is not a pure same-identity residual comparison. Better common-point RMS does not establish better localization or better total coverage. Here `c=0` has both slightly smaller combined-site error and greater overall association coverage.

## What remains to solve

The tested approaches separate two problems: binary gates create false geographic incentives, while smooth fixed-family fitting retains a physical/nomination bias. Wider drift bounds change the result without resolving it. Simple scan averaging reaches sub-1 km here, but joint fitting and individual-scan estimates remain worse and the combined result is not stable to every scan removal.

The next bounded iteration should expand **blind nuisance calibration multistarts**, then refresh candidate nominations during continuous fitting. That directly addresses both the strong S04 cold/warm disparity and the centre-frozen label assumption. In parallel, the S01 audit now identifies which candidate families need orbit/radio-model checks. Any added orbit/timing correction needs an identifiable prior and a comparison of fit gain against position movement; it must not be selected merely because it pulls a result toward GPS.

## Artifacts and verification

The [evaluation CSV](evaluation_summary.csv), [paired frequency CSV](c_ablation.csv), [consensus evaluation](consensus_evaluation.csv), per-scan protocols/endpoints, support masks, joint-site factor states and oracle-only audits preserve the measured results. [Validation](validation.json) records bounded monotone paths, matched `c` search starts and fixed nominations, source/input hashes, and **18 passing focused tests**. Ruff passes for the new numerical helpers, tools and tests.

The numerical helpers have tests for Gaussian constant elimination, affine removal that preserves curvature, continuous cost around the former gate, bounded recovery of known synthetic position, paired-versus-dense phase geometry, shared-position factor fitting, and one-time priors only for identical causal TLE entries. Dense orbit evaluation was replaced by evaluating only nominated observation/satellite pairs, with numerical parity tests; no RF was collected and archive inputs remain read-only.

Reproduction tools are `prototype_dsx01_continuous_position.py`, `prototype_dsx01_supported_position.py`, `prototype_dsx01_pooled_position.py`, `fuse_dsx01_continuous_position.py` and `refit_dsx01_consensus_calibration.py`, using `OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tools` and the repository virtual environment. Separate `report_*` and `audit_*` tools consume evaluation GPS; fitting tools do not. Source snapshots and hashes distinguish the original computations from later formatting and exact duplicate-model reuse.
