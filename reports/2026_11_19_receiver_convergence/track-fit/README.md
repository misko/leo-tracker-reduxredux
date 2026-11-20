# Exact orbital geometry for the lean track receiver

Refitting the same track assignments with exact range rate on the sampled orbit reduced fitted-calibration median error from **2.136 to 1.427 km** on the six timing recordings and from **1.377 to 1.066 km** on eight hash-selected DS26 confirmations. Both receivers published the same five timing and three confirmation fixes, all within 5 km. Both withheld on the frozen wrong tile. The candidate met the preregistered gate for raw-IQ follow-up. Original v5 published all 14 fixes and retained lower medians. [Protocol](PROTOCOL.md) · [Sealed predictions](prediction-lock.json) · [Independent scores](scores.csv)

## What explained the error

A trace-only run of the locked lean receiver exported each selected candidate's role on the original track samples. After the sandbox exited, a separate supervisor matched fitted-calibration v5 owner rows from completed publication receipts. It verified both the serialized frozen request and its canonical execution digest, then joined on receiver, channel, timestamp rounded to 1 µs and folded measured CFO rounded to 1 mHz. A conflicting published owner at the same join key was excluded from comparison. The match covered **15,529 of 19,017** points used across the six lean fits, including the one diagnostic withheld fit. The same NORAD was selected on **15,134 of the 15,529 comparable points**, or 97.46%. Agreement with v5 establishes correspondence between the methods on common support. The archive supplies no independent identity proof for these measurements. [Matched sample traces](ownership-trace.jsonl.gz) · [Owner receipts and aggregate diagnostics](ownership-audit.json)

| Recording | Same / comparable owner | Exact-minus-linear CFO RMS on matching rows (Hz) |
|---|---:|---:|
| DS26-0036 | 2,568 / 2,690 | 242 |
| DS26-0122 | 3,095 / 3,095 | 142 |
| DS26-0237 | 3,105 / 3,115 | 186 |
| DS29-0082 | 876 / 904 | 320 |
| DS29-0174 | 3,133 / 3,133 | 117 |
| DS29-0247 | 2,357 / 2,592 | 345 |

The geometry column evaluates the existing lean site and phase with both centre-linearized and shifted Hermite range rate, holding every alias, phase and radio coefficient fixed. Geometry changed predicted CFO by 117–345 Hz RMS even where IDs agreed. The conditional residual grew on all six same-owner groups when the other parameters were held fixed. The joint refit below isolates how far the geometry correction carries once the shared parameters may adapt. It recovers some of the location gap with identical identities and leaves a residual gap to v5.

## One change to the final fit

The candidate starts from the two original bounded fits, including each track's selected orbit, alias, time support and robust weight. It evaluates the shifted ECEF Hermite state, rotates it into the terrestrial orientation at the observed epoch, and computes range rate from the current WGS84 receiver position. A local Jacobian for site and phase reuses the existing bounded solver. Up to three relinearizations and four line-search fractions per step may reduce the exact penalized frequency objective. Training, held scores, coarse orbit search, assignments, priors, fit inventory and publication thresholds follow the lean receiver. Both final calibration arms share the same assignments. The fixed wrong-tile held score remained 0.221 against a 0.28 threshold. [Inference source lock](source-lock.json) · [Candidate implementation](../../../tools/pipeline_eval/variants/robust_orbit_fit.py) · [Wrong-tile result](wrong-region.jsonl.gz)

| Cohort and calibration | Within 5 km of all scheduled, lean / exact / v5 | Median error among fixes in km, lean / exact / v5 | Worst published error in km, lean / exact / v5 |
|---|---:|---:|---:|
| Timing, `c = 0` | 5/6 · 5/6 · 6/6 | 1.832 / 1.667 / 0.818 | 4.479 / 3.779 / 1.320 |
| Timing, fitted `c` | 5/6 · 5/6 · 6/6 | 2.136 / 1.427 / 0.832 | 4.158 / 3.457 / 1.458 |
| DS26 confirmation, `c = 0` | 3/8 · 3/8 · 8/8 | 1.439 / 1.313 / 0.786 | 2.637 / 1.725 / 3.191 |
| DS26 confirmation, fitted `c` | 3/8 · 3/8 · 8/8 | 1.377 / 1.066 / 0.727 | 2.290 / 1.143 / 3.356 |

The median paired change in fitted geographic error was −0.095 km on the five common timing fixes and −0.311 km on the three common confirmation fixes. DS26-0122 worsened from 2.729 to 3.457 km. Withheld candidates remain outside the published-error distributions and inside all scheduled denominators. The reported coordinate medians keep the original single offered tile. [Exact candidate positions](positions.jsonl.gz) · [Paired lean positions](stock-positions.jsonl.gz) · [Per-case and cohort scoring](summary.json)

Frequency moved differently. The median paired conditional RMS change was −4.55 Hz for zero calibration and −7.38 Hz for fitted calibration on timing, and −16.84 and −17.86 Hz on confirmation. Those frequency comparisons include the diagnostic forced fits because each paired method uses the same assigned samples. Evaluating the exact frequency objective before and after refinement gave a reduction for all 28 matched-tile arm fits, with median reductions of 38.3% for zero calibration and 41.3% for fitted calibration. These are changes under the exact objective and its original priors. [Frequency outcomes](scores.csv)

## Runtime and scope

Fresh sandbox workers ran on CPUs 10 and 11 with one numerical thread. Exact fit median CPU was 2.87 s and median wall was 3.79 s across 14 matched tiles. The corresponding fresh lean figures were 2.77 s CPU and 3.36 s wall. Exact fit peak RSS was at most 155,336 KiB, versus 155,300 KiB for lean. This is stored anonymous track input through serialized positions on the shared x86 host. The confirmation panel consists of recordings from the same installation. [Timing and memory receipts](positions.jsonl.gz)

The source-bound synthetic checks cover the analytic position and phase Jacobians, exact-objective decrease at a planted offset and the null inventory. The earlier lean synthetic checks cover aliased position recovery and rejection of indistinguishable orbits. The archive audit and paired trial run separately, with the published owners opened only after the trace worker exits.

```sh
taskset -c 10,11 .venv/bin/python -m tools.pipeline_eval.qualification.robust_orbit_fit_diagnostic \
  --cache /tmp/robust-orbit-inputs --out /tmp/robust-orbit-audit
taskset -c 10,11 .venv/bin/python -m tools.pipeline_eval.qualification.robust_orbit_fit_trials \
  --cache /tmp/robust-orbit-inputs --out /tmp/robust-orbit-fit
taskset -c 10 env OPENBLAS_NUM_THREADS=1 .venv/bin/pytest -q \
  tests/pipeline_eval/test_robust_orbit_fit.py tests/pipeline_eval/test_robust_em.py
```
