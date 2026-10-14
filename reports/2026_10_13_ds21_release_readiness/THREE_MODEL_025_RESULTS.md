# DS21-025 fitted-c three-model baseline

The first complete DS21-025 baseline gives combined CH1–8 errors of **3.297411 km
for A, 8.315280 km for B and 1.121626 km for C** against the configured reference.
None of the seven reported solutions is below 0.5 km; B/high is closest at
0.588376 km. All 12 outcomes were sealed before reference evaluation. Of 54
optimizer calls, 52 returned stationary fits; the two excluded results remain recorded.
There is no earlier DS21-025 result against which to claim an improvement.

| Model | View | Error km | Training-selected proposal | Fitted c Hz/GHz | Calls / stationary | Selected boundary |
| --- | --- | ---: | --- | ---: | ---: | --- |
| A | Final CH1–8 | 3.297411 | cold-2 | -590.566460 | 18 / 17 | No |
| B | CH1–8 | 8.315280 | cold-1 | -624.169408 | 6 / 5 | Yes |
| B | CH1–4 | 3.385533 | cold-1 | -523.645113 | 6 / 6 | No |
| B | CH5–8 | 0.588376 | cold-2 | -679.339017 | 6 / 6 | No |
| C | CH1–8 | 1.121626 | cold-2 | -601.630065 | 6 / 6 | No |
| C | CH1–4 | 5.954192 | cold-1 | -627.865423 | 6 / 6 | No |
| C | CH5–8 | 8.584032 | cold-2 | -709.404984 | 6 / 6 | No |

B's combined estimate has greater error than either of its half-band estimates;
C's combined estimate has lower error than either half. Each solution was
selected by its own stationary training objective, with original start order
breaking ties. Reference error did not select a model, view or start. This
within-recording comparison does not establish a universal combining rule.

A runs six dependent low → locked-high → final-all paths. Its 18 calls include
all three stages, rather than 18 independent final-all estimates. A/shape-low's
final call has KKT residual **1.534913**, above the 0.001 ceiling, and cannot supply
an A selection. B/all's shape-all call has residual **6.737279** and is also
excluded. Both solvers reported success; that flag did not override the
stationarity requirement. Their raw vectors, nuisance values and diagnostics
remain intact, with no retry. The first A path's process initially rejected the
known high-stage descriptive metadata override after its numerical outcome had
been saved. The qualified reader validated that retained outcome without a
refit; all six high-stage overrides preserve the original raw numerical fields.

B/all is the only selected solution with the original boundary flag. Its minimum
physical constraint slack is 1.066e-14. Its position remains 14.710 km from its
25 km proposal-local center and 115.585 km from the 250 km regional origin, so
the reported active constraint concerns satellite timing rather than a geographic
disk. Six additional stationary, unselected calls have boundary flags, as does
the excluded A final call. The flag covers timing/geographic constraints, not
every calibration coefficient bound. Stationarity does not prove global
optimality; tiny negative saved slacks down to -3.553e-15 are numerical roundoff.

Frequency-fit diagnostics are separate from position accuracy:

| Model, CH1–8 | Training objective | Likelihood NLL | Posterior frequency RMS Hz |
| --- | ---: | ---: | ---: |
| A | 30418.241836 | 30187.775287 | 129.266109 |
| B | 29181.896490 | 28791.714946 | 111.821739 |
| C | 28915.850380 | 28770.494009 | 113.776353 |

The objectives and posterior RMS definitions reflect different association and
calibration structures. They are not interchangeable validation scores or
position confidence estimates. No algorithm or parameter setting is promoted
from this baseline.

The [completed original proposal chain](PROPOSALS_025_RESULTS.md) supplies a
870-satellite regional bank, 36 shared final candidates and six physical
proposals per view. It uses the unchanged 100 / 50 / 25 / 12.5 km discovery
hierarchy, rather than the separate 80-center coverage intervention. Training
contains 2,428 / 1,240 / 1,188 windows and 3,346 / 1,686 / 1,660 native alternatives
for all/low/high. Whole 20-second counter groups retain seed 20261012 and held
blocks 2, 3 and 13.

All 24 required A/B initialization projections succeeded through the original
strict solver, with maximum saved function error 9.968e-10 Hz; no exact-source
fallback was needed. A's 12 unused all/high calibration placeholders remain
explicit. Eighteen C seeds share exactly six receiver ambiguity lift derivations
from all-training proposals. Exporting a physical function back into its own
source has maximum closure error 7.276e-12 Hz; this is distinct from C's native
projection approximation loss. B/C half-view likelihoods inherit all-channel
training discovery and physical initialization, and C also inherits those shared
lifts. They are not independent end-to-end half-band pipelines.

The unchanged [v2 fitted-only protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md)
limits each fit to 20 seconds/600 iterations, preserving original priors and
25 km proposal-local disks; A/high fixes geography to its preceding low-stage
solution. Saved fit durations range from 0.695 to 10.543 seconds. A paths retain
90/105/110-second internal/TERM/KILL limits and B/C views 165/175/180. All 402
initialization, 411 numerical and 412 reader live/archive source bindings pass;
the numerical source map is identical to DS21-011. No frozen source changed.

Held observations were not used for fitting or selection. All 12 scientific
outcomes, metadata reviews and seven training selections were sealed before the
configured-reference join. The reference is not an independently surveyed
location. Terminal SHA-256 is
`d59eb71a1533d2c83bda82b7797d7d40183bcf4748af5db43e69b06c0479e44f`;
evaluation SHA-256 is
`0995e078798d6cbf4eae708ac9adc436e0f3cc5da004c8769342fc981ceec461`.
The [independent receipt audit](THREE_MODEL_025_AUDIT.json) verifies all call
inventories, seed/options/center bindings, raw-field preservation, scalar seals,
training argmins and saved evaluation joins using metadata and arithmetic only.
It performs no new scientific or reference evaluation. The full-DS21 sub-0.5 km
target remains unmet.
