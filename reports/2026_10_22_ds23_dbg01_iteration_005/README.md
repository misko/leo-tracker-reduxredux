# DS23 DBG01 iteration 005: graph reentry and temporal predictive recovery

The next two worst unclosed scans are **0272 and 0068**. Building on the
existing ALGO02/ALGO03 research implementation recovers useful curved evidence
in 0272: its fitted-c error falls **3.783→1.220 km**, and original GLRT
association rises **67.90→73.34%**. A separate temporal predictive prototype
recovers 83 points but barely changes position.0068 remains unresolved.

**No new ALGO version is promoted.** These are conditional development results,
not a matched full-DS23 improvement. The archived 410-scan reference remains
mean 1.469461 km, median 1.178102 km; the mean-and-median 0.5 km objective is unmet.
The iteration also exposes a qualification inconsistency:0068's archived
baseline itself exceeds the later strict 15 s phase gate. Its fallback below
means the archived output, not a newly qualified solution.

![Association, position accuracy and graph ceilings](figures/iteration_summary.png)

## Population, controls and accounting

The queue uses the published full-population fitted-c error, excluding only
cases already closed in this debug pass.0405 remains in the evaluation and is
skipped only in the queue. The next batch is **0069 and0291**. No cases are
removed from the published benchmark to improve its statistics.

Inference retains the original **25×25 km box centered at37.906,-122.545**.
New position trials start at regional[0,0], with five phase-refresh rounds and
48 position iterations per round. Causal element epochs **and collection
times** are checked against the scan cutoff. Evaluation GPS
37.849061591561885,-122.48574968092912 ranks debug priorities and evaluates
sealed results; it does not supply inference, selection or a position prior.
No RF collection, IQ reread, receiver-stationarity assumption or RF history
position pooling is added.

Every proposal uses matched c=0/fitted-c observations, candidate assignments,
aliases, other priors, residual gates and search budgets. Original accepted
measurement IDs are retained by the accepted prototypes. Counts use unique
original winning GLRT IDs, never interpolated polynomial samples or additional
synthetic measurements. The c arms are controlled ablations, not two datasets.

| Scan | Original GLRT | Associated | Unused inside graph | Outside every graph | Graph-only ceiling | Outside-graph points needed even with perfect graph coverage to reach90% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
|0272|2,723|1,849|472|402|85.24%|130|
|0068|3,173|1,656|1,196|321|89.88%|4|

0068 is primarily a **satellite-association/model-compatibility** problem:
most unused points already lie in graph tracks.0272 also needs substantial
outside-graph evidence to approach 90%. Neither ceiling is a promise that all
of those points are physical satellite signals.

## Controlled end-to-end results

The graph repair and predictive methods are **separate experiments from the
same incumbent**. Their counts and benefits cannot be added together. We have
not selected the lowest GPS error among them as a deployable policy.

| Scan and method | Original GLRT associated | % | Associated fragments | Points/fragment | Points used for position | c=0 error km | Fitted-c error km | Fitted-c curved RMS Hz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
|0272 archived incumbent|1,849|67.90|55|33.6|1,849|3.808|3.783|153.00|
|0272 RF-qualified graph reentry|1,997|73.34|58|34.4|1,955|1.380|1.220|161.68|
|0272 screened independent predictive|1,927|70.77|61|31.6|1,927|3.944|3.931|153.00|
|0272 screened temporal predictive|1,932|70.95|61|31.7|1,932|3.761|3.746|153.00|
|0068 archived incumbent / all rejected-prototype fallbacks|1,656|52.19|49|33.8|1,656|3.557|3.707|95.54|

The graph repair uses 106 new curved points in 0272. A further 42 points pass
the post-fit graph-extension gates but do **not** enter its position
likelihood; hence 148 additional associations and 106 additional position
observations. The improved position accompanies a higher curved RMS on the
larger observation set. It is not an in-sample frequency-fit improvement.

The temporal method adds 83 predictive points in six complete fragments.
The independent control adds 78. Both preserve the curved calibration
membership and coefficients at a fixed position. They can still change the
position objective through prediction. The independent control's geographic
regression demonstrates why additional compatible points alone are insufficient
for an ALGO release.

The complete matched-arm table includes the exact fallback outputs and phase
qualification flags: [position and association](tables/position_and_association.csv).

