# DS23 DBG01 iteration 010: short curved tracks, constrained recovery, and confirmation

This bounded investigation continues the **ALGO02/ALGO03** research engines
on **0080 and 0257**, followed by 20 other scans selected without their error
values. In0257, an existing short-duration curvature rule recovers31 original
observations and improves fitted-c error **3.180→2.748 km**. In0080,
gate-constrained temporal recovery reaches **80.83% GLRT association**, but
fitted-c error remains **3.291 km**, slightly worse than its3.236km incumbent.

The short-curve experiment recovers394 calibration observations on12 of20
confirmation scans and raises fitted-c association **69.89→71.08%**.
However, mean error worsens **1.548→1.555 km**, while median improves
**1.546→1.536 km**. The c=0 mean and median both worsen. **Do not adopt the
new rule or publish a new ALGO version.** This report records both the local
improvement and its unsuccessful transfer test; it does not cherry-pick the
better single-curve0257 result or the rejected near1.2km0080 endpoints.

The full-DS23 reference remains **410 available scans**, fitted-c mean
**1.469461 km**, median **1.178102 km**. No new full-DS23 run is justified by
this confirmation result. The **mean and median ≤0.5km goal remains unmet**.
Close these bounded tests and move to **0163 and0209**.0209 was also in this
confirmation cohort: reuse its short-curve evidence rather than repeat that
prototype without a new hypothesis.

![Controlled outcomes](figures/iteration_summary.png)

## Scientific controls

All inference uses causal Space-Track elements whose epoch and collection
precede the scan cutoff, the original **25×25km box centered37.906,-122.545**,
and cold position starts at **east/north [0,0]**. The constrained refinement
explicitly starts from its prior cold-fit RF endpoint. Evaluation GPS
**37.849061591561885,-122.48574968092912** supplies debug priority and scores
sealed results only. No satellite, alias, mask, prior or optimizer start is
chosen using that coordinate. Following elements are isolated diagnostics.
The available catalogue is Starlink-only, not every possible orbital emitter.

Every comparison retains matched **c=0/fitted-c** observations, candidates,
aliases, other priors and budgets. Original receiver/band offsets, linear
drifts, smooth receiver bases, Student/Gamma and physical orbit priors remain.
The ordinary cold fits use five phase-refresh rounds of48 descent steps.
The additional constrained fit uses five rounds of40 steps in both c arms,
with the existing0.01 normalized interior margin and unchanged gate limits.
There is no RF collection, IQ reprocessing, trajectory prototype or stationary
history position pooling.

Counts are unique original winning GLRT IDs. Persisted graph polynomials,
native CFO values and the denominator remain unchanged. New short sources
are promoted only after independent RF curvature evidence. Linear sources
never calibrate receiver parameters. Temporal paths remain predictive-only;
their likelihood retains shared calibration covariance. At fixed position,
predictive data do not update the curved-calibration coefficients. All parent
likelihood and accepted association IDs must survive these new policies.

## Results and graph-coverage limits

| Scan / separate policy | Associated | % GLRT | Fragments | Points/fragment | Curved position points | Predictive position points | c=0 error km | Fitted-c error km |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
|0080 incumbent|2,533|77.46|74|34.23|2,127|406|2.539|3.236|
|0080 graph recovery|2,565|78.44|76|33.75|2,148|406|2.595|3.291|
|0080 constrained temporal|2,643|80.83|81|32.63|2,148|484|2.590|3.291|
|0080 short-curve policy: fallback to graph|2,565|78.44|76|33.75|2,148|406|2.595|3.291|
|0257 incumbent / graph fallback|679|60.57|24|28.29|655|24|3.195|3.180|
|0257 persistent temporal|745|66.46|30|24.83|655|90|3.489|3.388|
|0257 short whole curves|710|63.34|26|27.31|686|24|2.814|2.748|

These are **separate experiments**, not an untested sum of recovered points.
The0257 short policy does not include its66 temporal points. In0080,21 new
curved observations yield32 net associations because11 additional original
points become compatible after refitting. The constrained temporal policy
then adds78 predictive points. It changes no curved membership. Higher
coverage does not guarantee better location: both0080 recovered policies
are slightly worse than the incumbent in fitted-c accuracy.

