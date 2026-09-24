# DS1 baseline versus shared receive-time benchmark

Frozen before the new fits. DS1 v1 names the existing 339-recording cohort
without changing its ordered membership or 151/124/64 TRAIN/validation/TEST
partition. `dataset.json` and its seal enumerate five eight-hour calendar groups,
twenty nested 1/6/16/all-scan cases, and Sacramento 250 km/Reno 500 km priors.
These are fixed prefixes, not every possible single scan or sliding window.
This is a retrospective regression comparison: validation and partial TEST
outcomes have already been inspected. It is not a new untouched final test.

## Two models

Baseline has tau=0. Shared receive-time uses one tau across every track,
satellite, receiver, and recording within a case, bounded to [-5,+5] seconds.
Satellite ECEF position and velocity are interpolated at recorded time+tau
using the original causal cached elements. Positive tau evaluates later UTC.
At each geographic point/tau, reselect each track's candidate by training RMS
and fit its constant CFO on its original randomized training mask. No cone,
per-satellite orbit corrections, frequency drift or per-scan time parameters.
Retain every eligible >=3-second track and occupied-second weight in the
800-Hz-capped squared-RMS objective, including unsupported tracks at the cap.
The time range is an uncalibrated sensitivity bound, not a timing prior or CI.

## Bounded geographic and time search

Reuse the case/prior's previously sealed blind tau-zero baseline selected
coordinate, with exact membership, source/seal and tau-zero score checks.
Never use an earlier truth-error ranking or the recent p0007 geographic result.
This is a staged local comparison seeded by blind baseline acquisition, not an
exhaustive joint search over the full geographic disk.

At the seed, test integer tau=-5,...,+5 and refine within +/-1 second of its
TRAIN-best integer at 0.25-second spacing, clipped to the global bound.
Then use geographic spacings 5, 2.5, 1.25, 0.625, 0.3125 and 0.15625 km.
At each level, form the union of 3x3 neighborhoods around the accumulated
baseline and shared-time TRAIN winners, clipped to the original prior disk.
At every new geographic point score tau=0 and the current shared-time winner's
tau. Both models therefore see the same geographic union. Retain every earlier
point/tau score and select each model using only its own training objective.
Shared-time includes baseline tau-zero pairs and can never have worse minimum
training loss than baseline on the accumulated union.

After spatial levels 5, 1.25, 0.3125 and 0.15625 km, evaluate a local tau grid
within +/-0.5 seconds of the current shared-time winner at 0.1-second spacing,
clipped to [-5,+5], retaining current tau and zero. The grid may be centred on
a quarter-second value; 0.1 seconds is the increment, not rounding to a decimal.
Local tau updates occur only at the current winning geographic point. They do
not rescore all older geography at all new taus. Tau coverage is adaptive and
partial. Record all visited pairs, deterministic ties, global/local boundaries,
and non-increasing incumbent training scores. This is not a global optimum
certificate, and grid spacings are not uncertainty intervals.

## Execution and evaluation

Benchmark the reused exact scorer before launch and retain actual timings and
resource measurements. Use up to sixteen worker processes, single-thread BLAS,
long cases first; concurrency may be reduced for measured memory needs without
changing results. No fresh RF or production changes. Input/cache authority is
checked against the saved receipts. Preserve every input failure: the known
TEST recording `scan-hop-6cd2560365a058bc` makes the all-64 case ineligible;
do not omit or replace it to obtain a complete result. The unaffected 1/6/16
cases remain valid regression cases. Expected accounting is 80 model rows,
including four explicit input failures for the two priors on that full case.

Freeze each case/prior's paired inference before reading reference coordinates
or evaluating held observations. Use original randomized within-track holdouts,
not chronological masks. Held observations never select position, tau, candidate,
search expansion, bounds, or stopping. Reference is only post-inference evaluation.
Publish all rows, per-group/per-duration position errors, held capped/uncapped
RMS with denominator/support definitions, tau, runtime and failure/boundary
status. Group/view/initialization repetitions are correlated; report paired
comparisons and sample counts rather than treating 80 rows as independent.
No model/hyperparameter selection is authorized from this regression suite.
