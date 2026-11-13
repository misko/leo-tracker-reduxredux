# Bounded algo07v5 accuracy–speed investigation

All eight paired comparisons and the single bounded weak-track attempt are
terminal. The 16 complete workers exited zero. The separate weak-track attempt
timed out during its permitted numerical retry and qualified no inclusion.

The frozen scope, source/native bindings and exact launch command are in
[the evaluation guide](initial-discovery-evaluation.md#direct-timing-gap-follow-up).
This comparison adds `direct-timing-gap-v1` to fast-v5-zero. It does not measure
speedup against original v3. Both roles use CPU 21, one BLAS thread, matched
inputs and budgets, null inference GPS, and the same frozen scientific source.
DS29 errors use operator roof references, not independently surveyed truth.

## Terminal fresh pairs

| Case | Arm | Baseline → candidate error, m | Frequency score | RMS, Hz | Exact ownership change |
| --- | --- | ---: | ---: | ---: | --- |
| DS26-0263 | c0 | 788.223 → 788.223 | 35800.547 → same | 240.606 → same | None; 3384 owners |
| DS26-0263 | fitted c | 796.515 → 796.515 | 35791.928 → same | 216.267 → same | None; 3384 owners |
| DS29-0126 | c0 | 629.528 → 629.528 | 12922.526 → same | 113.643 → same | None; 1529 owners |
| DS29-0126 | fitted c | 429.243 → 429.243 | 12925.613 → same | 90.583 → same | None; 1529 owners |

| Case | Wall, s | CPU, s | Gap stage, s | Native calls | Native fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0263 | 467.150 → 498.995 | 462.384 → 494.668 | 0.0046 → 60.3679 | 4734 → 6239 | 0 → 0 |
| DS29-0126 | 160.199 → 165.732 | 158.205 → 162.308 | 0.0017 → 0.0018 | 2637 → 2637 | 0 → 0 |

All four workers completed with exit zero. DS26-0263 independently nominated
NORAD 67408 for a 41-point component, but the paired RF gates and exact-replay
verification rejected inclusion. Its audit ran and returned failed verification;
the generic persisted reason `exact replay fails or missing` does not mean the
audit was absent. Direct annotation, inclusion and audit consumed 34.951,
24.163 and 1.234 seconds, respectively, within the 60.368-second gap stage.
DS29-0126 found no qualifying timing component and performed no direct fits.
Both cases preserve exact scientific outputs between roles. Timing differences
in these single contended pairs do not establish repeatable overhead.

The worker owner revalidated public stores, report/request/work receipts,
source/native/provider bindings and archive hashes without numerical reruns.
Evidence is under
`/srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/`:

- `audit-ds26-0263/pair-audit.json`, SHA256
  `3f122af840baa4a432f4a721d760cf5eb79d710aafb973c1dc4e03dd876d1772`.
- `audit-ds29-0126/pair-audit.json`, SHA256
  `b456970d88b01f73f7011a5871ef8498f7a64d2fa8f60b146c8552fad1732bdf`.

## DS29-0399 alternating repetitions

All six workers completed with exit zero. Independent review verified actual
execution order baseline/candidate, candidate/baseline, baseline/candidate,
the public audits, exact owner sets and frozen source/native/provider bindings.
Every role's complete scientific arm dictionaries exactly match its other two
repetitions and the prior development screen. This establishes reproducibility
on one development recording, not independent holdout generalization.

| Arm | Baseline → candidate error, m | Frequency score | RMS, Hz |
| --- | ---: | ---: | ---: |
| c0 | 1269.409 → 377.472 | 16092.020 → 16774.805 | 101.208 → 104.963 |
| fitted c | 1311.255 → 466.076 | 16096.445 → 16776.683 | 78.991 → 87.722 |

Each candidate adds exactly the same 56 target observations as NORAD 66466 in
both arms, retaining all 2010 incumbents unchanged and reaching 2066 owners.
Each physical audit verifies and the production qualification passes. Frequency
scores and RMS above cover different observation sets between roles; they do
not establish a matched-observation frequency improvement. Position accuracy
comes from the separately held evaluation reference.

| Repetition | Order | Baseline wall, s | Candidate wall, s | Baseline CPU, s | Candidate CPU, s |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | B/C | 346.378 | 407.117 | 342.750 | 402.952 |
| 1 | C/B | 352.475 | 387.787 | 348.775 | 384.304 |
| 2 | B/C | 333.496 | 396.490 | 330.496 | 393.453 |

Candidate/baseline wall ratios are 1.17535, 1.10018 and 1.18889, with aggregate
1191.394 / 1032.349 = 1.15406. CPU aggregate is 1180.708 / 1022.021 = 1.15527.
Paired wall overhead ranges 35.313–62.994 s, median 60.738 s; CPU overhead
ranges 35.529–62.957 s, median 60.201 s. These are contended host observations,
not a general latency estimate. Each pair uses 6506 → 8380 native calls,
20 receipts per role, and zero fallbacks. Per-pair audit receipts are under
`direct-gap-followup-001/audit-ds29-0399-r{0,1,2}/` in the experiment root.

Candidate gap stages took 48.791, 48.705 and 50.453 seconds. Their internal
annotation, inclusion and audit totals were 52.338, 93.159 and 2.347 seconds
across all three workers. These durations are already inside whole-worker
clocks. The bound three-repeat summary is
`audit-ds29-0399-repeats/summary.json`, SHA256
`319b21bc0d47cd95424722f7d26ec842384053db9fc16f59e2de7ab88e1c2999`.

## DS26-0002 no-trigger control

All three pairs completed in B/C, C/B, B/C order. Each candidate found no
target and performed no direct annotation, inclusion, audit or native work.
Full scientific arm dictionaries and owner maps match exactly between roles
and across repetitions. Both arms retain 2783 owners with zero additions,
removals or identity changes.

| Arm | Baseline → candidate error, m | Frequency score | RMS, Hz |
| --- | ---: | ---: | ---: |
| c0 | 664.784 → 664.784 | 24156.758 → same | 76.333 → same |
| fitted c | 697.065 → 697.065 | 24165.931 → same | 76.841 → same |

| Repetition | Order | Baseline wall, s | Candidate wall, s | Baseline CPU, s | Candidate CPU, s |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | B/C | 353.911 | 325.832 | 349.882 | 323.969 |
| 1 | C/B | 346.116 | 354.430 | 341.003 | 350.004 |
| 2 | B/C | 342.036 | 340.473 | 340.229 | 338.022 |

Candidate/baseline wall ratios are 0.920660, 1.024019 and 0.995429. Aggregate
wall is 1020.734 / 1042.064 = 0.979531 and CPU is 1011.995 / 1031.114 =
0.981458. Paired wall differences range from -28.079 to +8.313 seconds,
median -1.564 seconds; CPU differences range from -25.913 to +9.002 seconds,
median -2.207 seconds. Opposite signs despite identical numerical work
demonstrate the host variation. The no-trigger check takes 3.049 to 3.403 ms
in the candidates. Every role uses 3087 native calls, 22 native receipts and
zero fallbacks. No repeatable whole-worker timing effect is established.

## Weak-track inclusion decision

**Stop this lever for now.** The one bounded DS26-0102 attempt completed its
primary fit and physical audit but failed the c0 optimizer acceptance gate.
Its permitted Powell retry timed out at 110.003 seconds. No inclusion was
accepted. The unaccepted primary proposal added 33 points without losing
incumbents, but worsened reference error by 12.323 m for c0 and 20.763 m for
fitted c; actual accepted error and ownership changes are zero. Frequency-fit
changes were negligible and mixed. All 1043 native calls activated without
fallback. There is insufficient demonstrated benefit to extend the retry now.

[The independently audited report](weak-track-inclusion-ds26-0102.md) contains
both-arm baseline/control/proposed endpoints and frequency metrics, stage wall
and CPU, explicit incomplete retry accounting, artifact hashes and exact CLI.
Tool/tests are committed as `5bb61e625`; 13 focused tests passed. The report and
stop decision are committed as `6305a0cca` and `f682a2dd8`.

## Decisions and next step

| Lever | Decision | Evidence and next step |
| --- | --- | --- |
| Direct timing-gap policy | Advance to full DS26/DS29 evaluation as an opt-in candidate. | The same 56-owner addition and roughly 0.85 to 0.89 km position improvement reproduce in both calibration arms across three pairs. No accepted scientific change occurred in either fresh recording or the no-trigger control. Full frozen-cohort evaluation is needed to measure benefit frequency, rejected-trial cost and accuracy tails. |
| Weak-track inclusion | Stop for now. | One bounded attempt failed qualification and timed out. Its unaccepted position shifted modestly farther from the reference in both arms, with negligible and mixed frequency changes. A longer retry has no demonstrated benefit for this accuracy–speed objective. |

The direct-gap lever adds accuracy at additional measured cost on DS29-0399.
It does not establish a new speedup relative to original v3. The timings here
use fast-v5-zero as their denominator and are explicitly ineligible as headline
benchmarks because the host was contended. Repetitions reuse one recording;
they do not turn the known development success into independent validation.
The two preselected fresh groups had zero accepted gains. Population-level
accuracy and expected overhead remain unknown.

The next full evaluation should preserve the frozen policy without tuning on
these results. Retain missing members, failures and timeouts. Report paired
c0/fitted-c error distributions, accepted owner changes, frequency evidence
and stage/native work. Continue to keep operator references outside inference.
No new full evaluation, RF collection or default promotion was launched in
this goal. Existing original-v3 and seed-policy services were preserved.

The exact numerical launch is committed in the evaluation guide. The
evidence-only collector `tools/collect_direct_gap_followup.py` revalidates
the frozen scope and all eight pairs without launching inference. Its final
machine receipt is `direct-gap-followup-001/audit-all-eight/summary.json`.
The quiet monitor `tools/watch_bounded_evaluation.py` checks service state
and report coverage every 300 seconds and explicitly leaves scientific
qualification to the collector and public audits. Six monitor tests and
13 weak-probe tests pass. The collector and evaluator suite passes 50 tests,
including four collector tests. Ruff and diff checks pass. The collector is
committed as `be85f8f35`; the quiet monitor is committed as `a6e96f38c`.

## Completion audit and reproducible verification

The evidence-only collector completed successfully. Its machine receipt SHA256
is `7b989c9364746800e39cc1c7f645074308f69f77b1f04f26f05d97907417ceb1`.
Independent review cleared this receipt, the collector and this report against
the underlying evidence. It verifies the four complete manifest terminals,
eight scheduled pairs, 16 unique run identities and output roots, exit-zero
workers and exact per-pair request equality after removing the explicit policy,
schema and run identity fields. Every request keeps zero ordinary recovery
targets and a null inference reference. Actual execution matches CPU 21 and
the declared alternating order. All 332 native receipts bind the same hashed
one-thread provider; 79,427 native calls completed with zero fallbacks.
Public-store inspection, report/request hashes and archive tree bindings pass.

The weak-track failure is separate from those 16 workers and remains an
unsuccessful outcome. Its saved primary fit and audit, StageDeadline receipt,
post-inference reference errors, unchanged accepted owners and unavailable
full-process CPU accounting are retained in the linked weak-track report.
The exact one-attempt scope was not extended.

Regenerate the eight-pair receipt without numerical inference from this
worktree:

```bash
PYTHONPATH=tools:src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  tools/collect_direct_gap_followup.py \
  --root /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001 \
  --scope-sha256 sha256:9fb261f6da6b7ff0ab4531b2ab09afcee4358ab1f4461c824a0bdbc443e324f5 \
  --runner /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-runner-002/tools/evaluate_initial_discovery.py
```

Build the Lever produced the quiet monitor and evidence-only collector.
Model the Domain kept service termination separate from scientific validation.
Prove It Works required their real process/output checks and independent
comparison with public scientific evidence before closing the bounded goal.