| Scan | All GLRT | Unused inside original graph | Outside graph | Graph-only ceiling | Outside-graph points required for90%, even with perfect graph recovery |
| --- | ---: | ---: | ---: | ---: | ---: |
|0080|3,270|414|323|90.12%|0|
|0257|1,121|110|332|70.38%|220|

The ceiling does not assert that all those observations are signal.0257
cannot reach90% by relabeling its existing graph alone. Frequency RMS is
reported separately in[the policy table](tables/position_and_association.csv).
For example,0257 short recovery lowers curved RMS172.44→171.51Hz locally,
but confirmation RMS stays near113.96Hz while mean location error worsens.

##0080: a protected family creates the active constraint

The longest wholly unused curved offers are RX1 CH1 T002,18 points over
219.97–246.22s; RX1 CH7 T004,21 points over10.91–36.82s; and RX1 CH4 T004,
21 points over235.71–260.19s. Causal uncertainty-aware nomination favors
**66384,66381,66384**, respectively. Only the66381 single passes the default
paired fit. Original single controls and all offered unions are retained;
the support control does not provide a better qualifying growth proposal.

The existing graph-seeded temporal algorithm tests independent identities
and a5s persistence model with19 time-permutation controls, fixed path gates,
the exact native receiver basis and joint predictive covariance. Its two
cold fits reach fitted-c errors **1.239 and1.209km**, but **both reject**.

The failing source is **RX1 CH5 T004**,26 points over50.91–76.11s, assigned
to **67014**. For the persistent proposal its conditional RMS is only
163.15Hz, but residual slope is **3.3458σ**, exceeding the unchanged3σ gate.
Step is3.9868 against4, and quadratic BIC gain7.09 against10. The other
67014 owner, RX1 CH4 T008,13 points over23.91–51.93s, has acceptable residual
statistics but then fails the family-support cascade when its partner fails.
The source family therefore cannot be counted as retained. These failed
endpoints and their lower errors remain diagnostics, not algorithm results.

The normalized worst slacks are−0.09646 in c=0 and−0.11526 in fitted-c,
inside the existing−0.25 near-feasibility trigger. The unchanged constrained
solver finds a paired passing solution for all78 frozen new predictive
points. Minimum slacks are about+0.010001 in both arms and phase refresh
converges. Its fitted-c endpoint returns to **3.291221km**. Making the
original constraints pass does not preserve the apparent1.2km gain.

![0080 original associated GLRT](figures/DS23-0080_incumbent_associated_GLRT.png)
![0080 original unused GLRT](figures/DS23-0080_incumbent_unassociated_GLRT.png)
![0080 graph associated](figures/DS23-0080_graph_recovery_associated_GLRT.png)
![0080 graph unused](figures/DS23-0080_graph_recovery_unassociated_GLRT.png)
![0080 constrained temporal associated](figures/DS23-0080_temporal_policy_associated_GLRT.png)
![0080 constrained temporal unused](figures/DS23-0080_temporal_policy_unassociated_GLRT.png)
![0080 independent paths: rejected final trial](figures/DS23-0080_independent_paths_1.png)
![0080 persistent paths: rejected unconstrained trial](figures/DS23-0080_persistent5s_paths_1.png)

Gray is **all original GLRT**, not unused GLRT. Red identifies unused points
in the unused views. Polynomial samples are display only. Path figures
label the original unconstrained trials; their local path gates can pass
while the parent67014 source fails. The constrained policy plots above use
the later qualified endpoint and membership.

### Ablation and an RF-only test of the tempting merge

Deleting67014 is the **only paired-passing single-family deletion** in0080.
It removes39 calibration observations and gives c=0/fitted-c errors
**0.615/0.737km**, with2,494 associated points,76.27%. Some other deletions
have still lower GPS errors but fail paired gates, so they cannot be called
valid remedies. This is evidence that the67014 family and its model are an
important source of tension, not proof that deleting that identity is a
general algorithm. No GPS-selected deletion is adopted.

One tempting explanation is that the nearby recovered66381 curve should
be merged with67014. The existing same-RX RF-normalized curvature comparison
tests that without TLEs or position. Separate affine terms remove aliases,
band constants and linear drift; shared versus independent nonlinear
polynomials are compared on the same active observations, through degree4.
For the closest67014 CH4 source, **BIC(shared)−BIC(independent)=+4.44**:
independent curves are favored. The independent curvature gain is185.65BIC,
so these are measurably curved signals. Other adjacent-family comparisons
favor independent curves even more. **Do not force the proposed merge.**
The test uses whole active masks with at least6s actual overlap and8 points
per curve; it is a diagnostic model comparison, not an identity probability.
All compared native IDs and fit arrays are in the raw evidence archives.

