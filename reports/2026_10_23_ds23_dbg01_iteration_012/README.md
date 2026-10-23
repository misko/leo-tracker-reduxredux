# DS23 DBG01 iteration012: recovered curves, false endpoints and coverage tradeoffs

Building on [ALGO02](../ALGO02/README.md) and the existing
[ALGO03 family-replacement work](../2026_10_22_ds23_family_cavity_full_assessment/README.md),
this bounded batch investigates **0215 and0281**. Support-aware whole-curve
recovery improves0215 fitted-c position error **3.049→2.637km**. Two independently
curved short sources improve0281 **3.032→2.813km**. Both gains also appear with
c=0. These local results do not establish a full-DS23 improvement.

More association is not consistently more position information. In0215, the
existing persistent temporal method raises coverage to **76.12%**, but moves
away from the better graph-parent solution to2.939km. A newly isolated14-point
curved core passes all final checks but also fails to improve its graph parent.
Keep the separate outcomes visible; no new ALGO version or dataset-wide policy
is promoted. Close these cases for now and move to **0234/0064**.

![Matched bounded results](figures/iteration_summary.png)

## Protocol and scope

The frozen batch began on2026-10-22; this report was completed on2026-10-23.
Its raw evidence remains in the original iteration012 output root. The
incumbent is the unchanged410-case family-replacement benchmark, fitted-c
mean/median **1.469461/1.178102km**. Iteration011's paired-positive RF guard
remains provisional:1.462402/1.167197km, only two changed previously studied
cases, unchanged coverage and time-block intervals reaching zero. It is not
silently included here. The **0.5km mean-and-median goal remains unmet**.

New final fits cold-start at[0,0] in the same **25×25km regional box centered
37.906,-122.545**. The catalogue is causal. GPS
37.849061591561885,-122.48574968092912 is used for debug ranking and report-only
accuracy, never nomination, association or policy choice. Following TLEs are
diagnostic only. No new RF collection, IQ reprocessing, moving-trajectory model,
manual satellite selection or stationary-position pooling is used.

Both c arms share observations, candidates, aliases, noise powers, other priors,
gates and search budget. Calibration sources must have distributed active
curvature; linear evidence stays predictive. Additional whole-short or derived
core sources are explicit experimental views, not edits to persisted graph
contracts. No incumbent likelihood observation or associated point ID is lost.
See [batch protocol](evidence/protocol.json) and the complete raw archives.

## Matched position and original GLRT association

The variants below are **separate policies from the same graph parent**.
Their added points are not summed into an untested combined pipeline. The core
column falls back to the graph parent when no qualified core exists.

|Scan|Method|Associated / all GLRT|Associated %|Curved / predictive likelihood points|c=0 error km|Fitted-c error km|
|---|---|---:|---:|---|---:|---:|
|0215|Incumbent|1166/1667|69.95|1109 /57|3.181603|3.049038|
|0215|Support-aware graph recovery|1193/1667|71.57|1136 /57|**2.822418**|**2.637363**|
|0215|Persistent temporal|1269/1667|**76.12**|1136 /133|3.181272|2.939255|
|0215|Whole short curves|1225/1667|73.49|1168 /57|2.922134|2.666405|
|0215|Source-owned curved core|1207/1667|72.41|1150 /57|2.894058|2.656649|
|0281|Incumbent / graph parent|1015/1419|71.53|946 /69|3.064638|3.032285|
|0281|Persistent temporal|1072/1419|**75.55**|946 /126|3.003928|2.965946|
|0281|Whole short curves|1047/1419|73.78|978 /69|**2.856673**|**2.813371**|
|0281|Source-core fallback|1015/1419|71.53|946 /69|3.064638|3.032285|

All exact numbers, associated fragment counts, points/fragment and RMS are in
[position/association CSV](tables/position_and_association.csv). Every
passing and rejected trial is retained in [prototype trials](tables/prototype_trials.csv)
and [all curved gates](tables/all_curved_gates.csv). Low RMS and high coverage
are evaluated separately from geographic accuracy. For example,0281's short
policy improves geography while its c=0 curved RMS slightly rises
149.674→150.432Hz. Neither quantity substitutes for the other.

