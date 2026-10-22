# DS23 iteration011: paired RF evidence and supported native-path recovery

Building on [ALGO02](../ALGO02/README.md) and the existing
[ALGO03 family-replacement research](../2026_10_22_ds23_family_cavity_full_assessment/README.md),
this iteration finds two local improvements and a small full-population candidate.
Requiring a proposed family replacement to improve RF evidence in **both**
calibration arms reduces full-DS23 fitted-c mean/median error from
**1.469461/1.178102 to 1.462402/1.167197 km**. Only two of410 available scans
change. Association coverage and the count within0.5km are unchanged. This is
provisional evidence, insufficient for a new ALGO release or a claim of
generalization. The mean-and-median0.5km goal remains unmet.

The bounded DBG01 batch is **0163/0209**. A same-mask RF parent comparison plus
the existing temporal recovery improves0163 from3.129 to2.709km and association
from56.31% to61.33%. Existing temporal recovery improves0209 from3.051 to2.907km
and association from68.13% to72.19%. These are development results, not a
full-population rollout of that local policy.

![Local results](figures/iteration_summary.png)

## Controlled protocol

Inference uses the existing graph polynomials, original winning GLRT observations,
causal catalogue, physical priors, integer aliases and phase-refresh engine.
No new RF collection, IQ reprocessing, manually assigned satellite identities,
motion model or pooling of stationary positions is introduced. Linear evidence
is predictive; it does not learn radio calibration. Every new final fit starts
at[0,0] in the original **25×25km box centered37.906,-122.545**. Diagnostic
restarts additionally use the81 established starts in the10km disk.

Each comparison retains matched observations, candidate hypotheses, aliases,
noise powers, other priors, gates and budgets in **c=0 and fitted-c** arms.
Evaluation GPS **37.849061591561885,-122.48574968092912** ranks debug cases and
measures final accuracy; it does not select the RF hypotheses. Following TLEs
appear only in diagnostic figures. Retained old failures and unavailable cases
are explicit. See the frozen [batch protocol](evidence/protocol.json).

## Full DS23: a paired evidence guard

The published family-replacement policy selects the same lowest corrected
c=0-loss challenger among already paired-gate-valid trials and adopts it when
its c=0 evidence gain is positive. In0080, that accepts a known harmful change
from66381 to67014: c=0 gain+0.3043, fitted-c gain−0.3128. This is a calibration
model sensitivity warning available without GPS. The change was already known;
it motivates this experiment and is not an untouched validation case.

The primary candidate preserves that exact challenger, observations and fitted
endpoints, but requires **both normalized RF gains to be positive**. The
normalization subtracts the original unused Student-prior constant. There is no
new search, candidate reranking, pose optimization, identity prior or tuned
threshold. This borrows the same-mask positive-gain principle already present
in ALGO02 combined recovery. Selection for all410 cases is frozen before the new
geographic comparison. The two arms share one decision.

Two existing-style controls are retained: a fixed2log2 margin in both arms,
and the published incumbent-preference/search-penalty rule. The margin is not
swept or chosen using geography. The following is a **decision replay of saved
causal pipeline results**, not410 new acquisition-to-position runs.

| Rule | Arm | Replacements | Mean km | Median km | P90 km | Improved / worsened vs published |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Published c=0-positive | c=0 |74|1.479378|1.190706|2.575508|0 /0|
| Both gains positive | c=0 |72|**1.474109**|**1.181122**|2.568884|2 /0|
| Both gains >2log2 | c=0 |70|1.473538|1.181122|2.568884|4 /0|
| Published sticky control | c=0 |9|1.498232|1.208241|2.662251|33 /32|
| Published c=0-positive | fitted c |74|1.469461|1.178102|2.619963|0 /0|
| Both gains positive | fitted c |72|**1.462402**|**1.167197**|2.550646|2 /0|
| Both gains >2log2 | fitted c |70|1.462365|1.167197|2.550646|3 /1|
| Published sticky control | fitted c |9|1.489249|1.169162|2.693838|31 /34|

All410 available scans of413 remain included;0012,0184,0286 are unavailable.
Both-positive changes only0080 and0273, leaving408 returned fits exact.
Fresh replay confirms the **same original associated point ID sets** before
and after each changed decision:0080 has2533/3270 points and0273 has699/1040
in each arm. Therefore the published full-population coverage remains
**726,425/1,036,559=70.08043% fitted-c** and726,622/1,036,559=70.09943% c=0.
This conclusion combines exact fallback provenance with fresh membership
checks on every changed case; it is not a fresh membership sweep on all410.