## 0272: two missing curved tracks matter

The unchanged bounded full-causal-catalogue screen examines the three longest
wholly unused curved graph tracks with at least 12 points, across the incumbent
and nine regional seeds, then refines nominations and fits combinations. It
does not hard-code identities. Two single-track reentries pass both arms and
their 106-point union passes:

| Track | Points | Span s | Inferred hypothesis | Result |
| --- | ---: | ---: | ---: | --- |
|RX1 CH4 T002|57|81.27|69170|Retained in union|
|RX1 CH4 T001|49|62.11|68557|Retained in union|
|RX1 CH5 T002|32|42.23|63037|Rejected: structured, large residual|

All original accepted IDs survive. The 32-point candidate's fitted-c
single-track trial has conditional RMS 722 Hz, slope z 3.91, quadratic BIC
gain 38.68 and maximum step z 4.60. Its rejection is substantive, not a rounding
issue at one threshold. The accepted union is chosen by the existing RF/gate
rule and added-point count, before geographic evaluation.

![0272 original unused evidence](figures/DS23-0272_published_unassociated_GLRT.png)
![0272 accepted hypotheses after graph reentry](figures/DS23-0272_graph_policy_associated_GLRT.png)
![0272 remaining unused evidence](figures/DS23-0272_graph_policy_unassociated_GLRT.png)
![0272 recovered curves with expected orbit and residual](figures/DS23-0272_recovered_curves.png)
![0272 long-curve diagnostics](figures/DS23-0272_long_curve_residuals.png)

This repair recovers missed evidence under the existing model; it does not
validate unrestricted growth across DS23. Iteration 003 already demonstrated
that broader growth can worsen cohort accuracy. We retain that evidence and
do not promote this favorable individual scan as a general algorithm gain.

## 0068: smooth polynomials fail shared orbital compatibility

The three longest tested unused curves each have **one persisted polynomial
piece**, with graph RMS around71–77 Hz. The joint satellite trials instead
leave large systematic residuals. There is no visible join boundary in these
three targets requiring a split repair; smooth graph residuals also do not
prove that a proposed satellite identity is correct.

| Target | Points | Graph RMS Hz | First regional joint trial hypothesis | Fitted-c conditional RMS Hz | Slope z | Quadratic BIC gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
|RX1 CH4 T000|34|74.9|64739|1,711.8|5.36|141.1|
|RX1 CH2 T000|81|70.8|48455|3,441.8|8.81|557.0|
|RX1 CH3 T001|61|76.7|53750|3,667.5|7.70|364.1|

These are hypotheses from the regional search, not verified identities.
Alternative original-family and multi-track controls also fail. The
support-aware bookkeeping control does not recover a passing addition. The
failure cannot be repaired merely by counting more points on the polynomial
or lowering its order.

![0068 original unused GLRT and graph polynomials](figures/DS23-0068_published_unassociated_GLRT.png)
![0068 polynomial versus joint satellite residuals](figures/DS23-0068_long_curve_residuals.png)
![0068 retained-track gate distributions](figures/DS23-0068_track_residuals.png)

### An inherited phase-qualification inconsistency

Satellite 58133's archived baseline phase is 15.1648 s in c=0 and 15.1218 s in
fitted-c. Phase-reference clipping to±15 s does not constrain the posterior
phase itself. The subsequently applied strict gate checks the latter. Thus
all 81 restarted 0068 endpoints fail qualification; that does not imply the
archived baseline satisfies the same gate.

After whole-path screening, both predictive trials pass all curved and
predictive residual checks and preserve all original accepted IDs. They still
fail this phase gate: the temporal trial reaches 15.1613/15.1217 s. It is
rejected. No phase bound, prior or acceptance tolerance is changed here.
The fallback table preserves the archived 3.707 km result for comparability,
with an explicit phase-failure flag. It is not a qualified fresh solution.
The full-population reference is an archived metric, not a new 410-scan
certification under this stricter gate. A separate qualification audit is
needed before making that claim.

## Temporal predictive recovery: hypothesis, algorithm and negative controls

Hypothesis: unused winning GLRT points may trace a satellite curve even when
the original graph did not retain the complete evidence. Temporal identity
continuity could help recover them without letting uncertain or linear
fragments calibrate offsets, drift or orbit corrections.