## 0215: one recoverable whole source, two structurally inconsistent sources

The longest unused **RX2 CH1 T003** has27 points over18.585–46.623s and one
persisted cubic piece. Causal search nominates66582. The default final fit has
noise-like conditional residuals(~151Hz), but fails the existing family-support
logic. The already available support-aware recovery passes all original gates,
adding27 calibration points without a new prior or threshold. Fitted-c error
falls to2.637km and c=0 to2.822km. This is the useful local gain.

The nearby **RX2 CH2 T005**,15 points over24.536–47.004s, also nominates66582,
but fitting the whole source leaves about1.54kHz residual RMS and quadratic
residual BIC gain≈52.5. Same-RX, actual-overlap RF-normalized polynomial
comparison permits separate affine terms for band shifts and small linear
drifts. It favors **independent curvature by58.90 BIC units**: shared degree4
RMS354.05Hz versus independent degree2 RMS148.90Hz. This test uses neither GPS
nor a TLE. Merely adding a constant or linear band term cannot explain that
particular curvature disagreement within this diagnostic model.

The existing persistent path accepts13 of the15 source points after the
9.62s gap, plus other native points, under66582. The first two source points
remain unused. At the fixed fitted-c graph-parent radio/orbit prediction their
residuals are approximately−4523/−4590Hz. This is much larger than the later
source residuals. Those early points are inconsistent with the recovered
family under the tested model; two points alone cannot establish another
satellite identity. We do not force them into a different family.

The13-point later core is **not independently curved**: its minimum linear
RMS under single-point deletion is134.49Hz and minimum quadratic BIC gain
−0.21. The full source's apparent curvature is partly explained by the gap and
incompatible early observations. It remains predictive evidence and is not
promoted into radio calibration to manufacture a larger point count.

![Source CFO, causal orbit-plus-radio prediction, residuals and leverage](figures/DS23-0215_source_endpoints_and_predictions.png)
![Same-RX curvature diagnostic](figures/DS23-0215_overlap_curvature.png)
![Longest unused sources, causal/following element profiles](figures/DS23-0215_unused_track_TLE_diagnostics.png)

The native CFO panel retains the GLRT's actual alias gauges. Lines break at
alias changes; isolated expected samples are marked. A display discontinuity
between gauges does not supply an extra datum or a new polynomial fragment.
The prediction is causal satellite Doppler plus the frozen graph-parent radio
terms, not a free polynomial refit of each displayed section.

### A high-leverage endpoint in RX1 CH3 T006

This15-point source covers253.746–280.161s. Its first point is separated by
**9.7598s** and has **0.9181 leverage** in the stored degree2 fit. The graph RMS
is only137.1Hz, yet the causal66525 phase-only diagnostic RMS is685.0Hz;
following elements give679.6Hz. A good polynomial fit is insufficient evidence
that all points share the same physical trajectory.

The frozen persistent path contains14 of these source points plus three
outside-source detections. An earlier core adapter required the entire path
to be an all-but-one subset of one graph source, so those additional detections
prevented it from recognizing an otherwise eligible source core. The bounded
prototype intersects the already screened path with exact source IDs **before
new fitting**, then applies the existing rules unchanged:

1. One omitted endpoint only; its gap is at least5×median native cadence and
   its original polynomial leverage is≥0.9.
2. At least12 points and10s of retained source data.
3. Nonlinear amplitude≥250Hz and quadratic-over-linear BIC gain>10 survive
   every single-point deletion. No deletion is used to fit a preferred subset.
4. The frozen two-arm HMM family and integer alias agree. The original source
   stays masked out; a derived view adds only the measured core. Other native
   path points are not promoted by this test.

