# DS23 DBG01 iteration015: retain the RF-supported parent and diagnose a clean unmatched curve

This bounded iteration builds on [ALGO02](../ALGO02/README.md) and the existing
[ALGO03 family-replacement work](../2026_10_22_ds23_family_cavity_full_assessment/README.md).
On **0273**, composing the already published paired-positive guard with existing
native prediction and the unchanged near-feasible solver gives **727/1040
associated GLRT points (69.90%)** and fitted-c error **2.419 km**, versus
699 points and2.858 km in the reference. The guard's parent-only improvement
was established in iteration011; it is reused, not rediscovered here.

On **0049**, recovering one37-point curve as69500 improves fitted-c error
**2.858→2.123 km**, reaching **64.95%** association. Existing persistent native
prediction adds31 more points and reaches **67.17%**, but worsens fitted-c
error to **2.188 km**. More associations again do not guarantee better position.

We also test a shared event for conflicting additions and a broader nonlinear
phase/alias nomination for a clean29-point unused curve. Both fail the original
final checks and are rejected. **No new ALGO version or full-DS23 policy is
adopted.** The canonical410-scan fitted-c mean/median remain
**1.469461/1.178102 km**. The0.5 km mean-and-median goal remains unmet.

![Local controlled results](figures/iteration_summary.png)

## Scope and controls

These are the next two unclosed cases from the unchanged published error
ranking. Inference cold-starts at the center of the original **25×25 km** box,
**37.906,-122.545**. Evaluation GPS **37.849061591561885,-122.48574968092912**
ranks debug priorities and measures frozen errors only. No satellite, phase,
event or point is selected using that coordinate.

Every comparison includes c=0 and fitted-c using matched observations,
candidate choices, aliases, other priors and fitting budgets. All inference
uses the causal catalogue; following TLEs are diagnostic only. No RF collection,
IQ reprocessing, moving trajectory or stationary-history pooling is used.
Original persisted contracts, point IDs and polynomial fixtures are unchanged.

The current whole-curve, support-aware, point-priority, temporal, curvature,
same-band event and cross-band event rules are reused without tuning. Neither
scan has an eligible isolated single-source step under the original013/014
rule; the corresponding event trials are empty. Extra point-priority and
augmented same-family replacement searches also have no eligible target here.
Those empty outcomes are retained rather than silently changing their scope.

|Scan|Method|Associated /all GLRT|Associated %|Curved /predictive likelihood points|c=0 error km|Fitted-c error km|
|---|---|---:|---:|---:|---:|---:|
|0273|Incumbent /graph fallback|699/1040|67.21|649 /50|2.868521|2.857551|
|0273|Persistent native, incumbent parent|727/1040|69.90|649 /78|2.904029|2.856950|
|0273|Existing011 guard parent|699/1040|67.21|649 /50|2.502659|2.487656|
|0273|Guard + constrained native|727/1040|**69.90**|649 /78|**2.558874**|**2.419087**|
|0049|Incumbent|873/1401|62.31|766 /74|2.573557|2.857535|
|0049|Whole-curve graph recovery|910/1401|64.95|803 /74|1.967994|**2.122928**|
|0049|Persistent native, graph parent|941/1401|**67.17**|803 /105|**1.907778**|2.187521|

0049 has33 post-fit associations outside the likelihood in these rows. They
are counted once in association coverage, not described as additional position
measurements. Its guard rows in the full table reuse the unchanged graph parent
and existing temporal results. They do not represent additional fits or gains.
The [full table](tables/position_and_association.csv) includes both arms,
fragment counts, points/fragment, RMS, strict phase checks and original IDs lost.

## 0273: reuse the existing guard, then preserve parent residual checks

There are no wholly unused actively curved sources for the graph reentry
budget. The longest remaining whole sources are short, noncalibrating tracks:
RX1 CH1 T002(14 points/19.94 s), CH4 T005(16/13.98 s), and CH3 T002(14/13.77 s).
Their leading matched causal phase-only profile RMS values are approximately
138.71,200.29 and175.19 Hz. Following elements change these only modestly.
Low single-source RMS alone does not establish a unique identity.

