# Model A: source and stage audit, then matched high-timing control

No new scientific fits were run for this report. The implemented control is
ready for source review and a separate coordinator-owned freeze and bounded run.
No subkilometer improvement is established by its synthetic tests.

## Rank within one named algorithm version

The historical **shared-six sequential proposals v2, fitted-c** version has five
sealed development errors:

| Rank, best first | Case | Final CH1–8 error km |
|---|---|---:|
| 1 | DS21-001 | 0.534 |
| 2 | DS21-023 | 2.032 |
| 3 | DS21-003 | 2.601 |
| 4 | DS21-005 | 5.436 |
| 5 | DS21-039 | 6.229 |

Thus its best two are 001/023 and its worst is 039. DS21-005 is second worst.
These are the fitted-c column of the unchanged
[historical report](../2026_10_13_ds21_sequential_proposals_v2/README.md), not a
best-of-versions table. The current 34-case comparison is still being completed
and must supply its own uniform-version rank.

The separately named **coverage fitted-model composition v1** currently has
two qualified A cases: DS21-013 = **1.509542 km**, DS21-009 = **3.155489 km**.
Its best case is 013 and its worst is 009. The original fitted-v2 errors of
013 = 266.839679 km and 009 = 0.658299 km are separate baselines. Coverage changes
discovery geography and candidate sets as well as downstream physical seeds;
the 009 regression cannot be attributed to a single changed shift coefficient.
The next matched control starts from the qualified coverage parents for **both
009 and 013**, using each parent's own bank and six paths. It will not compare
different-bank model scores as if they were one objective.

## What the source and saved stages establish

The original high stage fixes the low-stage geography and complete physical
correction function, then fits per-receiver uncentered offsets **and satellite
timings** on high rows. The final stage frees geography, common correction
(including fitted c), clock and timings while retaining those offsets exactly.
Neither low-anchor uncertainty nor high timing/offset covariance propagates
into those final fixed offsets.

Reading saved scalar/vector receipts gives the following own-path audit. Motion
is Euclidean low-to-final displacement in the original optimizer frame. Fitted
c is the physical RF slope in Hz/GHz, which is invariant under affine time/RF
recentering; raw centered intercepts were not compared.

| Parent version / case | Selected path | Low→final motion km | Low c | Final c | High offset explained by timing, RX0 / RX1 |
|---|---|---:|---:|---:|---:|
| Historical shared-six / 001 | cold-0 | 0.770822 | -421.612760 | -244.630441 | 0.851444 / 0.465869 |
| Historical shared-six / 023 | cold-1 | 3.120402 | -232.859605 | -404.400047 | 0.905340 / 0.715273 |
| Historical shared-six / 005 | shape-high | 6.243580 | -493.414523 | -731.225208 | 0.825457 / 0.563661 |
| Historical shared-six / 039 | shape-all | 1.452373 | -615.832350 | -863.784453 | 0.795961 / 0.673699 |
| Original fitted-v2 / 009 | shape-high | 0.628534 | -525.964061 | -631.971642 | 0.809607 / 0.746724 |
| Coverage-v1 / 009 | cold-1 | 1.674692 | -506.108208 | -436.657687 | 0.860159 / 0.684081 |
| Original fitted-v2 / 013 | cold-0 | 6.232325 | -677.461184 | 82.727343 | 0.841205 / 0.579174 |
| Coverage-v1 / 013 | shape-high | 3.174758 | -566.570033 | -730.616690 | 0.831904 / 0.582889 |

The original diagnostic projects each high offset column against conditional
satellite timing columns using signal responsibilities, excluding priors. These
fractions establish local confounding; they are not observed Fisher information,
identity measurements or a monotonic predictor of position error. The best two
historical cases also have large fractions.

Original low→final calibration projection RMS is about 1e-11 Hz in these selected
paths: 8.99e-11 Hz for historical 039, 9.38e-12 Hz for coverage 009 and 9.16e-12 Hz
for coverage 013. This rules out a material coordinate/function representation
loss **on the checked original projection rows**. It does not establish correct
RF mapping, accurate extrapolation from low to high, or correct associations.
Final c changes do change the learned physical correction away from its low
anchor, despite exact coordinate transfer.

Historical 039 moves only 1.45 km from low to final, so its large miss is not
explained solely by a large final geographic update. Historical 005 moves
6.24 km, exposing a different stage pattern. These facts argue against one
universal final-stage drift explanation. The original 013 miss has a proven
upstream geographic coverage failure: the reference is outside all original
proposal disks. Coverage repairs that admissible geography, leaving a separate
1.51 km residual. None of these observations proves that high timing freedom
causes the remaining error.

The existing free-final-contrast experiment is already negative: low-informed
joint fits on 005/023 performed worse than matched absolute continuations.
This control does not repeat it. The DS21-039 root-cause reports also show that
better training frequency fit can coexist with only a small position improvement,
and that an extra receiver RF slope did not solve localization. A new coefficient
or a frequency score alone is therefore insufficient justification for promotion.

## Falsifiable intervention