The14-point core spans16.6547s, with minimum linear RMS319.22Hz and minimum
quadratic BIC gain18.83. It qualifies independently. A matched prediction-versus-
calibration test uses the **same14 IDs**,66525 hypothesis, alias, other priors
and cold5×48 fitting budget. The curved view inherits the source's original
noise power; no precision is tuned to obtain a gain.

|0215 same-core test|c=0 error km|Fitted-c error km|Associated points|
|---|---:|---:|---:|
|Graph parent, no core|2.822418|2.637363|1193|
|14-point core as predictive evidence|3.007001|2.777340|1207|
|Same14 points as curved calibration|2.894058|2.656649|1207|

Both derived trials pass paired gates and preserve all parent IDs. Calibration
is better than prediction for this core, but still slightly worse than the
graph parent. That distinction prevents an association repair from being
misreported as a localization repair. This is an inspected-case prototype,
not a generalization claim or a global endpoint-trimming policy.

### Higher coverage moves the estimate away from the better parent

Persistent temporal recovery adds76 predictive points in6 paths, raises
coverage to76.12%, and passes both arms. Nevertheless fitted-c error worsens
2.637→2.939km relative to its graph parent. The independent-state control adds74
points and reaches2.595km; it remains a named control, not a GPS-selected
replacement for the frozen persistent primary. This illustrates model-dependent
influence from additional individually plausible evidence. The present tests
do not identify a unique physical cause for the remaining position bias.

![0215 incumbent unused evidence](figures/DS23-0215_incumbent_unassociated_GLRT.png)
![0215 graph recovery associated](figures/DS23-0215_graph_recovery_associated_GLRT.png)
![0215 temporal unused evidence](figures/DS23-0215_persistent_temporal_unassociated_GLRT.png)
![0215 temporal path residuals](figures/DS23-0215_persistent5s_paths_1.png)
![0215 all retained track residual checks](figures/DS23-0215_track_residuals.png)

## 0281: long fitted degree is not active curvature; shorter sources can help

No wholly unused source meets the original actively-curved nomination rule.
The longest unused **RX2 CH2 T002** has29 points over35.800s and a stored
degree3 polynomial. Its distributed curvature check has minimum quadratic
BIC gain **−3.32**, so it should not calibrate offsets or drifts merely because
the graph selected a cubic. Its leading60316 causal phase-only diagnostic RMS
is106.53Hz; a following element gives107.93Hz. A good single-track profile
does not independently establish identity, and the original temporal search
is restricted to existing graph-parent families.

Two whole short sources pass the already implemented10s jackknife ablation:

|Source|Points / span|Causal nominee|Minimum linear RMS Hz|Minimum quadratic BIC gain|
|---|---|---:|---:|---:|
|RX1 CH3 T004|16 /18.216s|66260|363.23|15.19|
|RX1 CH1 T007|16 /14.348s|66133|360.18|33.23|

These are complete original sources; no endpoint is removed and no graph
polynomial is rewritten. Full-catalogue coarse nomination refines seven
candidates in both arms. Fixed-radio residual and alias checks precede the
regional fits. Both single-source trials and their32-point union pass final
gates. The predeclared maximum-added-points rule selects the union, giving
73.78% associated and2.813km fitted-c error, an improvement of218.91m. c=0
improves207.96m. The original20s classifier remains the published rule.

The same short-source rule already failed the iteration01020-scan mean-error
confirmation. These new local gains do not overturn that negative result;
there is no fresh full-DS23 rollout. In0215 its two16-point sources raise
association but worsen the already improved graph-parent position slightly.

Persistent prediction separately adds57 points in6 paths, reaches75.55%
association and2.966km fitted-c error. Its independent-state control adds56
points and gives2.967km. No supported endpoint core is offered for0281. The
short-source and temporal variants are kept separate.

### New-family search limit and a controlled singleton test