![Longest unused sources and TLE diagnostics](figures/DS23-0273_unused_track_TLE_diagnostics.png)

The existing family replacement **59651→57955** has normalized RF gains
**+0.3374 in c=0 but−1.3973 with fitted c**. Iteration011's predeclared
paired-positive guard therefore keeps59651. It preserves the original699
associated IDs and improves fitted-c error to2.487656 km. This result and its
full410-scan context are already published in
[iteration011](../2026_10_22_ds23_dbg01_iteration_011/README.md).

We now reuse that RF decision before native temporal discovery, with the same
19 permutation controls, identity/alias tests, original noise powers, priors
and cold-fitting budgets. The original guarded-parent native fit proposes28
persistent predictive points but initially fails: the existing22-point
RX2 CH4 /62115 calibration source moves from slope z **2.9833** to
**3.0168>3**. A good new path is insufficient if an original source becomes
incompatible. The unconstrained result is rejected.

Its minimum normalized gate slacks are **+0.03479 and−0.00561**, within the
existing−0.25 refinement trigger. The unchanged solver uses five phase rounds,
40 steps, the original gates and a0.01 numerical margin. It retains the same28
new points and all original IDs. The62115 slope becomes **2.9700**, RMS121.67 Hz,
and lag-one correlation0.487. No threshold is relaxed and no source is removed.

![Original-source retention before and after constrained recovery](figures/DS23-0273_guard_parent_retention.png)

The qualified result gives727 points and2.419087 km fitted-c error. Relative to
the existing guard alone, fitted-c improves by68.6 m but c=0 worsens by56.2 m.
Both remain better than the published incumbent. This distinction is important:
the composition is a local result, not evidence that the extra points improve
every calibration arm or the full dataset.

## 0049: recover one supported curve, retain the conflicting alternatives

The longest unused RX1 CH2 T003 curve contains37 points over39.79 s. Its69500
nomination passes the original paired fit and is selected by the existing
added-point ordering. Another RX1 CH4 T003 curve has24 points over28.04 s and
passes independently as67807. Their61-point union fails, including a4.005 step
statistic on69500, a slope just above3 on67807, and a quadratic screen on an
original source. Individually passing additions need not be mutually compatible.

The selected37-point recovery reduces fitted-c error by734.6 m and c=0 by605.6 m.
Persistent native prediction adds31 points but worsens fitted-c accuracy by64.6 m
relative to that graph parent. The independent native control adds18 points and
gives2.215778 km fitted-c error, also worse than the graph parent. Neither is
selected using GPS.

![Unused evidence after graph recovery](figures/DS23-0049_graph_recovery_unassociated_GLRT.png)

### Shared-event control for the failed union

A bounded extension considers only the largest failed union of additions that
already passed individually. One of its new components must fail only the step
screen in both arms. Both the target and original-parent witnesses must pass
the existing every-single-deletion curvature rule. Witnesses exclude **all**
newly added families, preventing the two new curves from validating each other.

The resulting RF split is near25.720 s. We test one shared band event and one
shared receiver event, retaining the300 Hz prior and a search penalty covering
the inspected trial count, source splits and two event kinds. Each event has a
fresh identical-mask unconstrained null with matched five-round/48-step budgets.

Both event alternatives have **negative RF gains**, approximately−0.803 in c=0
and−0.950 with fitted c. The67807 source still fails its slope screen. Neither
event is accepted. This conflict is not explained by the tested shared jump.

![Failed joint-curve event control](figures/DS23-0049_joint_curve_step_control.png)

## A clean29-point curve remains unmatched

RX2 CH3 T001 spans **218.527–247.347 s**. Its29 measurements follow one
persisted cubic with graph RMS **36.30 Hz**. This is not an isolated-endpoint
curvature artifact: linear RMS remains above **1270.28 Hz**, and quadratic BIC
gain above **132.45**, under every single-point deletion. The observed source
is smooth and has distributed active curvature. One persisted piece does not,
by itself, establish the entire construction history; these diagnostics find
no unsupported endpoint or visible discontinuity in its retained measurements.