For each of six original paths, reuse **the same own-path sealed low fit** in
both conditions. Compare:

1. `original-high-repeat`: run the original free-timing/high-offset stage from
   the original high donor, then the original final stage.
2. `low-timing-locked-high`: keep the high stage's geography, correction **and
   full common/relative satellite timing vector** at its own stationary low fit;
   optimize only original supported receiver offsets. Then run the original
   final model, freeing geography, fitted c, clock and timings with its learned
   offsets fixed as usual.

The treatment tests whether independent high-stage timing adjustments contaminate
the offsets later treated as known. It deliberately changes high-stage freedom;
high objectives across conditions are not evidence of better localization. Both
final likelihoods retain the same original mathematical model family, although
their learned fixed offsets and final initial timing vectors can differ. Report
final own-training objective, NLL and frequency RMS separately from post-seal
position error.

Observations, randomized whole-group training assignments, ordered candidate
identities, physical correction seeds, priors, six original proposal-centered
25 km domains and all other final-model options remain matched **within each
parent case**. All fits use fitted c; there is no new zero-c condition. Reused
low and upstream preparation costs are disclosed rather than counted as new
optimizer work. The high treatment's conditional KKT certificate explicitly
states `receiver-offsets-only; low-position-correction-timing-fixed`; it must
never be passed off as a free-timing certificate.

Each condition has at most twelve new calls: six high and six final fits. Across
both conditions this is **at most 24 new calls per case**, with 20 s / 600
iterations per call; a single explicitly named unit gets at most 90 s internally,
105 s external TERM and 110 s KILL. Failed/nonstationary stages remain visible,
stop dependent stages and are excluded from selection. No substitute low donor,
timing clipping, failed retry, reference seed or error-based selector is allowed.
Every condition selects the lowest stationary final objective, then original
start index. If a case's low outcome failed originally, both conditions retain
that own-path failure without a new fit.

The mechanism receives support only if the matched treatment changes the saved
offsets/timing allocation and improves post-seal localization across the fixed
cases while preserving convergence and disclosed budgets. A lower final training
cost alone is a failed accuracy argument. Regression, no accuracy change, or
failure to converge rejects promotion; none permits tuning the timing lock,
choosing a different case or switching models by reference error.

## Implementation and handoff

New files only:

- `src/leo/analysis/model_a_timing_locked_high.py`: original high likelihood and
  gradient, offset-only bounded optimizer, independent conditional stationarity,
  strict unchanged physical vector and timing coverage; standalone own-path helper.
- `tools/ds21_model_a_timing_locked_control.py`: qualified parent dispatch,
  freeze, explicit unit execution and receipt-only aggregate sealing.
- `tests/analysis/model_a_timing_locked_high_test.py` and
  `tests/tools/ds21_model_a_timing_locked_control_test.py`: 30 synthetic tests.

The runner accepts original fitted-v2 or qualified coverage-v1 parents through
their **genuine existing readers**. It does not forge a policy/schema to reuse
the wrong reader. Both retain their original live/archive source checks. The
new protocol also binds original initialization, all six original A terminals,
all six low call receipts, inputs, its own reachable sources and archives.
Sources and parent authorities are rechecked before fitting and before sealing.
Each new high/final fit gets distinct launch/call/termination receipts. The
runner has no held loader. Its separate reference evaluator requires all twelve
scientific units and both selectors to be sealed and verifies development role
before loading the configured reference. Re-freezing an existing namespace
checks its existing source archives before any writes, so missing/tampered
archives cannot be silently repaired.

The coordinator should freeze a new output namespace per case after review:

```text
tools/ds21_model_a_timing_locked_control.py freeze OUTPUT --model-directory PARENT
tools/ds21_model_a_timing_locked_control.py run OUTPUT --unit original-high-repeat-0
tools/ds21_model_a_timing_locked_control.py run OUTPUT --unit low-timing-locked-high-0
...
tools/ds21_model_a_timing_locked_control.py seal OUTPUT
tools/ds21_model_a_timing_locked_control.py evaluate OUTPUT
```

Use coverage parents under
`reports/2026_10_13_ds21_release_readiness/local/coverage-models-v1/DS21-009`
and `DS21-013`. Initial output namespaces belong under this report directory's
`local/model-a-timing-control-v1/`. The coordinator joins configured-reference
error only after the aggregate seal. Dependent low/high stage locations may be
audited, but must be labeled as such; this experiment does not provide
independent CH1–4 and CH5–8 end-to-end qualification.

The focused 30-test suite passed in 1.53 s with the existing scientific Python
environment and single-threaded BLAS. Ruff passes. Tests cover actual original
high objective closure, fixed-vector immutability, conditional versus free
timing stationarity, offset box KKT, strict budgets, source/parent changes before
fitting, qualified provider selection, explicit-unit-only scope, own low reuse,
high/final failures, scientific receipt tampering, missing-stage/orphan refusal,
immutable archive guards, reference access after the complete aggregate seal,
and training objective/tie selection. No original numerical runner/core, public contract,
golden fixture, QNAP path or RF recording was changed.