An explicit active-family audit confirms60316 is absent from the graph parent.
We also reuse the completed iteration007 full-population new-family experiment:
its grouped search considered two- and three-source groups, not singletons.
Three groups containing this29-point source all failed fixed-radio residual
checks and had negative gain against independent curves. They did not establish
that the source itself lacks a good satellite explanation. The old full result
returns the incumbent for0281; no previous grouped fit is repeated here.

The new bounded proposal permits **one longest wholly unused noncalibration
source≥20s and≥8 points per scan** to nominate a new family as predictive
evidence only. No such target exists in0215 after its graph recovery;0281's
29-point source is eligible. The entire causal catalogue is screened, seven
candidates are refined in both arms, and the same winner/alias is required.
The original fixed-radio residual checks, gap>2log100 to the next refined
candidate, and proper wrapped unresolved-polynomial comparison remain in force.
The multiplicity threshold is2log(targets×catalogue×27)=21.362. No radio
calibration coefficient is learned from the new source. Phase-only prediction
is the declared primary; three physical orbit modes are a named control.

60316 wins in both arms. Gains against the wrapped curve null are59.206/59.451,
and gaps to the next refined candidate1582.46/1570.57. Both exceed their fixed
thresholds. These scores are conditional nomination evidence, not calibrated
identity probabilities. All29 original points enter the subsequent cold fit.

|0281 predictive-family test|c=0 error km|Fitted-c error km|New points|
|---|---:|---:|---:|
|Incumbent|3.064638|3.032285|0|
|New60316, phase-only primary|3.168829|3.170596|29|
|New60316, physical-mode control|3.170797|3.172269|29|

Both trials pass final gates and phase convergence. The primary family phase
is0.829/0.836s, within the15s limit. Every original associated ID is preserved;
coverage becomes1044/1419=73.57294%, as recorded in the
[singleton table](tables/single_source_new_family.csv).
The receiver calibration coefficients are identical to the curved-only solution
at each fixed position. The optimum position can still move because the new
predictive factor contributes to the spatial likelihood. Here that movement
**worsens** fitted-c error by138.31m. This is a real association-search repair,
but it is not a localization improvement and is not promoted. It does not justify
deleting the source or selecting an identity using GPS either.

The old iteration007 grouped result on0215 is also reused for context:54 new
predictive points from66136/66140 reached2.775km fitted-c, worse than the present
graph recovery. Those old groups are separate from the new short/core policies.
See the [reused result receipts](evidence/reused007_new_family_results.json).

![Single-source60316 causal prediction and residuals](figures/DS23-0281_single_source_prediction.png)
![0281 singleton associated points](figures/DS23-0281_single_source_new_family_associated_GLRT.png)
![0281 singleton remaining unused points](figures/DS23-0281_single_source_new_family_unassociated_GLRT.png)

![0281 accepted short sources and residuals](figures/DS23-0281_short_curves.png)
![0281 incumbent unused evidence](figures/DS23-0281_incumbent_unassociated_GLRT.png)
![0281 short-policy associated](figures/DS23-0281_whole_short_curves_associated_GLRT.png)
![0281 short-policy unused evidence](figures/DS23-0281_whole_short_curves_unassociated_GLRT.png)
![0281 causal/following diagnostics](figures/DS23-0281_unused_track_TLE_diagnostics.png)
![0281 temporal paths](figures/DS23-0281_persistent5s_paths_1.png)
![0281 retained track residual checks](figures/DS23-0281_track_residuals.png)

## DBG01 loss, independent starts and family ablations

The loss figures evaluate a spatial grid with the **same incumbent observations**
at every pixel and refresh orbital phases. They do not rerun acquisition or the
full association pipeline per pixel. Arrows show local descent directions.
The81-start figures separately optimize each regional start through the bounded
association bank: curved labels/aliases can change under the existing c=0
step rule, fitted c follows its schedule, and predictive labels remain fixed.
Purple open diamonds are intermediate phase-round endpoints; final orange X
marks follow five rounds. GPS stars are evaluation only. These figures describe
the incumbent, not the short-source or new core policies.