| Changed case | c=0 gain | Fitted-c gain | Published fitted-c error km | Both-positive error km |
| --- | ---: | ---: | ---: | ---: |
|0080|+0.304286|−0.312806|3.236264|**0.711902**|
|0273|+0.337357|−1.397290|2.857551|**2.487656**|

The fixed-margin control additionally changes0213 and0252. It harms0213 by
45.55m while helping0252 by60.42m in fitted c. Its slightly better aggregate
mean is not a reason to select a margin after seeing these outcomes. The sticky
control has10 regressions exceeding500m in fitted c. Simply protecting every
incumbent is not a solution either.

![Matched population metrics](figures/full_DS23_paired_guard_summary.png)
![RF gains in the two calibration arms](figures/full_DS23_RF_gain_comparison.png)
![Every available scan](figures/full_DS23_by_scan.png)

The mean benefit is7.06m and median benefit10.91m in fitted c. The worst error
remains16.980km and the within0.5km count stays48/410. Both arms retain409/410
strictly qualified results;0068's inherited phase>15s exception is unchanged
and is not hidden by dropping it. Mean fitted-c GLRT RMS changes only
110.624592→110.623333Hz. That negligible fit change does not establish geographic
accuracy; the geographic result is evaluated independently above.

### Scope and uncertainty

| Format | Scans | Published fitted-c mean / median km | Both-positive mean / median km |
| --- | ---: | --- | --- |
| Fast |204|1.240377 /1.031316|1.228003 /1.029732|
| Adaptive |206|1.696320 /1.333925|1.694524 /1.333925|

Only one fast and one adaptive case change. Whole UTC-block bootstraps use
5000 draws, fixed seed2026102211, and1h/3h/6h blocks containing107/37/19
occupied blocks. For the3h choice, the fitted-c mean-change95% interval is
**[−20.89,0]m**, and median-change interval **[−23.15,0]m**. These are descriptive
after extensive same-site engineering, not independent confirmation. Outside
the original engineering three, only0273 changes. Nothing here establishes
performance at new receiver locations. The sensible outcome is a provisional
guard candidate, preserving the published benchmark and ALGO IDs.

![Temporal-block sensitivity](figures/full_DS23_temporal_uncertainty.png)

## DBG01:0163, ambiguity between two graph parents

The incumbent associates932/1655 points, with747 curved calibration and185
predictive likelihood points. The long unused **RX1CH1T000**,31 points over
227.804–261.608s, has one persisted polynomial piece. Its leading58629 causal
phase-only diagnostic RMS is182.19Hz; a following TLE gives182.16Hz. However,
the final joint58629 trial has fitted-c RMS234.76Hz and fails residual slope
z=3.326, step z=4.974 and ACF0.792. The ACF limit is4/√31=0.718. RMS below
450Hz is insufficient. No wrong join is established merely from one failed
orbital fit or from the polynomial degree.

A second source, **RX1CH2T005**,16 points over227.944–249.743s, passes under
62997 in the default recovery. Its58629 alternative passes in support-aware
recovery. Both parents add exactly the **same16 curved likelihood points**
and retain the same predictive factors, so a normalized RF score comparison is
meaningful. Their post-fit association extensions differ; the comparison does
not mistake that descriptive extension for a different likelihood mask.

The previous point-count tie defaults to62997. A bounded alternative chooses
support58629 only when it is already paired-qualified, its entire likelihood
mask and predictive signature match, and its normalized full-data RF bound
improves by **>2log2 in both arms**. Gains are10.8549(c=0),9.1615(fitted c).
The choice is frozen before fitting any new child or scoring geography.
Unequal masks never enter this raw score comparison.

|0163 policy|Associated original GLRT|Calibration / predictive points|c=0 error km|Fitted-c error km|
|---|---|---|---:|---:|
|Incumbent|932/1655=56.31%|747 /185|3.234675|3.128580|
|Default graph parent62997|971/1655=58.67%|763 /185|2.938261|2.788166|
|RF-selected graph parent58629|948/1655=57.28%|763 /185|3.490750|3.400981|
|Default-parent temporal policy|971/1655=58.67%|763 /185|2.938261|2.788166|
|RF-parent persistent5s temporal policy|**1015/1655=61.33%**|763 /252|**2.877481**|**2.709340**|

RF selection alone worsens geography despite a better frequency bound. Its
benefit appears only when the independently screened temporal evidence is
added. The default parent's temporal trials fail the retained62997 source's
slope gate(c=0≈3.426,fitted-c≈3.193); neither low-error rejected trial is adopted.
The new parent's persistent trial admits67 predictive points in6 paths and
passes both arms. The independent-state control admits63 points but ends at
3.197km fitted-c. Persistence was the predeclared primary, not selected from
the geographic winner. No incumbent associated point ID is lost.