The ordinary56030 joint fit fails large smooth residual structure, with slope
z about5.28, quadratic BIC gain about187 and lag-one correlation about0.90.
The original-pool causal/following profile for56030 changes only
**1059.21→1058.11 Hz**. A nearby following element does not repair that tested
model discrepancy. This is a limited diagnostic pool, not a claim that every
possible following element or catalogue identity has been exhausted.

![CFO, graph polynomial and rejected causal joint predictions](figures/DS23-0049_hard_curve_CFO_and_residuals.png)

### Test nonlinear phase and alias choices jointly

The original coarse screen chooses an integer alias near the prior mean and
uses a linearized, moment-Gaussian phase approximation. To test whether that
screen omitted the correct hypothesis, the prototype evaluates **every causal
candidate at121 nonlinear phase values from−15 to+15 s**, proposing the nearest
alias at each phase. It integrates the original Gaussian or finite-variance
Student phase prior with trapezoidal quadrature and full held-source radio
covariance. This is a nomination score, not a calibrated identity probability
or a complete wrapped likelihood.

The best seven candidates, plus the old best/original nominee when needed,
then use the unchanged physical-mode refiner. Only the best phase-qualified
refined nominee receives a new matched cold joint position fit. No phase limit,
physical prior, visibility condition or final residual threshold is widened.

![Nonlinear phase/alias proposals](figures/DS23-0049_joint_phase_alias_search.png)

The new screen proposes68912 strongly on its nonlinear grid; after the original
physical-mode refinement,62563 is the best qualified nominee. A separate
**matched linearized control at the identical graph parent, position, radio
posterior and candidate refiner** still selects56030. Common candidate/alias
scores replay exactly, so the changed proposal is not merely a change of parent
calibration. The prototype also changes the phase-integration approximation;
it is not an isolated ablation of alias selection alone.

![Matched proposal-screen comparison](figures/DS23-0049_matched_proposal_screens.png)

The62563 joint fit nevertheless fails. Its fitted-c source profile RMS is
about2306 Hz, slope z5.268, quadratic BIC gain188.98 and lag-one correlation0.905.
It is rejected. The broader search changes nominations but does not supply a
supported identity or explain this curve under the current physical/radio
model. Its satellite remains **unresolved**; a smooth polynomial is not sufficient
reason to force an association.

## Loss surfaces, ablations and coverage limits

DBG01 retains the 10 km loss/gradient maps, loss decomposition, family and
track ablations, prior controls and81 independent starts per scan. All81 final
restart records per scan pass their compatibility checks. Best RF gains are
only1.08×10⁻⁹ and3.37×10⁻⁸, below the2log4 restart penalty. No restart is adopted.
These starts do not reveal a better minimum under the incumbent model.

Purple diamonds are intermediate phase-round endpoints; orange X marks final
five-round endpoints. Red points are independent starts. Curved labels/aliases
can change within the bounded c=0 hypothesis bank; fitted c follows that
schedule, while original predictive labels stay fixed. Loss-map pixels evaluate
the recorded conditional model rather than rerun acquisition, GLRT and discovery.

![0273 loss and gradient](figures/DS23-0273_loss_gradient_10km.png)
![0273 independent starts](figures/DS23-0273_convergence_10km.png)
![0049 loss and gradient](figures/DS23-0049_loss_gradient_10km.png)
![0049 independent starts](figures/DS23-0049_convergence_10km.png)

The lowest paired-valid family-deletion errors are2.460 km after deleting58389
in0273 and1.460 km after deleting59535 in0049. These are GPS-evaluated diagnostics,
not deletion policies or proof of wrong satellite identities. They show remaining
model tension even after some missing evidence has been recovered.