Both scans have81/81 qualified restart outputs. The best score differences
from the incumbent are numerical-scale(~1e−8), so no restart is adopted. Under
this bounded bank, the error is not resolved by starting at a different place.

![0215 loss and gradient](figures/DS23-0215_loss_gradient_10km.png)
![0215 regional starts and final states](figures/DS23-0215_convergence_10km.png)
![0281 loss and gradient](figures/DS23-0281_loss_gradient_10km.png)
![0281 regional starts and final states](figures/DS23-0281_convergence_10km.png)

Family deletion diagnostics preserve the nuisance design and refit the other
evidence. The best paired-passing fitted-c deletion reaches2.672km in0215
(drop59495) and2.432km in0281(drop60918). Neither approaches0.5km; multiple
families influence the result. These are GPS-ranked explanations, not deletion
rules. Generic phase-prior controls are also retained, without selecting priors
from these scans' location errors.

![0215 family/source/prior influences](figures/DS23-0215_influence_and_controls.png)
![0215 loss decomposition](figures/DS23-0215_loss_decomposition.png)
![0281 family/source/prior influences](figures/DS23-0281_influence_and_controls.png)
![0281 loss decomposition](figures/DS23-0281_loss_decomposition.png)

The original graph covers1358/1667=81.46% of0215 and1123/1419=79.14% of0281.
Even perfect graph association needs at least143/155 additional outside-graph
observations respectively to reach90%. Native recovery uses existing measured
points outside that graph where supported; the remaining points are not forced
into families to meet a percentage target. Gray in GLRT panels means **all
original points**, red means unused, and colored lines are graph display
polynomials. Associated panels color by satellite hypothesis.

## Validation and evidence

All standard numerical stages are terminal and pass. The standard DBG01 audit
replays **534 scientific endpoint-arm checks**, covering restarts, family/source
ablations, priors and the reference diagnostics. **24 additional recovery arms**
are independently audited: eight temporal, twelve short-source, four source-core.
These recompute expected log density, coefficient equations, dense predictive
covariance, original curved/predictive gates and exact original-ID membership.
Maximum recovery audit differences are1.06e−7 in density,4.77e−8 in coefficient
equations, and1.68e−8 in predictive covariance evaluation. Four additional
singleton endpoint arms replay their saved objectives, curved densities, new
family gates and exact memberships; dense joint predictive-density discrepancies
are≤4.55e−13 and curved calibration coefficient differences exactly zero.
**19 component tests pass**. The iteration011 exact-native-timestamp repair remains in use; no
timestamp interpolation or radio-basis change is introduced.

The report includes **48 figures,12 CSV tables and five compressed evidence
partitions**. See [all figures](FIGURES.md),
[tables](tables/), [evaluation](evidence/evaluation.json),
[standard audit](evidence/independent_iteration_audit.json),
[recovery audit](evidence/recovery_endpoint_audit.json),
[singleton audit](evidence/single_source_audit.json),
[archive inventory and hashes](evidence/archive_manifest.json), and
[changed source/test snapshots](source/). Reused algorithms remain in prior
source freezes. These are research snapshots for the existing scientific
environment, not a standalone runtime package. No public contract, golden
fixture or production default changes.

To reproduce in a fresh output tree: bind a new root in the iteration012
runner, run its batch stages, then existing-recovery diagnostics/paths,
whole-short and source-core stages, recovery numerical audit, singleton
nomination/fits and report builder.
Their protocols fix candidate budgets, cold starts, both c arms and all reused
thresholds. Do not overwrite frozen experimental outputs. The only new core
eligibility operation is exact source-ID intersection of a previously screened
path; the prior endpoint and distributed-curvature guards remain mandatory.

The bounded case analysis is complete. These results support better diagnosis
and limited local recovery, while leaving a substantial systematic localization
bottleneck. Continue to0234/0064 and reserve new ALGO-series publication for a
credible matched full-DS23 improvement in position accuracy, not just coverage.
