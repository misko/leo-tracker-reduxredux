# Posthoc local response of the complete-owner CFO changes

Applying the actual 159 native CFO deltas to the previously saved response matrix gives a useful explanation for DS24-0010, but a poor approximation to the DS24-0011 refit. This is a **posthoc frozen-Gaussian/VI diagnostic**, not a position-accuracy forecast or an acceptance rule. It uses no GPS and performs no new measurement, orbit calculation or position fit.

| Case / arm | Local Hδ east / north (m) | Raw RF refit east / north change (m) | Difference norm (m) |
|---|---:|---:|---:|
| 0010 c0 | −76.006 / +109.927 | −99.863 / +100.350 | 25.708 |
| 0010 fitted c | −75.783 / +110.623 | −93.276 / +104.279 | 18.608 |
| 0011 c0 | −21.662 / +6.042 | −75.808 / −67.750 | 91.526 |
| 0011 fitted c | −22.913 / +6.717 | −78.298 / −69.868 | 94.513 |

![Saved local response and raw RF endpoint changes](local_response.png)

The matrix H maps native CFO changes to local east/north position change, in km/Hz, after the original shared nuisance projection. Each delta was used **once**, with no additional RF factor q. Exact native-ID joins preserve every column of the old 3,186-row and 2,241-row designs; all unmodified observations receive zero delta. The [native ordering table](native_ordering.csv) records all 159 nonzero-input locations.

Each owner's delta was decomposed into its projection onto the original degree≤2 time-Legendre basis and an orthogonal remainder. The original helper includes that owner's constant RF factor; its column space is the same quadratic time subspace, and projection does not rescale the measured delta. Both components were passed through H separately. Their responses and the owner responses sum exactly to the complete case response, within 7e−17 km. [Owner contributions](owner_response.csv) and [case totals](case_response.csv) retain both c arms.

For 0010, the remainder contributes only about 1.6 m to the combined local response; the quadratic component explains almost all of its approximately 134 m predicted displacement. For 0011, the quadratic and remainder responses partially cancel, leaving a predicted displacement of only 22–24 m. The actual raw refit moves 102–105 m. Orthogonality to a quadratic in measurement space does not imply zero position response. The large 0011 discrepancy also shows that this frozen linear map does not reliably forecast the full refit after nuisance, phase, precision and nonlinear geometry updates. This readback does not identify which update causes the discrepancy.

The actual arrows are differences between the sealed original and corrected RF endpoints. They are not distances from truth or policy gains. In particular, the 0011 c0 corrected endpoint loses original postfit accepted IDs, so its raw displacement remains a diagnostic even though its original primitive/owner gate field passes. Operational qualification and geographic evaluation remain separate.

The two projection/additivity fixtures passed. Computation, tests and a conservative metadata allowance consumed **1.481 seconds**, below the 20-second cap. The [summary](summary.json) and [seal](seal.json) bind the old H arrays, complete-owner ledger and helper, the immutable [measurement vector](../measurement/corrections.json), and the already sealed position RF outputs. The old external arrays/runtime are not republished here; exact source paths and hashes are recorded for replay. Original missing-mode and frozen precision assumptions remain. No measured RMS was multiplied by a worst-direction susceptibility proxy, and this explanation does not alter any endpoint, gate, measurement or prior decision.
