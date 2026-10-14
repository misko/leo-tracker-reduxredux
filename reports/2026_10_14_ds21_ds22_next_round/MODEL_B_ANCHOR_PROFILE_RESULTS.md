# Model B: profiling at half-band positions does not improve the selected result

The two original worst cases completed a new six-call training-only experiment.
For each training-selected all/low/high position, the experiment copied the
original all-band state, changed only its two geographic coordinates, and fit
all-band nuisance parameters with geography fixed. It then released geography
using that profile's unchanged physical calibration and timing state. All twelve
calls converged, but training-objective selection chose the original all-band
position on both cases: **039 remains 8.599847 km; 023 remains 5.599817 km**.
This intervention is not an accuracy improvement and is not promoted.

Both complete training outcome sets were sealed before any reference join.
Selection used only stationary free-fit objective, with predetermined anchor
order for ties. The original incumbent was not added as an extra selectable
state; the same-anchor profile and continuation reproduced it exactly.

| Case | Anchor | Final objective | Final likelihood NLL | Prior penalty | Position error km | Selected |
|---|---|---:|---:|---:|---:|---|
| 039 | all | 34895.827 | 34517.503 | 378.324 | 8.599847 | yes |
| 039 | low | 35804.013 | 35513.197 | 290.816 | 7.603771 | no |
| 039 | high | 38427.453 | 38069.599 | 357.855 | 26.435310 | no |
| 023 | all | 28711.604 | 28510.822 | 200.782 | 5.599817 | yes |
| 023 | low | 32209.611 | 31935.961 | 273.650 | 21.232529 | no |
| 023 | high | 30918.537 | 30722.092 | 196.445 | 1.279603 | no |

023's high-anchor continuation is closer to the reference but has a substantially
worse training objective. Its likelihood penalty increases by 2211.269 while
its prior penalty decreases by 4.337 versus the selected all-anchor state.
Thus the model's likelihood ranking, rather than the prior penalty, rejects
this particular closer solution. Selecting it by reference error would be an
oracle result and is not allowed. These local profiles do not exhaust all
possible modes or prove the exact source of likelihood misspecification.

| Case / anchor | Fixed-position profile NLL | Profile prior penalty | Free-position movement km |
|---|---:|---:|---:|
| 039 / all | 34517.503 | 378.324 | 0.000 |
| 039 / low | 35737.947 | 379.924 | 7.713 |
| 039 / high | 38182.763 | 309.461 | 6.969 |
| 023 / all | 28510.822 | 200.782 | 0.000 |
| 023 / low | 33365.660 | 200.650 | 19.147 |
| 023 / high | 30958.353 | 238.544 | 9.217 |

Each new call retained 20 seconds, 600 iterations and fitted c. The same all-band
objective, observation frame, candidates, priors and numerical fit implementation
were used throughout. Half-band fits supplied geography only, not calibration,
nuisance coefficients or timing. Every seed was checked against the regional
prior, coefficient bounds and orbit timing support without clipping/rescaling.
Independent post-fit audits replayed objective and projected KKT: fixed geography
was excluded only for the profile; every selectable final used the full free
audit. Maximum final KKT was 0.000860, below 0.001.

The intervention explicitly changes the local search disks to 25 km around the
training-selected anchors. Six new calls per recording match the original count,
but this is **not** an equal-cost end-to-end comparison: the anchors and warm
all-band state depend on eighteen earlier view fits plus discovery. It is a
controlled warm-start diagnostic, with no incumbent or best-error substitution.

Whole experiments took 26.736 s and 18.584 s under 180/195/200-second bounds.
Six tests and Ruff passed, including actual synthetic fixed-position optimization,
physical-state preservation on release, failed-profile release suppression,
objective/KKT replay, invalid geographic/calibration seeds and pre-reference
paired-outcome requirements. Implementation is `e84033f0d`.
Raw sealed results are `local/model-b-anchor-profile-{039,023}-v1`.

The next scientific investigation must distinguish residual-model or association
bias from additional unsearched modes; merely recycling these half-band positions
does not resolve the combined-band failure. The full DS21/DS22 target remains open.
