# Independent review of the bounded ALGO03 fast-scan adapter

This review found and reproduced a missing numerical-completion gate for shared
families, verified its adapter fix, and identified a difference between the
shadow evaluation path and the proposed production path. **The full candidate
must use the same production wrapper, recovery budget, and final proof checks
before its results can support a deployment decision.** This report makes no
full-cohort performance or promotion claim.

The reviewed scientific release is **ALGO03-2026-10-30-r1**. Its exact
[scientific manifest](../ALGO03/releases/2026-10-30-r1/manifest.json) SHA-256 is:

```text
6dd58bbbe5e7d1f881c820edf0bee0345952a365553afaf37f457dfcec189545
```

All **29 scientific source hashes** in that manifest were checked and match.
The qualification fix is in the adapter; those frozen numerical sources were
not changed. [review-snapshot.json](review-snapshot.json) records the reviewed
adapter/test hashes, scope authorities, and validation result. It describes this
review snapshot; subsequent wrapper integration needs its own executable freeze.

## Current scope: 400 fast-recording evaluation rows

The user's explicit fast-only amendment applies to the comparison and deployment
gate. Its authority is
[promotion-scope-amendment-2026-10-30.json](../ALGO03/promotion-scope-amendment-2026-10-30.json).
Input availability at this review is:

| Dataset | Fast members | With an input | Missing input, retained |
|---|---:|---:|---:|
| DS23 | 207 | 204 | 3 |
| DS24 | 34 | 25 | 9 |
| DS26 | 159 | 158 | 1 |
| Total | **400** | **387** | **13** |

These are membership and input counts, not successful-position counts. Every
missing, failed, unavailable, timed-out, and fallback result stays in the
coverage ledger. Adaptive acquisitions are excluded from this comparison and
production-v2 admission. Acquisition manifests establish fast mode; a public
tracking export's compatibility label can say `adaptive` for a fast acquisition
and must not redefine its recording mode.

DS26's separately sealed authority retains all 317 recordings. Its
[fast-only evaluation membership](../2026_10_30_ds26_all_new_recordings/fast-only-evaluation-membership.json)
selects the 159 fast members without rewriting that authority. Late-ready
DS26-0317 is included; incomplete DS26-0172 remains unavailable. The
[DS26 capsule](../2026_10_30_ds26_all_new_recordings/README.md) was published to
`main` in commit `ff9fd1de8`.

## Findings and fixes

**Shared-family numerical qualification — fixed and tested.** The frozen shared
inclusion script's `paired_valid` flag checks physical residuals, retained
observations, and phase stability. Its exact replay does not independently
require the position optimizer to finish. Consequently, the adapter initially
admitted a shared-family trial even when a matched control or addition had an
unqualified final numerical fit.

The adapter now checks the final fit for **both control and addition, in both
`c0` and `fitted_c`**. If a `success` field exists, it must be exactly `true`.
Otherwise the bounded Gauss–Newton result must report
`stopped = small_step_and_improvement`. An iteration cap, an unaccepted damped
step, a missing completion record, or an explicit failure is rejected. This
adds a completion requirement without relaxing any physical or ownership gate.

**Evaluation/production equivalence — required before full freeze.** The reviewed
dataset runner launched the shadow worker with a 1,200-second recovery budget
and checked its process read audit. The production wrapper reserved 30 seconds,
passed 1,170 seconds to recovery, and then called `verify_selected` and validated
the v2 terminal envelope. Near a deadline, that budget difference can change
which target or joint fit completes. Different final proof paths can also give
different admission decisions. The complete fast comparison must invoke the
same production entry point and final proof checks; the earlier shadow path is
not an exact-deployment evaluation. Integration was still a freeze requirement
when this review was sealed.

**Published-support accounting — corrected.** The historical four-canary report
first counted 29 unreported post-fit extrapolations in C3's baseline and unchanged
shadow output. The corrected published-support count is **3,790 / 5,298 =
71.54%**, rather than 3,819 / 5,298 = 72.08%. That correction changes neither
the historical endpoint nor its recovery decision; the original execution
evidence remains preserved.

The current ownership proof starts from the exact IDs in the qualified ALGO02
terminal. For older v1 track gates without a NORAD field, it obtains ownership
from an objective-verified replay of the original model. Explicitly published
NORADs must agree with that replay. Unreported post-fit IDs are recorded
separately and receive no recovery credit. A selected result may publish only
the original terminal support plus its explicitly scored targets, with the
same owners in both calibration arms.

The [earlier canary figure](../2026_10_30_algo03_automatic_shadow/figures/canary_comparison.png)
is **historical only**: it describes the earlier two-target adapter and its
corrected accounting. It is not evidence for the current eight-target adapter,
the full 400-row comparison, or deployment superiority.

