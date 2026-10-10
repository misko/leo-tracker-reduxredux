# Qualification observations before accuracy evaluation

These are live numerical-receipt diagnostics, not position-error results or an
interim change to the frozen protocol. No reference coordinates were read.

The first two members completed both discovery policies and have qualified
selected endpoints in both final c arms. Native discovery discarded one of
its three retained regions for each member:

| Member | Region | Coarse projected stationarity | Evaluations | Stop reason |
|---|---|---:|---:|---|
| DS16-020 | retained-1 | 0.005058657936181987 | 217 | optimizer-success-returned-state-nonstationary |
| DS16-024 | retained-0 | 0.001462414863690073 | 134 | optimizer-success-returned-state-nonstationary |

Both states were feasible. Their discovery and free-c audits agreed because
these were already fitted-c discovery states. The handoff returned
`discovery-unqualified`, with no nonlinear promotion or Newton polish attempted.
All three zero-led retained regions qualified in both members. This establishes
a difference in retained-region availability, not a localization advantage.

The frozen 150 transition first requires qualification under the discovery arm;
only an admitted state can receive free-c promotion. Thus the existing bounded
promotion repairs changing the c constraint, but does not repair an already
unqualified coarse optimum. Increasing the coarse evaluation limit alone is
not shown to help: these receipts explicitly report optimizer success followed
by a failed independent stationarity check.

A possible successor is one uniform, bounded fixed-position repair for every
retained region that fails its discovery-arm qualification, preserving that
arm, before the unchanged free-c transition. It must preserve originals, use
the same budget/rule for both discovery policies, requalify independently and
retain failures. This is a hypothesis only. No retry, new fit, region-selection
change or relaxation of the qualification threshold has been performed. Finish
151 before deciding whether this extra work is warranted across its full panel.

## Independent receipt/source review

An independent read of only these four completed native/zero member receipts
confirms the table and all eight qualified selected final endpoints. Both rejected
native states are feasible and their two audits are identical. In
[150 transition.py](../2026_10_10_position_error_iter150/transition.py),
`if not own['qualified']: return receipt` occurs **before** bounded promotion.
Their missing nonlinear/polish attempts are therefore deliberate frozen-policy
behavior, not an exhausted repair budget or an exception hiding a repair.

All six zero-led states pass their own constrained audit, fail the free-c audit,
and receive the nonlinear promotion. One of those six also receives the optional
polish; all six handoffs subsequently qualify. The constrained zero-c audit omits
the locked static-c derivative. Releasing that constraint introduces a new
stationarity requirement, so a large free-c gradient does not mean the original
zero-c fit falsely claimed convergence. Conversely, the two rejected native fits
have no model/constraint change to explain their failed own-arm gate.

The same conditional rule is applied to both branches, but it supplies different
repair opportunities: qualified zero-c states may receive extra work when c is
freed, while unqualified fitted-c states receive none. Consequently this pilot
compares discovery **plus its arm-dependent admission/continuation consequences**.
Any eventual position difference cannot be attributed solely to grid coverage or
to a better geometric basin from these receipts. No position errors were read for
this review, and retained-region availability is not an accuracy measurement.

The smallest general successor would preserve the sealed search and retained
three regions, then add one bounded fixed-position attempt for **any** retained
state failing its own discovery-arm audit. Use the original state and its original
arm, the same predeclared 5-second/200-iteration budget and physical constraints,
and the unchanged independent 0.001 gate. A failed attempt remains rejected; a
qualified result proceeds through the unchanged free-c transition. Preserve the
original and replacement receipts separately, and never rerank the completed
discovery queue using repaired scores. Applying this rule to both arms avoids a
special retry for these two labels. It remains conditional on full-panel review
and a separately frozen experiment, with additional cost and regional availability
reported alongside matched final c results.

Do not blindly reuse iteration 102's polish for a zero-c discovery repair: its
current qualifier constructs a fitted-c problem. The proposed minimal own-arm
bounded attempt needs no extra polish; adding one later would require an explicit
arm-aware implementation and separate review. No code, model call, fit, test,
reference query or change to the live 151 protocol was performed in this review.

## Returned best state is not necessarily the optimizer endpoint

Further source inspection narrows the diagnosis. Coarse discovery uses
`regional_position_fit.fit_position`, which returns its best feasible objective
evaluation, with a gradient-norm tie-break within 1e-9. It does not necessarily
return `result.x`. Its optional diagnostics separately audit the terminal state,
but the 116 point adapter used by this pilot does not request those diagnostics.
The independent qualification in the saved point receipt concerns the returned
best state.

Therefore `optimizer-success-returned-state-nonstationary` proves a mismatch
between the success flag and the returned state's stationarity. It does not
prove that the optimizer endpoint was itself nonstationary. Neither those
terminal vectors nor terminal audits can be reconstructed from these receipts
without a new experiment. Do not describe premature solver convergence as an
established root cause of these two specific coarse failures.

The newer `hard60_bounded_fit.fit_bounded_position` separately preserves
terminal/best diagnostics and prefers independently stationary recorded
candidates. That makes the proposed retained-state repair materially different
from merely extending the original coarse iteration cap. It still needs a
matched experiment; no replay or source change to either fitter was performed.

## Full sealed pilot: five own-arm rejections

After all twelve members completed, the terminal receipts showed five retained
states rejected at the own-arm gate. All five were independently physically
feasible. The fixed stationarity threshold is 0.001; it is not relaxed for the
proposed successor.

| Member | Discovery | Retained index | Own-arm stationarity | Recorded evaluations |
|---|---|---:|---:|---:|
| DS16-020 | fitted-c | 1 | 0.005058657936181987 | 217 |
| DS16-024 | fitted-c | 0 | 0.001462414863690073 | 134 |
| DS17-006 | zero-c | 0 | 0.0013216694684525798 | 143 |
| DS17-015 | zero-c | 0 | 0.0010243060775137203 | 235 |
| DS17-027 | zero-c | 1 | 0.001773898802822943 | 234 |

Every returned state records `optimizer-success-returned-state-nonstationary`.
The terminal-state limitation above applies to all five. Their fitted-c audits
are not interchangeable with the own-arm gate: the three zero-c states have
free-c stationarity residuals of approximately 504.891, 494.380 and 359.176,
respectively. The first question is whether bounded optimization in the original
arm qualifies the same fixed-position state; promotion into fitted-c is the
separate, unchanged next step.

These observations come from preserved terminal handoff receipts, without new
model evaluations. They motivate a uniform same-arm repair rule over the whole
sealed panel, not per-scan changes based on position errors or looser stopping
tolerances. Any accuracy effect still requires the matched successor experiment.