1. Exclude the union of incumbent accepted IDs and retained calibration
   observations. Include all remaining original winning points, both unused
   graph points and points outside every graph.
2. Partition by physical receiver, channel and actual RF, ordered by time.
   Candidate families are **all incumbent active curved families** inferred
   in the scan. This prototype cannot discover a family absent from that set.
3. Compute causal orbit plus curved-posterior predictions and marginal
   uncertainty. Use a normalized wrapped Gaussian CFO density, including a
   Fourier representation when uncertainty approaches the alias period.
   An explicit uniform-clutter state has density 1/alias-period.
4. Compare independent labels,τ=0, against temporal persistence,τ=5 s.
   A state persists with probability exp(-Δt/τ); gaps above 10 s reset it,
   and below-horizon families cannot retain state. The proposal signal
   fraction is fixed at 1/2. Forward/backward inference and Viterbi decoding
   nominate complete paths with at least 8 points spanning at least 6 s.
5. Require each lane's native likelihood ratio to exceed the largest of 19
   time/CFO permutation controls plus 2 log 20. Heteroscedastic noise follows
   its permuted measurement. This is a coherence diagnostic, **not a
   validated exchangeability-based p-value**.
6. Check every proposed path against every visible active family and
   uniform clutter using the **full correlated curved-calibration covariance**
   and one integrated 300 Hz constant per path. Both c arms must prefer
   the same family, with nominal class probability≥0.99, a gain exceeding
   2 log(2×number-of-lanes×number-of-families), and marginal uncertainty below
   one twentieth of the alias period. Alias lifts must agree between arms.
   These probabilities are post-selection compatibility scores, not
   calibrated probabilities of a true satellite identity.
7. Freeze at most 24 paths per method, ranked by c=0 correlated RF gain.
   Append them as **predictive evidence only**: no new curved members,
   calibration normal-equation updates or invented polynomial samples.
   Old and new predictive evidence enter **one joint covariance block**.
8. Cold-refit both c arms. Require the existing residual/alias/visibility,
   phase, regional-bound and original-ID-retention checks. Otherwise retain
   the archived baseline and record its own qualification status.

The HMM uses marginal emissions only for discovery. Its posterior is not
substituted for the correlated path check or the joint final position
likelihood. Selection reuses scan data; no claim of independent identity
validation is made.

### Why a second whole-path screen was tried

Initial 11-path proposals in 0272 offer 267/279 points for independent/temporal
models;0068 offers 166/165 points. All four unscreened unions fail final checks.
Several paths with high Gaussian compatibility retain systematic residuals.
The bounded refinement therefore applies the **unchanged existing residual
checks at both incumbent endpoints before fitting**, rejecting entire paths,
then freezes the remainder for one cold fit. There is no iterative trimming,
no removal of individual bad residuals, and no GPS-based path selection.

| Scan | Method | Initially offered points | Points after whole-path screen | Final decision |
| --- | --- | ---: | ---: | --- |
|0272|Independent|267|78|Passes; error worsens to3.931 km|
|0272|Temporal5 s|279|83|Passes; error3.746 km|
|0068|Independent|166|37|Residual checks pass; strict phase gate fails|
|0068|Temporal5 s|165|19|Residual checks pass; strict phase gate fails|

![0272 temporal coherence control](figures/DS23-0272_temporal_coherence.png)
![0068 temporal coherence control](figures/DS23-0068_temporal_coherence.png)
![0272 screened temporal associations](figures/DS23-0272_screened_persistent5s_associated_GLRT.png)
![0272 screened temporal unused evidence](figures/DS23-0272_screened_persistent5s_unassociated_GLRT.png)
![0272 screened independent associations](figures/DS23-0272_screened_independent_associated_GLRT.png)
![0272 screened independent unused evidence](figures/DS23-0272_screened_independent_unassociated_GLRT.png)

All original offered paths, including rejected ones, are visualized with the
native GLRT, expected orbit plus curved receiver calibration and a descriptive
path mean, and the mean-centered prediction residual. Lines break across
aliases/time gaps. The descriptive mean in these figures does not replace
the integrated 300 Hz prior or final residual gates:

