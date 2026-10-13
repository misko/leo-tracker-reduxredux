# Fixed likelihood-scale transfer to five development cases

Prespecified before new transfer fits. This tests whether the modest DS21-039
regularization sensitivity transfers; it is not an alpha search or a release
claim. Every fit keeps common `c` free. Locked recordings remain untouched.

## Cases and starts

Run DS21-001, 003, 005, 023 and 039 in that order. All five are required regardless
of the preceding outcomes. Use each case's six historical **all-view fitted
endpoints**, preserving its complete vector and two group nuisance coefficients.
Each endpoint retains the 25 km disk centered on its own original physical
proposal. The same six endpoint/center pairs enter both conditions.

The receipt-only preflight found all 30 finite endpoint states. Twenty-eight
are stationary. DS21-003 start 4 and DS21-039 start 2 are nonstationary; keep them
as initializers in both conditions, but exclude them from baseline incumbents.
Do not filter cases or replace starts using position error. Recorded receiver
sampling lifts are already included in these physical endpoints and must not
be applied a second time.

| Case | Training windows | Fixed satellite bank | Physical vector size | Nuisance size |
| --- | ---: | ---: | ---: | ---: |
| DS21-001 | 2,562 | 39 | 46 | 2 |
| DS21-003 | 2,422 | 37 | 44 | 2 |
| DS21-005 | 1,808 | 44 | 51 | 2 |
| DS21-023 | 2,384 | 33 | 40 | 2 |
| DS21-039 | 2,798 | 43 | 50 | 2 |

DS21-039 here uses its historical six endpoints. It does **not** receive the
later seven-call refinement winner used in the two-start sensitivity experiment.
Consequently, neither 4.073 km nor 3.930 km is promised as a replay result for
this different, consistently defined transfer comparison.

## Fixed conditions and budgets

Use `objective = alpha * original observation NLL + original physical priors`
with alpha=1 and alpha=0.25 only. Preserve each case's original native candidates,
satellite bank, calibration frame, common/relative timing basis, physical limits,
Gaussian priors, neutral waveform evidence and zero temporal edges. Reuse the
corrected tempering numerical component without changing its arithmetic.

Each case has exactly twelve prescribed new fits: six starts per condition,
20 seconds and 600 iterations per fit, at most 240 optimizer seconds. Each case
is a separate bounded slice with 285 seconds internally, TERM at 295 seconds
and KILL at 300 seconds. Scientific slices run one at a time. Checkpoints must
be explicit; failed or orphan attempts cannot be silently rerun.

Select the minimum stationary training objective within each condition, using
a fixed start-index tie rule. Alpha=1 may also retain eligible stationary
historical incumbents. Alpha=0.25 requires actual new stationary outcomes.
Cross-alpha objective values cannot select a condition because they have
different likelihood scales. Retain unavailable conditions and failed cases.

## Input reconstruction and validation

Use a new training-only loader: original tracking input, unchanged partition
seed 20261012 and 20-second blocks, all CH1–8, exact original preparation digest.
No historical wrapper that also prepares held observations may be invoked.
Load the bound discovery bank and select the original proposal bank indices;
do not rebuild the catalogue or choose a new candidate set.

Freeze each case's six endpoints, original seeds/lifts, source archives, parent
receipts, membership, census, input, bank, native evidence and new source closure
before numerical work. Before any fit, alpha=1 must replay the saved objective
and untempered NLL for **all six** original endpoints within 1e-7, including the
two nonstationary initializers. Actual alpha=1 wrapper gradients and posteriors
must agree with the reconstructed original model.

Historical source archives are limited: the preflight verified all 50 archived
files, but one orchestration module per case differs from current code and the
old archives omit some dependencies. Do not claim complete historical byte
identity. Preserve the old archives, document the reconstruction and require
the actual endpoint replay gates. A failed gate stops that case before fitting
and is reported; it does not authorize changing observations or old receipts.

Owned tests must cover training-only preparation, source/bank/endpoint gates,
the two nonstationary initializer rules, unchanged endpoint/center pairs, no
double application of sampling lifts, actual tiny-fitter integration, bounded
12-call routing, preserved failures, and cached-selection tamper rejection.

## Evaluation and decision

Seal both condition selections before joining the configured reference. Report
per-case error, stationary/failed fits, coverage, median, maximum and count below
0.5 km. Separately report original untempered NLL, scaled NLL, physical prior
cost, native branch RMS, signal/clutter mass and active bounds.

A positive result on DS21-039 alone does not establish transfer. No per-case
choice of whichever alpha is closer to the reference is allowed. This five-case
test still precedes all 34 fast development cases and the frozen release's 20
locked fast cases. The configured reference is not independently surveyed here.