![0163 before, unassociated](figures/DS23-0163_incumbent_unassociated_GLRT.png)
![0163 after, associated](figures/DS23-0163_rf-parent_temporal_policy_associated_GLRT.png)
![0163 after, unassociated](figures/DS23-0163_rf-parent_temporal_policy_unassociated_GLRT.png)
![0163 offered temporal paths and residuals](figures/DS23-0163_persistent5s_paths_1.png)

Gray points in these plots are **all original GLRT**, red points are unused,
and colored polynomial lines are display fits. Associated plots color points
by the satellite hypothesis. Recovered samples are not synthesized evidence.

### Why the two curved sources should not simply be merged

Both sources nominate58629, but their same-RX RF-normalized curvature is
inconsistent over the **actual shared time interval**. We compare degrees1–4
with BIC, allowing separate affine terms for constant band/alias shifts and
small linear drifts. Whole-window BIC slightly favors shared curvature(−3.66),
while strict-overlap BIC strongly favors independent curvature(+29.06).
Within overlap, shared degree3 RMS110.84Hz compares with independent degree4
RMS56.68Hz. This is a GPS/TLE-independent diagnostic, not an identity posterior
or an automatic deletion gate. It illustrates why a cheap shared polynomial
over unequal windows can mask local disagreement. The31-point source is not
forced into58629 to increase coverage.

![RF-only curvature comparison](figures/DS23-0163_shared_curvature.png)
![0163 causal and following TLE diagnostics](figures/DS23-0163_unused_track_TLE_diagnostics.png)
![0163 retained residuals](figures/DS23-0163_track_residuals.png)

## DBG01:0209, native prediction helps modestly

The incumbent associates1024/1503 points(68.13%), using912 curved and112
predictive likelihood points. Its longest wholly unused curved nominee is
**RX1CH4T004**,22 points over32.584–57.032s. Leading57338 phase-only diagnostic
RMS155.39Hz becomes155.14Hz with a following element. The final c=0 whole-source
trial fails slope z=3.099>3 and step z=3.034>3 despite RMS165.99Hz. Fitted c
passing alone cannot qualify the shared proposal. No graph reentry passes.

The original-parent temporal method recovers **61 predictive points in7 paths**,
preserves all original associated IDs and reaches **1085/1503=72.19%**,
c=0 error3.134273km and fitted-c error2.906811km. The independent-state control
recovers70 points, reaches72.79% and2.837646km fitted-c; it remains a named
control rather than replacing the frozen persistent primary based on GPS.

The previously run iteration010 short-curve confirmation on0209 is reused,
not repeated. It added16 calibration points and led to1076/1503=71.59%
associated, c=0 error3.151668km and fitted-c error2.965875km. These are separate
policies; short and temporal gains are not added together without a matched
joint experiment. The20-case short-curve confirmation failed overall mean
improvement and remains unpromoted.

![0209 before, unassociated](figures/DS23-0209_incumbent_unassociated_GLRT.png)
![0209 after, associated](figures/DS23-0209_rf-parent_temporal_policy_associated_GLRT.png)
![0209 after, unassociated](figures/DS23-0209_rf-parent_temporal_policy_unassociated_GLRT.png)
![0209 paths, page1](figures/DS23-0209_persistent5s_paths_1.png)
![0209 paths, page2](figures/DS23-0209_persistent5s_paths_2.png)
![0209 causal/following diagnostic](figures/DS23-0209_unused_track_TLE_diagnostics.png)
![0209 residual checks](figures/DS23-0209_track_residuals.png)

## Loss surfaces, optimizer basin and family ablations

For each scan, the original DBG01 conditional loss evaluates the same incumbent
observations at a spatial grid, refreshing phases; it does not rerun acquisition
and association at each pixel. Descent arrows are local directions. The second
figure runs81 independent regional starts through the bounded association bank:
curved labels/aliases may change under the existing c=0 step rule, fitted c
follows that schedule, and predictive labels remain fixed. This is not a fresh
full-catalogue association search at every descent point. Purple open diamonds
are **intermediate phase-round endpoints**; orange X marks the final endpoint
after five rounds. These surfaces diagnose the incumbent, not the new temporal
policy. GPS stars are report-only.

All81 restarts in each scan qualify, and their best RF improvement over the
incumbent is only≈3e−9, far below the2log2 restart preference. Restart search
does not remove this bias. The0163 gradient at the true site points toward the
biased minimum: this is evidence against a simple optimizer-start failure
within the tested bank, not proof that every possible association is correct.