![0272 independent paths page1](figures/DS23-0272_independent_predictive_paths_1.png)
![0272 independent paths page2](figures/DS23-0272_independent_predictive_paths_2.png)
![0272 temporal paths page1](figures/DS23-0272_persistent5s_predictive_paths_1.png)
![0272 temporal paths page2](figures/DS23-0272_persistent5s_predictive_paths_2.png)
![0068 independent paths page1](figures/DS23-0068_independent_predictive_paths_1.png)
![0068 independent paths page2](figures/DS23-0068_independent_predictive_paths_2.png)
![0068 temporal paths](figures/DS23-0068_persistent5s_predictive_paths_1.png)

## DBG01 surfaces, restarts and ablations

Both scans have the standard fixed-assignment 10 km loss/gradient map and
81-start convergence experiment. The grid recomputes the continuous nuisance
model at each sampled position; it does **not** rerun acquisition, GLRT,
graph construction and the full catalogue search at every pixel. Restarts
can choose among an RF-discovered finite assignment bank while descending
and refreshing phase.0272 has two bank branches;0068 has four. This is not an
unlimited fresh catalogue search at every descent step. All input masks,
original measurements and bank identities remain recorded.

0272's 81 restarts qualify but produce only 4.7 e-8 c=0 RF gain versus a
1.386 penalty; none is adopted.0068 has zero qualified endpoints. A separate
true-site-initialized diagnostic returns to the same 3.783/3.707 km errors.
That GPS-initialized diagnostic is clearly excluded from inference. Nonzero
gradients at the evaluation site and near-zero gradients at the archived
endpoints show that local optimization accuracy alone is not the bottleneck
under these fixed models.

![0272 local loss and gradient](figures/DS23-0272_loss_gradient_10km.png)
![0272 multi-start convergence](figures/DS23-0272_convergence_10km.png)
![0068 local loss and gradient](figures/DS23-0068_loss_gradient_10km.png)
![0068 multi-start convergence](figures/DS23-0068_convergence_10km.png)

All 15/18 active families and 38/36 retained curved tracks are ablated,
alongside the two standard phase-prior controls. Removing 68556 improves 0272
to 2.264 km, still well above 0.5 km. Removing 64738 in 0068 gives 0.858 km but
**fails paired gates**. The best passing family deletion there remains
3.427 km. No satellite is deleted because its GPS error looks favorable.
The zero-mean and wider-phase-prior controls do not solve either scan.

![0272 family, track and prior influence](figures/DS23-0272_influence_and_controls.png)
![0272 objective decomposition](figures/DS23-0272_loss_decomposition.png)
![0068 family, track and prior influence](figures/DS23-0068_influence_and_controls.png)
![0068 objective decomposition](figures/DS23-0068_loss_decomposition.png)
![0272 residual gate distributions](figures/DS23-0272_track_residuals.png)

The archived ablation flag `paired_gates_valid` denotes that ablation
implementation's residual checks. It must not be read as a fresh strict 15 s
phase certification;0068's inherited inconsistency is reported separately.

## Following TLEs: diagnostic only

For each frozen causal nomination, read the earliest locally archived element
by epoch then collection with **both after scan end and within48 h**. All
9/7 requested candidate identities have real following elements. No missing
element is silently replaced by a causal one. The digest-verifying archive
port is read-only. The diagnostic fixes the causal RF endpoint and receiver
posterior, profiles phase over±15 s with a quarter-second grid and local
refinement, and includes no phase prior or orbital-shape mode in either TLE
version. Full correlated radio/fragment uncertainty remains matched.

| Scan/curve | Frozen causal nomination | Graph RMS Hz | Causal / following conditional profile RMS Hz |
| --- | ---: | ---: | ---: |
|0272 CH4 T002|69170|189.4|299.1 /296.0|
|0272 CH4 T001|68557|106.0|166.5 /234.6|
|0272 CH5 T002|63037|222.6|540.5 /536.6|
|0068 CH4 T000|64739|74.9|699.2 /700.9|
|0068 CH2 T000|47778|70.8|5,931.6 /5,911.1|
|0068 CH3 T001|58133|76.7|422.5 /388.9|

These are conditional profile comparisons, not the regional joint-trial RMS
table above; their nominated identities and conditioning differ. Following
elements modestly help 58133, worsen some other profiles and do not explain
away the large 0068 discrepancies. They neither establish the true identity
of each rejected curve nor authorize use of future information in inference.

