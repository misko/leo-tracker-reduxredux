# DS21-011 fitted-c three-model results

Model C's training-selected CH1–8 position is **0.479573 km** from the configured
reference, below the 0.5 km threshold on this recording. Model B gives
**0.743996 km** and Model A **2.491943 km**. All **54 location fits were stationary**;
all 12 outcomes were sealed before the seven reference rows were calculated.
One passing development result does not establish the full-DS21 target, which
remains unmet.

| Model | View | Error km | Selected proposal | Fitted c Hz/GHz | Calls / stationary | Boundary flag |
| --- | --- | ---: | --- | ---: | ---: | --- |
| A | Final CH1–8 | 2.491943 | shape-all | -406.987881 | 18 / 18 | No |
| B | CH1–8 | 0.743996 | shape-low | -500.767405 | 6 / 6 | No |
| B | CH1–4 | 1.142057 | shape-high | -552.111720 | 6 / 6 | No |
| B | CH5–8 | 6.735033 | shape-all | -600.029778 | 6 / 6 | No |
| C | CH1–8 | 0.479573 | shape-all | -477.651392 | 6 / 6 | No |
| C | CH1–4 | 1.080449 | shape-high | -543.133185 | 6 / 6 | No |
| C | CH5–8 | 3.818150 | cold-2 | -447.904939 | 6 / 6 | No |

Both B and C improve on their own half-band estimates when combining bands.
This differs from [DS21-009](THREE_MODEL_009_RESULTS.md), where B combining was
worse than either half and A was closest. These are separately selected
training solutions; reference error does not select a model or start. The
variation across recordings argues against choosing a universal approach from
one favorable case. No algorithm is promoted by this result alone.

A runs six low → locked-high → final-all paths. Its 18 calls include all three
dependent stages, not 18 independent combined fits; only its final-all result
is selected. B/C each use six starts per view. Selection minimizes each model's
training objective among stationary results, with original start order resolving
ties. B/C half-view likelihoods use their designated observations but inherit
shared discovery, geography and physical initialization. C also reuses six
receiver ambiguity lifts derived once from all-training proposals. These are
not independently initialized end-to-end half-band pipelines.

All seven selected boundary flags are false. The recorded minimum physical
constraint slacks range from 0.240704 to 3.133655; the original flag covers
satellite total-timing and geographic constraints, not every coefficient bound.
Stationarity and inactive reported boundaries do not prove global optimality.

Frequency diagnostics remain separate from position accuracy:

| Model, CH1–8 | Training objective | Likelihood NLL | Posterior frequency RMS Hz |
| --- | ---: | ---: | ---: |
| A | 39079.546013 | 38846.483122 | 105.998479 |
| B | 37669.860104 | 37423.118539 | 97.216725 |
| C | 36364.559021 | 36155.907807 | 93.211941 |

The models have different association/calibration structures. Their objectives
are not interchangeable validation scores, and frequency RMS is not a position
confidence interval. This case's better C frequency fit and position error do
not overturn the counterexamples in the earlier comparisons.

The [completed proposal chain](PROPOSALS_011_RESULTS.md) supplies 41 shared
satellite candidates and six original proposals per view. Training inventory is
3,062 / 1,805 / 1,257 windows and 3,951 / 2,371 / 1,580 native alternatives for
all/low/high. Whole 20-second groups use the original seed 20261012 partition.
The model initialization audit found all 24 required A/B projections succeeded
with the unchanged strict solver, with maximum saved closure 2.539e-9 Hz.
No fallback source transfer was needed. A's 12 unused all/high calibration
projections remain explicitly omitted; their placeholder/timing seeds are
retained. C's 18 native seeds reuse exactly six lift derivations.

This is the unchanged [v2 fitted-only protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md):
20 seconds and 600 iterations per fit, original 25 km proposal-local disks and
physical priors, with A's high stage locked to its preceding low-stage position.
A paths use 90/105/110-second internal/TERM/KILL limits; B/C views use
165/175/180. One dataset science process and one BLAS thread run at a time.
The same 411 numerical and 412 metadata-reader source bindings used on DS21-009
remain valid. There were no new numerical source changes or refits on this case.
The metadata reader preserves the original sequential high-stage descriptive
override while checking every raw fit field and the remaining validation gates.

Held observations were not used for these fits or selection. The reference
entered only after all 12 outcomes and seven training selections were sealed.
Accuracy is measured against the configured station reference, which is not an
independently surveyed location. The aggregate terminal SHA-256 is
`406cd9a13724b48abb385bf6292fd7db6e00ba37d093d5e255e3ee5f46a32cb4`.
The separate [receipt audit](THREE_MODEL_011_AUDIT.json) passed all source, parent,
call, selection and evaluation checks without new scientific calculations.

The historical five-case table remains unchanged; 009 and 011 are reported as
additional fitted-only three-model comparisons, with 007 a C-only comparison.
Nine of 34 fast development recordings have complete proposal sets and 25 still
require initialization. DS21-013's final comparison is next. The 20 locked fast
recordings remain unopened for inference; full-dataset performance is unproven.