![0163 loss and gradient](figures/DS23-0163_loss_gradient_10km.png)
![0163 starts and phase rounds](figures/DS23-0163_convergence_10km.png)
![0209 loss and gradient](figures/DS23-0209_loss_gradient_10km.png)
![0209 starts and phase rounds](figures/DS23-0209_convergence_10km.png)

Removing individual satellite families produces many small shifts, without a
single-family cure. Best paired-valid fitted-c deletion gives0163
2.805794km(removing58494), and0209 2.709384km(removing58869). These deletions
are ranked by evaluation error solely to explain sensitivity; no GPS-ranked
deletion is adopted. Generic phase-prior controls also shift endpoints but
are not tuned or promoted for these scans. Remaining bias can reflect multiple
model/association discrepancies and weak geometry; these experiments do not
identify a unique receiver or orbital cause.

![0163 family, source and prior controls](figures/DS23-0163_influence_and_controls.png)
![0163 loss decomposition](figures/DS23-0163_loss_decomposition.png)
![0209 family, source and prior controls](figures/DS23-0209_influence_and_controls.png)
![0209 loss decomposition](figures/DS23-0209_loss_decomposition.png)

## Why90% is not forced

The original graph covers1355/1655=81.87% of0163 and1218/1503=81.04% of0209.
Even perfect association within those graphs cannot reach90%. Each scan would
need at least135 points outside its current graph. Native temporal recovery can
use outside-graph original detections but is conditional on existing families,
independent path identity checks and unchanged final residual gates. It is not
a license to assign all remaining clutter. Local recovery is useful but still
leaves substantial original data unmodeled.

## Timestamp repair, numerical audit and validation

The first0209 temporal run exposed a post-fit extension index error: appended
native timestamps were searched into the original graph-only global time grid.
A timestamp beyond that grid could index past its end; interior timestamps
could map to a later graph time. The likelihood already used native flat times.
The repair unions original and appended native timestamps and recomputes exact
indices for every track. It preserves times, CFO, IDs, receiver basis, noise,
priors and fitted endpoints. No interpolation or resampling is introduced.

Fourteen previously saved arms from0080,0257 and0163 are independently replayed:
objective and coefficient deltas are exactly zero and accepted ID sets are
identical. Successful0163 output is reused byte-for-byte. Only the failed0209
run is resumed with the same proposal/fit budget; its already frozen discovery
and selection records agree exactly. Old failure output and pre-fix sources
remain in the evidence archive. The native adapter now uses the corrected
helper; published historical source snapshots remain unchanged.

Validation includes **19 passing component tests**,516 independent scientific
endpoint-arm checks in the standard batch audit,16 fresh temporal endpoint
checks, and16 fresh full-guard changed-configuration arms. These independently
check expected RF log densities, coefficient equations and dense predictive
covariance, replay original curved/predictive gates and exact physical ID
membership. The first guard audit's legacy linear-gate schema mismatch is
preserved; the repaired audit uses the existing strict legacy comparator.
There are no public contract, golden fixture or production-default changes.

## Evidence and reproduction

All48 figures,16 CSV tables, five compressed raw-evidence partitions(each<9MiB),
protocols, frozen choices and changed source/test snapshots are included.
See [table inventory](tables/), [complete figure gallery](FIGURES.md),
[archive hashes](evidence/archive_manifest.json),
[standard numerical audit](evidence/independent_iteration_audit.json),
[temporal endpoint audit](evidence/temporal_endpoint_audit.json),
[guard endpoint audit](evidence/paired_guard_changed_endpoint_audit.json),
[all410 guard decisions](evidence/paired_guard_RF_selection.json), and
[source hashes](evidence/source_hashes.json). Saved causal input roots are
referenced rather than copying radio corpora into Git. Snapshots require the
existing research environment; they are not a standalone deployment package.

The source tools preserve existing outputs. To reconstruct in a fresh output
tree, use the existing scientific environment, bind a new output root and run
the iteration011 batch, existing-recovery diagnostics/paths, explicit native
time repair, same-mask parent selection/application, paired replacement
selection/evaluation, both numerical audits, population sensitivity and report
builder. Their frozen JSON protocols specify order, reused010 evidence, seeds,
physical priors and source hashes. Do not overwrite immutable experiment output
to rerun a report or silently change archived inputs.

The next bounded cases are **0215/0281**. Close0163/0209 for now. Retain the
paired guard as a provisional ALGO03 candidate and require broader evidence
before adoption or an ALGO-series release. A two-case coverage gain, a better
in-sample RF score, or an exhaustively studied same-site result is insufficient
to claim the0.5km target or new-location accuracy.
