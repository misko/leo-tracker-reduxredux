# Conditional 12-recording persistence mechanism pilot

Source preparation only. No protocol is frozen, no membership selection has been
executed on recording metadata, and no positive-rho recording work is authorized
by this document. Parent and independent review precede any freeze or execution.

The conditional trial changes only the final B7 identity-dependence likelihood:
iteration109 marginal-preserving persistence at global `rho=0.5` versus exact
`rho=0`. It is a consumed-development mechanism pilot, not a holdout, a deployment
qualification or a replacement for full148/193 coverage. Iteration108's original
positive-rho transition is not used.

Freeze all 148 potential historical members (63 DS16, 51 DS17, 34 DS18), their
original authorities and the complete numerical source closure. Select four per
dataset by ascending SHA256 of compact JSON `[seed,dataset,session_id]`, breaking
ties by inventory label. The fixed seed is
`position-persistence-pilot110-seed20261009`. Freeze all 148 ranks plus selected12
metadata before any experiment. Selection ignores error, readiness, signal quality,
track coverage and prior result status. Failed selected members are not replaced.
One recording includes both receivers and both calibration arms.

Use ordinary archived iteration85 B7 endpoints reconstructed by immutable108/87
helpers. Freeze iteration108 metadata-only segments: same receiver/channel/exact
RF, positive gaps≤2 seconds, overlap/uncovered independent, all rows exactly once.
Use that identical layout and bank in both c arms. No reference coordinate or
error selects a model, group, start, parameter or winner. The inherited legacy51
loader still compares an archived error for exact provenance equality and binds
reference-bearing document hashes; this admission dependency is disclosed rather
than described as complete reference-field nonaccess.

Each selected member receives four fits, all at frequency width125 Hz, relative
timing sigma2 s, receiver slope bound±60 Hz/s and unchanged B7 satellite/clock
priors. Every fit uses the same archived fitted-B7 physical and clock start,
90-second/600-iteration production fit budget and 25 km local radius. The c=0
fitter locks static c and both RF-time coefficients. The zero-c control can move
from its shared fitted-derived start: report it separately from archived zero-c.

Verify both archived objectives within1e-6 and exact rho0 physical/clock gradient
nesting before fitting. Reuse iteration106's independent finite-value, full KKT
≤0.001, physical-feasibility and clock-bound qualification. Failure preserves the
raw attempt; candidate falls back to qualified same-arm rho0 control, then its
archived B7 arm. Control failure falls back to archive. No cross-model objective
comparison selects winners. All four attempts remain in coverage even with no
eligible persistence links; report such members as mechanistic no-ops.

Before execution the reviewed protocol must state progression criteria. Proposed
accuracy screen: fitted-c mean improves≥5% versus matched rho0, median does not
worsen; neither arm has a paired regression over1 km or increased worst error;
c=0 mean worsens no more than5%; all48 raw fits independently qualify without
fallback. These are conditional pilot screens, not generalization guarantees.
Sequence likelihood improvement alone cannot pass the screen. Report each failure
and every counterexample. Runtime ratios to a converged rho0 endpoint are
descriptive; rho0 frequently stops immediately, so a 2× ratio would conflate
new-model optimization work with steady-state embedded cost. Retain the absolute
90-second fit budget and report actual time/evaluations and memory separately.

Execution after freeze would use `engine.py --label LABEL`, at most two globally
coordinated single-thread workers. There are at most48 attempted fits and no
automatic retries or replacement members. Results/attempts are append-only and
protocol-bound. Reference-based position evaluation occurs only after operational
choices are sealed. No production change, RF collection or reserve access occurs.

The prepared launcher is `controller.py --shard 0|1 --maximum-members N`, with
N between1 and6. Each shard processes alternate selected members sequentially.
An exclusive immutable claim is written before starting a child process. A
claimed member without a terminal receipt is never automatically retried; child
exit/launch errors are retained separately. Valid terminal input/fit failures
remain covered and do not cause replacement selection. The controller reports
all12 statuses, including unlaunched and claimed-without-terminal members. Global
two-worker capacity remains the parent's responsibility.

## Verified inherited fitter semantics

The frozen106 `run_attempt` calls production `hard60_dynamic_rf.fit`, passing
copies of the shared vector/clock and exactly `maximum_seconds=90` and
`maximum_iterations=600`. **600 is an iteration limit, not an evaluation cap.**
The deadline is checked between objective calls; a running call and final
objective/qualification checks can finish after90 seconds. It is not a hard
process wall-clock kill. Actual elapsed time and objective evaluations must be
reported without truncation; optimizer iteration counts are explicitly null
when the production fitter does not return them.

The production parameterization locks static RF coefficient index6 and the last
two RF-time coefficients for c=0, while preserving other physical/clock starts
apart from its ordinary bound-feasibility adjustment. That same adjustment runs
for both models. Clock bounds are±2000 Hz-equivalent coefficients, with fitted
RF-time bounds±1000 and the existing physical bounds/local25 km disk. Returned
states are re-evaluated by106's independent physical and scaled-clock KKT check;
finite objective/gradients, clock feasibility, score decomposition and zero-c
locks are required. Optimizer success alone cannot qualify a result. Reusing
this exact path avoids adding another scientific convergence definition.