![0080 loss and gradient](figures/DS23-0080_loss_gradient_10km.png)
![0080 multistart convergence](figures/DS23-0080_convergence_10km.png)
![0080 family and track influence](figures/DS23-0080_influence_and_controls.png)
![0080 loss decomposition](figures/DS23-0080_loss_decomposition.png)
![0080 residual distributions](figures/DS23-0080_track_residuals.png)

None of0080's81 unconstrained regional restarts passes the paired gates.
They converge to the same problematic family fit: phase refresh and the15s
phase limit pass, but the67014 source fails slope and sometimes step. More
starts alone do not resolve this model/gate conflict. The RF restart selector
therefore has no eligible replacement. Surface arrows describe descent of
the sampled conditional objective, not feasibility or a calibrated geographic
probability. Intermediate purple phase-round states are distinguished from
the final orange endpoints.

##0257: short sources really have active curvature

0257 has no wholly unused component meeting the existing20s curved-track
rule. That does not mean its unused data are linear. The existing
[iteration008 rule](../2026_10_22_ds23_dbg01_iteration_008/README.md) permits
10s only when at least12 points have **≥250Hz linear-fit RMS** and **>10
quadratic BIC gain under every single-point deletion**. Here it is applied
to whole original sources, rather than an endpoint-trimmed core.

| Source | Points | Span s | Minimum linear RMS across deletions Hz | Minimum quadratic BIC gain | Causal hypothesis |
| --- | ---: | ---: | ---: | ---: | ---: |
|RX2 CH1 T003|17|12.892|315.78|82.34|64143|
|RX1 CH3 T004|14|18.285|782.22|36.89|58077|

Both are strong enough to qualify independently of TLEs and GPS. Each new
source is absent from receiver calibration during causal catalogue nomination.
The best7 coarse nominees are refined in both c arms, using a shared c=0
candidate/alias pool and fixed-radio residual checks. Their leading score
gaps exceed122 and276 respectively within that shortlist. This is not a
calibrated global identity probability.

The research view appends the existing source to curved calibration without
changing its IDs, values, polynomials or native basis. It preserves old powers
and supported modes; new one-owner families use the existing0.2 power and
retain phase while avoiding unsupported shape coordinates. An exact
parent-objective null precedes fitting. At most two targets are ranked by
point count, span and key; all three nonempty subsets are fitted. Parent IDs
and all original gates must survive.

|0257 short experiment|c=0 error km|Fitted-c error km|Decision|
| --- | ---: | ---: | --- |
|17-point64143 only|3.538|3.482|Passes RF gates|
|14-point58077 only|2.329|2.308|Passes RF gates|
|Both,31 points: declared maximum-point policy|2.814|2.748|Passes RF gates|

The better2.308km single is **not** selected using GPS. The maximum-point
policy takes the31-point union. This is an explicit example of why a passing
additional family can worsen location relative to another valid point set.
The independent temporal control adds52 points and gives3.368km; persistent
temporal adds66 and gives3.388km. Their association improvements do not
solve localization, and are separate from the short-curve calibration test.

![0257 short sources and expected curves](figures/DS23-0257_short_curves.png)
![0257 original associated](figures/DS23-0257_incumbent_associated_GLRT.png)
![0257 original unused](figures/DS23-0257_incumbent_unassociated_GLRT.png)
![0257 graph fallback associated](figures/DS23-0257_graph_recovery_associated_GLRT.png)
![0257 graph fallback unused](figures/DS23-0257_graph_recovery_unassociated_GLRT.png)
![0257 short policy associated](figures/DS23-0257_short-curve_policy_associated_GLRT.png)
![0257 short policy unused](figures/DS23-0257_short-curve_policy_unassociated_GLRT.png)
![0257 persistent temporal associated](figures/DS23-0257_temporal_policy_associated_GLRT.png)
![0257 persistent temporal unused](figures/DS23-0257_temporal_policy_unassociated_GLRT.png)
![0257 independent paths](figures/DS23-0257_independent_paths_1.png)
![0257 persistent paths](figures/DS23-0257_persistent5s_paths_1.png)