## Gates, identity, and inference separation

Target selection requires the same unused observation IDs in both calibration
arms. It ranks by native point count and stable track ID, without position error.
Partial graph targets reconstruct the exact parent observations unused by both
arms; the original graph and measured values remain unchanged. Partial and
shared-family targets remain individual alternatives in this release.

A joint alternative requires two individually qualified native new-family
trials, distinct satellite families, and disjoint target IDs. It uses one joint
RF likelihood with shared receiver covariance, not a sum of separate position
solutions. Matched controls, both calibration arms, exact incumbent orbit gates,
target physical gates, phase checks, and ownership replay must qualify. The
published owner map is restricted to the scored support.

New-family Powell retries are selected by numerical failure after the RF,
ownership, and phase guards pass. A joint retry additionally requires the full
matched control/factorized/joint diagnostic in both arms; a physical or phase
failure does not authorize the retry. The control and addition receive matched
optimizer settings. No retry or target choice uses evaluation geography.

Annotation uses three distinct timestamp-selected randomized physical-block
holdouts, 12-second blocks, and two-second guards. Training uses predeclared
150 Hz point noise and unit family powers rather than full-data learned RF
weights. The holdout sets overlap, so they are not independent replications.
Evidence remains conditional on the existing graph, incumbent identities, and
bounded competitor search.

The reviewed selection and inference paths contain no GPS-based ranking or
initialization. They use the original 25 km regional box centered at
`(37.906, -122.545)` and its declared regional starts. Evaluation truth, including
the separately confirmed DS26 site, belongs to the evaluator only. Existing
causal catalogues and priors are copied from the qualified baseline; later TLEs
are not introduced. Read guards confine scientific children to the isolated
analysis export, current recovery artifacts, and executable dependencies.

Every large localization comparison must retain the matched **`c = 0` versus
fitted-`c`** ablation: identical observations, candidates, other priors, and search
budgets. Frequency-fit/score changes and position accuracy must be reported
separately. Scores from different observation sets are not directly comparable
evidence of improved localization.

## Runtime behavior and remaining limits

The adapter considers **at most eight** commonly unused native or partial
targets and selects at most one joint alternative containing **two distinct new
families**. It does not jointly combine partial targets, shared-family additions,
or same-family additions. It selects one deterministic RF-qualified alternative;
individual recovery counts or endpoints cannot be added together.

Discovery has a soft 600-second threshold, individual subprocesses are capped at
600 seconds, and the production wrapper reserves proof/sealing time within its
declared recovery budget. The discovery threshold is checked between targets;
it does not guarantee every selected target is assessed or guarantee time for a
joint fit. Actual source-export, baseline, recovery, proof, and total runtimes
must be accounted for in the final comparison.

A timed-out scientific child can be killed before its exit-time read receipt is
written. The outer audit requires a receipt for every launched Python process.
Thus one later timeout can invalidate an otherwise completed earlier single
candidate and force exact ALGO02 fallback. This is deliberate conservative
behavior: the review does not recommend weakening the read proof to retain that
candidate. Timeouts, incomplete searches, skipped targets, and fallbacks must
remain visible in the final ledger.

The search is bounded and heuristic. Conditional predictive identity support and
local numerical/phase checks are not an exhaustive catalogue search, a proof of
a global position optimum, or a calibrated cross-site accuracy guarantee.

## Validation and disposition

The shared-completion failure was reproduced before the fix: **20 rejecting
fixtures failed and five positive/scientific-rejection controls passed**. After
the adapter fix, the existing six shadow tests and 25 new admission cases pass:

```text
31 passed in 1.66s
```

Reproduction command:

```bash
PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -m pytest -q --tb=short \
  tests/tools/test_algo03_shadow.py \
  tests/tools/test_algo03_shadow_qualification.py
```

The [new qualification tests](../../tests/tools/test_algo03_shadow_qualification.py)
cover every control/addition arm, failed optimizer status, both Gauss–Newton
failure stops, missing completion, explicit-failure precedence, both accepted
completion forms, and scientific-stage rejection. The independent review found
no additional confirmed unsafe gate or identity omission in the reviewed path.

Proceed to a full candidate freeze only after production/evaluation wrapper
equivalence and its end-to-end canary are verified. Apply the unchanged
[promotion criteria](../ALGO03/promotion-criteria-2026-10-30.json) under the explicit
fast-only scope, retaining every denominator and both calibration arms. A
scientific pass must still be followed by the required operational, contract,
staging, and installed-canary gates. This review alone authorizes no performance
claim or deployment decision.