![0272 following-element profiles](figures/DS23-0272_following_TLE_profiles.png)
![0068 following-element profiles](figures/DS23-0068_following_TLE_profiles.png)

## Decision and next iteration

Keep ALGO02/ALGO03 as the development base. Retain 0272's graph repair as a
conditional result requiring broader validation. Keep the temporal method as
a research prototype: it adds supported original points, but offers no
convincing accuracy gain here and has not been tested across full DS23.
The permutation and identity scores cannot justify bypassing final gates.

Close this bounded two-scan batch and move to 0069/0291. Revisit 0068 only for a
transferable hypothesis, such as enforcing posterior phase constraints during
optimization and auditing inherited baseline qualification. Do not weaken
residual gates, assign an arbitrary time-varying curve correction or use
following elements to reach 90%. New ALGO-series promotion still requires
matched full-population mean, median, tails, regressions, availability,
association, gate qualification and runtime evidence.

## Evidence and reconstruction

Independent replay checks 554 endpoint arms and 42 nomination densities. Both
new c arms of every offered predictive position trial are replayed from their
saved phase references, with original curve/linear gate identities checked.
Ten focused tests cover wrapped density normalization, transition
normalization/horizon behavior, independent-mixture parity, clutter handling,
whole-path preservation, unique predictive ownership, unchanged curved
membership, bounded read-only archive access and debug-queue/context wiring.

Main tables:
[positions and associations](tables/position_and_association.csv),
[all family ablations](tables/family_ablations.csv),
[all interventions](tables/all_interventions.csv),
[retained residual diagnostics](tables/residual_diagnostics.csv),
[following-element profiles](tables/following_TLE_profiles.csv),
[temporal lane controls](tables/temporal_lanes.csv),
[path compatibility](tables/temporal_paths.csv), and
[all offered predictive position trials](tables/temporal_position_trials.csv).
The trial table includes rejected outputs; the main policy table uses the
declared archived fallback. RF loss across differing masks is not used as an
adoption criterion.

[Evaluation summary](evidence/evaluation.json) and the
[compressed scientific receipts](evidence/raw_scientific_receipts.tar.gz)
contain frozen protocols, hashes, exact IDs, inference outputs, nomination
screens, all ablations, restart selection, following-element provenance and
independent audits. The raw HMM discovery source and its protocol are frozen.
A mechanical execution repair removes an unnecessary graph-template lookup
for physical lanes without a graph track. The old helper is archived, and an
AST comparison verifies that only `append_fragments` changed; discovery and
likelihood mathematics are unchanged. Existing 0068 fits are reused. The
source snapshot contains the repaired implementation and documents this
version difference through the archived execution-repair receipts.

Source snapshots are in [source/tools](source/tools) and
[source/tests](source/tests). Run in the existing repository environment,
with the original persisted scan inputs and dependency versions; reference
repositories are not runtime dependencies. The stage order is inventory,
screen, nominations, positions, reentry audit, support, support finalization,
DBG01 preparation/discovery/bank/analysis, independent audit and RF restart
selection via `run_ds23_dbg01_iteration_005.py`. Then run temporal discovery,
paired positions, whole-path screening, the separate following-element
diagnostic, and `report_ds23_dbg01_iteration_005.py`. Existing frozen artifacts
are preserved rather than overwritten with new scientific outcomes. The
historical protocol hash records the pre-repair append helper; a clean
reproduction should freeze a new output directory and the repaired source
hash, retaining identical scientific thresholds.

Additional complete association views:

![0272 original associations](figures/DS23-0272_published_associated_GLRT.png)
![0068 archived associations](figures/DS23-0068_published_associated_GLRT.png)
![0068 graph fallback associations](figures/DS23-0068_graph_policy_associated_GLRT.png)
![0068 graph fallback unused](figures/DS23-0068_graph_policy_unassociated_GLRT.png)
![0068 screened independent fallback associations](figures/DS23-0068_screened_independent_associated_GLRT.png)
![0068 screened independent fallback unused](figures/DS23-0068_screened_independent_unassociated_GLRT.png)
![0068 screened temporal fallback associations](figures/DS23-0068_screened_persistent5s_associated_GLRT.png)
![0068 screened temporal fallback unused](figures/DS23-0068_screened_persistent5s_unassociated_GLRT.png)