The corresponding0080 short test has three RF-eligible sources, of which the
fixed two-target budget considers20 and19 points. The20-point source's best
causal nomination,69375, fails fixed-radio checks at about778Hz. The19-point
source nominates59189 and passes nomination, but its full fit rejects. No
short-curve gain is adopted for0080.

![0080 short-source checks](figures/DS23-0080_short_curves.png)
![0257 loss and gradient](figures/DS23-0257_loss_gradient_10km.png)
![0257 multistart convergence](figures/DS23-0257_convergence_10km.png)
![0257 family and track influence](figures/DS23-0257_influence_and_controls.png)
![0257 loss decomposition](figures/DS23-0257_loss_decomposition.png)
![0257 residual distributions](figures/DS23-0257_track_residuals.png)

All81 regional restarts pass on0257 and return the incumbent RF solution;
the best corrected gain is numerical noise. Deleting65641 is its GPS-best
paired-passing family ablation, but still leaves **2.266km** while removing80
curved points and lowering association to53.43%. No single-family deletion
solves this case. Complete ablations and prior sensitivities are in the tables.

##20-scan confirmation: association transfers, accuracy does not consistently

The frozen cohort uses seed2026102210 and six bounded workers. Selection
uses only available scan IDs, excludes all closed debug cases and0080/0257,
and is invariant to the benchmark's error values. These are scan-disjoint
cases at the **same previously studied site**, not an untouched dataset or
new-location test. The experiment uses each incumbent directly; it adds no
long-track graph recovery or temporal paths, isolating the short whole-curve
rule. All20 scans, including eight exact fallbacks, remain in evaluation.

| Arm / policy | Mean error km | Median km | P90 km | Associated / all GLRT | % | New curved likelihood points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
|c=0 incumbent|1.518863|1.563262|2.534693|34,807 /49,803|69.8894|0|
|c=0 short policy|1.531112|1.616507|2.556299|35,421 /49,803|71.1222|394|
|Fitted-c incumbent|1.548263|1.546016|2.501017|34,807 /49,803|69.8894|0|
|Fitted-c short policy|1.555295|1.535684|2.530513|35,401 /49,803|71.0821|394|

Twelve scans accept recovery. Both arms have two regressions exceeding100m
and none exceeding500m. Net associations rise by614/594, more than the394
new calibration points, because previously post-fit-only memberships change
at the new positions. No old accepted ID is lost. Mean curved RMS changes
only114.054→114.054Hz in c=0 and113.961→113.964Hz in fitted-c. These RF fit
statistics are separate from accuracy and do not validate the new policy.

Every selected endpoint's normalized objective, original gates and unique
membership are replayed before geographic scoring. Original calibration
powers and every parent accepted ID remain. Missing legacy phase-refresh
metadata are reconstructed from the saved endpoint and actual phase
linearization reference, without refitting or assuming convergence.

![All20 results and association versus error changes](figures/confirmation20_positions_and_coverage.png)

The result fails the intended simultaneous mean/median improvement. Retain
the incumbent. The full410-scan benchmark is not replaced by this20-case
summary, and a new ALGO number is not justified.

## Causal and following-element diagnostics

For each scan the three longest wholly unused original tracks, including
linear tracks, receive a full available causal-catalogue coarse search and
top7 refinement. The top3 hypotheses then receive matched phase-only causal
versus real earliest following-element profiles, using the same c=0 RF
endpoint and causal receiver posterior. Following element epoch and
collection must both be after the scan and within48h. None is used for
inference, identity selection or point admission.

The [profile table](tables/following_TLE_profiles.csv) and figures preserve
all tested alternatives. In0257 the18.3s58077 hypothesis changes only about
206.74→205.29Hz between causal and following phase-only profiles. This does
not explain a categorical20s classifier exclusion. A low RMS on a single
linear piece is not identity evidence strong enough to calibrate offsets.
The physical-mode nomination and restricted phase-only profile are different
models; their RMS values must not be compared as a TLE-only ablation.

![0080 whole unused-track diagnostic](figures/DS23-0080_unused_track_TLE_diagnostics.png)
![0257 whole unused-track diagnostic](figures/DS23-0257_unused_track_TLE_diagnostics.png)

## How DBG01 surfaces and starts were computed

