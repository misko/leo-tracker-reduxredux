# DS21-009 fitted-c three-model results

All **54 location fits were stationary**. Model A's training-selected CH1–8
result is **0.658299 km** from the configured reference; Model B gives
**5.327196 km** and Model C **1.595252 km**. None of the seven reported results
meets 0.5 km. Model A is closest on this recording, but this post-seal comparison
does not authorize choosing an algorithm separately for each reference position.
The full-DS21 target remains unmet.

| Model | View | Error km | Selected proposal | Fitted c Hz/GHz | Calls / stationary | Boundary flag |
| --- | --- | ---: | --- | ---: | ---: | --- |
| A | Final CH1–8 | 0.658299 | shape-high | -631.971642 | 18 / 18 | No |
| B | CH1–8 | 5.327196 | shape-high | -529.788594 | 6 / 6 | Yes, timing |
| B | CH1–4 | 0.790354 | shape-high | -525.964061 | 6 / 6 | No |
| B | CH5–8 | 0.772167 | cold-1 | -533.143309 | 6 / 6 | Yes, timing |
| C | CH1–8 | 1.595252 | cold-1 | -503.852470 | 6 / 6 | No |
| C | CH1–4 | 4.547625 | shape-all | -591.704701 | 6 / 6 | No |
| C | CH5–8 | 1.758365 | shape-low | -556.738873 | 6 / 6 | No |

Model A runs six dependent low → locked-high → final-all paths and selects the
lowest stationary final training objective. Its 18 calls are the six paths'
three stages, not 18 independent all-band fits. It does not produce independently
selected half-band position estimates. Models B and C each select among six
stationary starts separately for all, low and high training observations. All
selections use their own training objective, with original start index as the
tie-breaker; reference error never selects a start, view or model.

Combining bands worsens Model B's position error relative to both halves, while
Model C's all-band result improves on both halves. These opposing results do
not establish a universal benefit or penalty from combining bands. B/C half-view
likelihoods use their designated observations, but inherit the shared discovery
bank, proposal geography and physical initialization. C additionally inherits
six receiver ambiguity lifts derived once from all-training proposals. These
are not independent end-to-end half-band pipelines.

The B/all and B/high boundary flags are retained. The frozen fitter flags a
minimum satellite-timing or geographic feasibility slack below 1e-6; the flag
does not itself identify a 25 km disk hit. These two selected points are only
3.864952 km and 5.862350 km from their original 25 km proposal centers, and are
also inside the 250 km regional prior. Their recorded minimum slacks,
1.066e-14 and 3.553e-15, therefore arise from satellite timing constraints.
They satisfy the original constrained stationarity checks; an unconstrained or
globally optimal solution is not claimed.

Frequency fit is reported separately from position accuracy:

| Model, CH1–8 | Training objective | Likelihood NLL | Posterior frequency RMS Hz |
| --- | ---: | ---: | ---: |
| A | 35182.924108 | 34948.117723 | 98.888113 |
| B | 34413.680903 | 34005.526625 | 97.668409 |
| C | 32978.015734 | 32667.422547 | 95.537665 |

The models have different calibration/association structures. Their frequency
costs are not validation accuracy or a rule for choosing a release. In this
case B has a lower all-band frequency loss than A but a larger position error.
RMS values are frequency residual diagnostics, not positional confidence bounds.

The comparison uses the completed [fitted-only proposal chain](PROPOSALS_009_RESULTS.md):
41 shared satellite candidates, original ordered six proposals and 2,780 / 1,506 /
1,274 all/low/high training windows. Preparation retains randomized whole
20-second groups with seed 20261012. Every location fit uses fitted c, the
unchanged original objective and priors, at most 20 seconds and 600 iterations,
and its original 25 km proposal-local disk; A's high stage instead locks the
low-stage position as prescribed by its original core. No zero-c arm was run.
Initialization and each A path are bounded at 90 seconds internally / 105 TERM /
110 KILL; each B/C view uses 165 / 175 / 180. Dataset slices run serially with one
BLAS thread.

The [v2 seed-transfer validation](INITIALIZATION_009_V2_RESULTS.md) preserves all
22 successful required A/B projections exactly. Only B/all `cold-0` and `cold-1`
use independently verified original source coefficients after the specific
strict-projection nonconvergence error. Both verify frame, clock basis, physical
function closure and original coefficient/timing bounds; maximum mismatch is
7.276e-12 Hz. Failed solver coefficients are never accepted as fits or seeds.
C's original native projection and once-only lifts are unchanged. A's unused
initial high/all calibration coordinates are omitted, preserving every consumed
sequential input.

A-0 saved three stationary fits before its old post-run validator rejected the
core's explicit descriptive override: raw high-stage `training_high_fractions`
is `[0.5, 0.5]`, while the sequential path records `None` with
`uncentred-high-minus-low` parameterization. The separately versioned metadata
reader recognizes only that known override and checks every raw fit field,
source, seed, call, slice, selection and remaining scalar seal. **A-0 was not
refitted**. The completed comparison contains 54 calls, not 57; all original
scientific sources and receipts remain unchanged.

All 12 scientific outcomes and metadata reviews were sealed before the seven
reference rows were joined. Held observations were not used for these fits or
selection, and the reference entered only the post-seal error join. Accuracy is
relative to the configured station reference, not an independently surveyed
position. The
[independent receipt audit](THREE_MODEL_009_AUDIT.json) passes all source,
selection, boundary and evaluation checks, including 54 call/launch/termination
triples, all 12 complete slices and unchanged raw numerical fields. The aggregate
review terminal SHA-256 is
`06fd86ac0b2e85521c1dd098ef2911406ab22f719ce68202467ec0911e84764f`.

Scientific adapter: `tools/ds21_fitted_models_v2.py`, commit `7d83e159f`, with
411 frozen source files. Metadata reader: `tools/ds21_fitted_model_receipts.py`,
commit `13332f295`, with 412 source bindings. The v2 suite's original 20 tests,
14 strengthened targeted checks and corrected full sequential fitter comparison
passed. The metadata reader's 13-test suite, two targeted real-fit/54-call checks
and standalone failed-high check passed; it collects 14 cases. Independent
source review found no remaining blocker, and Ruff passed.

The historical five-case A/B/C table remains unchanged; this is a separate new
fitted-only comparison. Nine of 34 fast development recordings have complete
proposal sets, leaving 25 requiring initialization. DS21-011's model comparison
has started without an accuracy result; DS21-013 has proposals but its final
models have not started. The 20 locked fast recordings remain unopened for
inference. No full-dataset success or algorithm promotion is established.