The original graph covers only **758/1040 (72.88%)** in0273 and
**1094/1401 (78.09%)** in0049. Reaching90% requires at least **178 and167**
outside-graph measurements, respectively. Graph-only recovery cannot meet that
target. Native prediction helps, but its residual and identity checks remain
necessary and its accuracy effect must be evaluated separately.

Gray in the GLRT figures means **all original measurements as context**. Red
highlights unused points; colored curves are corresponding graph polynomials.
Polynomial samples are display-only and are never counted as measurements.

![0273 unused evidence after qualified guarded recovery](figures/DS23-0273_guard_temporal_policy_unassociated_GLRT.png)
![0049 unused evidence after persistent recovery](figures/DS23-0049_persistent_temporal_unassociated_GLRT.png)

## Validation, evidence and decision

All13 standard stages pass. Independent validation checks **482 standard
endpoint arms and21 nomination densities**, plus **24 additional endpoint arms**
covering native controls, guarded parents, constrained recovery, matched event
nulls and rejected phase/alias fits. Seven nonlinear-grid nominee scores receive
an independent dense-covariance and Student-density replay; the maximum score
difference is **3.28×10⁻¹¹**. Accepted measurement IDs and all original gates
replay. Nine component-owned tests pass, including phase quadrature normalization,
phase-dependent alias proposals, guarded selection and the original feasibility
trigger. Rejected fits are preserved and are never included in coverage gains.

The source snapshot and raw protocols reconstruct the bounded experiments:

1. `run_ds23_dbg01_iteration_015.py --batch` runs standard DBG01 and graph recovery.
2. `probe_ds23_iteration015_recovery.py --stage ...` reuses the existing diagnostic,
   native, feasibility, extra-curve, event and source-integrity rules. Empty
   eligible sets remain explicit outputs.
3. `probe_ds23_iteration015_guard_parent.py` reuses the frozen011 RF guard;
   `probe_ds23_iteration015_guard_feasibility.py` applies the original solver.
   0049's unchanged-parent results are copied, not refitted.
4. `probe_ds23_iteration015_joint_step.py` tests the failed-union event hypothesis.
   `probe_ds23_iteration015_joint_phase_alias.py` tests broader causal proposals;
   `diagnose_ds23_iteration015_linearized_control.py` supplies the matched screen.
5. The two015 audit scripts independently replay the completed results.
   `report_ds23_dbg01_iteration_015.py --finalize` assembles already-rendered
   figures, late controls, sources and evidence without new position fitting.

Use the existing virtual environment, BLAS threads set to1,
`PYTHONDONTWRITEBYTECODE=1` and
`PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`. Frozen outputs are preserved
rather than overwritten by scientific runners. The standard batch has an
1800-second wall cap; separate bounded experiment caps are in their protocols.

The [46-figure gallery](FIGURES.md), [positions and coverage](tables/position_and_association.csv),
[all trials](tables/prototype_trials.csv), [all curved gates](tables/all_curved_gates.csv),
[family ablations](tables/family_ablations.csv), [retention gates](tables/guard_retention_gates.csv),
[event controls](tables/joint_step_models.csv), [proposal candidates](tables/joint_phase_alias_candidates.csv)
and [matched screens](tables/matched_proposal_screens.csv) are included.
The [source hashes](evidence/source_hashes.json), [standard audit](evidence/independent_iteration_audit.json),
[extended audit](evidence/extended_endpoint_audit.json),
[guarded solver audit](evidence/guard_constrained_independent_replay.json) and
[five raw archives](evidence/archive_manifest.json) bind the inputs and outputs.

No full-DS23 accuracy gain or new-location generalization is claimed for015.
The [completed-deadline policy](../2026_10_23_ds23_completed_deadline_assessment/README.md),
the011 guard and earlier shared-event studies remain separate provisional
results. Close this batch after these controls and continue to **0386/0409**.
Revisit the unresolved29-point source only for a new transferable hypothesis;
do not tune it to evaluation GPS or relax its gates to reach an association quota.