At each sampled regional1km grid point and local0.25km grid point, the
surface keeps the current labels, aliases and observations fixed, profiles
nuisance parameters, and refreshes absolute phase five times. It does not
rerun acquisition/GLRT/graph construction at every pixel. Arrows show the
negative finite-difference gradient direction of that conditional loss.

The separate81-start experiment permits curved labels/aliases to switch at
accepted c=0 descent steps among at most four complete-observation assignment
hypotheses. Fitted c follows that branch schedule; predictive labels stay
fixed. The bank combines the current assignment, available original archived
choices and13 actual cold same-scan discoveries, discards their fitted radio
states, preserves predictive families, deduplicates, and ranks the cap only
by corrected RF objective at the regional center. The pool is not exhaustive
catalogue reassociation. Purple diamonds denote intermediate phase-round
endpoints; orange X markers are final after all five rounds. All coordinates
are available in[the per-round table](tables/restart_phase_rounds.csv).

## Execution fixes, tests and source evidence

The initial010 process**27353** terminated at bank construction: rescued
scan0080 lacks its original `fit_radio_noise.json` choice archive. The
scientific-receipt guard stopped dependent work. The repair uses the current
complete assignment plus13 real completed cold discoveries and explicitly
records the missing archive. It fabricates no historical choices. Other
scans with that archive retain the original path. The original failed
execution is preserved; resumed process**23573** completed all stages.
Independent DBG01 checks pass for **548 endpoint arms and21 nominee densities**.

In confirmation,0290 and0331 have no old predictive factors. The reused path
refitter's post-fit audit incorrectly assumed `curved_calculate` existed,
although its calibration-only fit itself was defined. V2 implements the
same five-by48 support-model fit for that empty-prediction case, records
that no predictive density exists to audit, and reruns only those two failed
cases. Eighteen successful cases are reused byte-for-byte. All20 qualify as
complete computations; ordinary scientific rejections remain exact fallbacks.
No case is dropped or resampled.

Two report-only repairs are also retained: missing legacy refresh metadata
are measured at frozen endpoints, and incumbent rows report zero newly added
points rather than copying the candidate policy's selection annotation.
Before-correction source/results remain archived. Neither correction changes
an inferred position, candidate choice or accepted mask. **18 component-owned
tests pass**, including native-RF derivative scaling, no duplicate IDs or
linear calibration, frozen powers, missing-prediction handling, error-blind
cohort selection, scientific receipts and all-case summary accounting.

The report contains **34 scientific figures and11 CSV tables**. Complete
JSON/CSV/Python evidence is partitioned by main scan, restart and confirmation
scan under[evidence](evidence), keeping individual archives below45MiB.
It includes failures, repairs, every fit, raw masks and IDs, all DBG01
grids/restarts/ablations, causal/following profiles, RF curvature comparisons,
confirmation protocols, reused-file digests and objective/gate replays.
Scientific inputs remain in the existing corpus outside Git.

Reproduction uses the existing research environment, not a standalone
deployment bundle. Source snapshots and hashes are in[source/tools](source/tools),
[source/tests](source/tests) and[the source manifest](evidence/source_hashes.json).
To regenerate figures/tables after the frozen scientific stages:

```bash
env PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/algo03-feasible-deps:src:tools \
 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
 .venv/bin/python -B tools/report_ds23_dbg01_iteration_010.py
```

Machine-readable results:

- [Position and unique-GLRT accounting](tables/position_and_association.csv)
- [All prototype endpoints, including rejected fits](tables/prototype_trials.csv)
- [Family ablations and qualification](tables/family_ablations.csv)
- [Every family/track/prior intervention](tables/all_interventions.csv)
- [Retained residual distributions](tables/residual_diagnostics.csv)
- [Whole temporal path checks](tables/temporal_paths.csv)
- [Independent short-curve evidence](tables/short_curvature.csv)
- [All20 confirmation positions](tables/confirmation20_positions.csv)
- [Both-arm confirmation summaries](tables/confirmation20_summary.csv)

The next useful question is whether RF-only family adequacy can distinguish
0080's conflicting67014 model from an unknown curve, before selecting any
deletion. That requires a comparable full-observation density and a physical
or broad-curve alternative, not GPS-ranked ablation or additional unconstrained
freedom. Inspect prior adequacy/outlier work before implementing it. Continue
DBG01 on0163/0209 and revisit a closed scan only for a transferable hypothesis.
