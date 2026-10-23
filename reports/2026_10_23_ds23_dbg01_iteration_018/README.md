# DBG01 iteration 018: recover evidence, then test the remaining family conflicts

DS23-0239 and DS23-0261 improve modestly through existing whole-curve and native-point recovery. The persistent temporal prototype raises original GLRT association from **47.05% to 50.40%** and **72.53% to 79.91%**, respectively. Fitted-c position errors fall from **2.795 to 2.520 km** and **2.780 to 2.395 km**. Both c arms improve and retain every previously accepted measurement. Neither scan approaches the 0.5 km objective.

The new bounded identity experiments reject every additional proposal. In 0261, the unused 29-point CH4 curve fails residual-structure gates under 62146. Some existing tracks are then rejected by the multi-channel support rule, rather than failing their own individual checks. A whole-family replacement with 66399 is worse on matched RF evidence. This is evidence of an unresolved curve/family conflict, not proof that all existing 62146 tracks are wrong.

This report closes the bounded debug batch, not the scientific question. No new ALGO version or full-DS23 improvement is claimed. The next unfinished scans in the frozen benchmark queue are **0338 and 0185**. Earlier 0035/0041 analyses were already completed; the recent revisit of 0081/0326 did not reset that queue.

![Association and error overview](figures/iteration_summary.png)

## Results and counting rules

| Scan | Frozen policy | Original GLRT associated | Association | Fragments | c=0 error, km | Fitted-c error, km | Fitted-c frequency RMS, Hz |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0239 | Incumbent | 646 / 1373 | 47.05% | 23 | 2.902 | 2.795 | 99.42 |
| 0239 | Whole-curve graph recovery | 669 / 1373 | 48.73% | 24 | 2.810 | 2.703 | 119.89 |
| 0239 | Graph + persistent temporal | **692 / 1373** | **50.40%** | 26 | **2.651** | **2.520** | 119.69 |
| 0239 | Independent predictive control | 692 / 1373 | 50.40% | 26 | 2.651 | 2.520 | 119.69 |
| 0261 | Incumbent / graph fallback | 1130 / 1558 | 72.53% | 40 | 2.739 | 2.780 | 91.11 |
| 0261 | Persistent temporal | **1245 / 1558** | **79.91%** | 50 | **2.405** | **2.395** | 91.14 |
| 0261 | Independent predictive control | 1246 / 1558 | 79.97% | 50 | 2.376 | 2.379 | 91.11 |

The independent control is reported separately; its slightly better GPS error does not select it over the persistent policy. The “Extra curve” panels in the complete gallery show fallback to the graph parent because that branch added no eligible source; they are not an additional successful algorithm. These are scan-level development outcomes, not additions silently applied to the population benchmark.

Association counts unique original winning GLRT measurement IDs. Fragments include accepted native paths and need not equal distinct physical satellites. For 0239, the final 692 associations contain 611 curved calibration points, 56 predictive position points, and 25 associated points unused by the position likelihood. For 0261, all 1245 associations enter position: 1060 curved and 185 predictive. Linear sources remain predictive-only and do not calibrate nuisance coefficients.

Original graph coverage caps association at 1082/1373 = 78.81% on 0239 and 1257/1558 = 80.68% on 0261. Reaching 90% therefore requires evidence outside the original graph even if every graph point could be correctly identified. The actual remaining fractions are much larger than this minimum. More associations alone do not establish better localization: 0239's noisier recovered curve increases RMS while improving evaluated position.

Exact values, point roles, strict phase checks and per-arm results: [position and association table](tables/position_and_association.csv).

## What evidence was recovered?

**0239:** The entire 23-point RX1 CH3 T001 curve, 120.78–164.50 s, can join existing family 66367 without violating the original gates. Two persistent native paths add another 23 points to existing family 100195: 12 on RX1 CH3 and 11 on RX2 CH1. All 23 native points were outside the original graph. The independent and persistent searches select the same paths. This adds measurements and channel/time support, but does not introduce a new satellite geometry.

**0261:** Whole-curve proposals fail, so the original curved set remains. Ten persistent native paths add 115 predictive points; the independent control adds 116. The added evidence improves both c arms, but leaves a roughly 2.4 km error. Complete path membership, satellite identities, spans and graph provenance are in [temporal_paths.csv](tables/temporal_paths.csv); individual path/orbit panels are in the [figure gallery](FIGURES.md).

The following panels show the accepted temporal policy's remaining evidence. Consult the legends: gray is context, and the colored points/traces identify the plotted associated or unassociated set.

![0239 remaining GLRT and tracks](figures/DS23-0239_persistent_temporal_unassociated_GLRT.png)

![0261 remaining GLRT and tracks](figures/DS23-0261_persistent_temporal_unassociated_GLRT.png)

Matching accepted GLRT panels: [0239](figures/DS23-0239_persistent_temporal_associated_GLRT.png), [0261](figures/DS23-0261_persistent_temporal_associated_GLRT.png). Incumbent, graph, extra-curve fallback and independent-control panels are preserved in the gallery.

## New test 1: try other causal identities on whole remaining sources

We tested up to two longest remaining nominated curves per scan with at least two physically qualified alternatives. Each proposal retains the whole source, every parent observation, the frozen alias nomination, original priors and original gates. Up to three qualified nominees with conditional nomination RMS ≤750 Hz were eligible; these cases supplied two each. Nominees originate from the causal catalogue search, not GPS or a hand-picked satellite list.

Each candidate receives matched c=0/fitted-c cold optimization and the existing bounded feasibility rescue when applicable. Selection requires all original gates and preservation of parent accepted IDs. Alternative identities compete on the same observation mask; RF losses on different point sets are not compared. Replacing an already valid nominee additionally requires both-arm RF gain above 2 log(candidate count).

| Scan | Whole remaining source | Points | Tested identities | Result |
| --- | --- | ---: | --- | --- |
| 0239 | RX1 CH4 T002 | 33 | 69990, 58061 | Both reject; 69990 remains structured, 58061 exceeds the RMS gate |
| 0239 | RX2 CH4 T001 | 21 | 58087, 100420 | Both reject; acceptable RMS does not eliminate structure or preserve all parent memberships |
| 0261 | RX1 CH4 T000 | 29 | 62146, 45565 | Both reject residual structure; 62146 also loses parent family support |

There are six paired trials, twelve fitted arms. **None is selected.** All numerical endpoint audits completed; successful execution is distinct from scientific acceptance. [Exact trial table](tables/conflict_alternatives.csv) and archived full gate records preserve the rejected outcomes.

### Why 0261's long curved source fails

RX1 CH4 T000 covers 214.49–250.47 s and consists of one persisted polynomial piece. Its graph polynomial RMS is 146.34 Hz. That makes it a credible curve to investigate, but does not prove an orbital identity. Under the joint 62146 addition, fitted-c profile RMS is 303.55 Hz, below the 450 Hz ceiling. However, conditional slope z=4.035, maximum step z=4.743 and lag-one correlation=0.746 reveal structured mismatch. The upward residual trend near the end is visible below. No points were trimmed.

![0261 whole-family CFO and conditional residuals](figures/DS23-0261_family_conflict.png)

The orange line includes the predicted orbit and fitted nuisance terms; it is not a bare orbit prediction. All original points of each source are shown. Lines between observations only aid reading and do not imply measurements during gaps.

Gate replay distinguishes two mechanisms:

| Fitted-c source | Points | Own profile/conditional/alias/elevation gates | Final result |
| --- | ---: | --- | --- |
| RX1 CH1 T000 | 31 | Pass | Rejected by family support cascade |
| RX1 CH1 T001 | 25 | Pass | Rejected by family support cascade |
| RX1 CH4 T000, newly proposed | 29 | Fail profile and conditional noise | Rejected directly |

The 62146 trial enables orbital-shape corrections using nominal support on CH1 and CH4. Once CH4 fails, the passing tracks occupy only CH1. The existing rule requires at least two distinct (receiver, channel) owners for a family with those corrections, so it removes the remaining support. In c=0, CH1 T001 additionally fails its own noise checks; CH1 T000 still fails only through the cascade. All three sources are above the horizon; this particular rejection is not a visibility failure. [Gate attribution](tables/family_gate_attribution.csv) records every base gate and support outcome.

This is a useful diagnostic improvement: a family-wide rejection count can exaggerate how many curves independently contradict the orbit. It does not justify removing the support rule. The existing support-aware recovery also protects incumbent families and cannot simply disable their orbital coordinates because a new addition fails.

## New test 2: nominate and refit the entire conflicting family

We generalized the existing augmented-family trigger from at least two new curved sources to at least one, without relaxing any acceptance gate. The trigger selects the largest failed whole-source addition to an already active family. Only 0261 qualifies. Its 56 incumbent 62146 curved points and 29 new points are held out together while the remaining evidence calibrates the nomination model.

The full causal catalogue is screened coarsely, then the best seven plus the incumbent are refined. The original family identity and best qualified alternative receive full joint cold fits on the same 85-point family and identical remaining observations. Whole-family 62146 has cavity score 1249.67; the best qualified alternative, 66399, scores 1385.96. In the final matched joint fits, 66399 has RF gains of **−83.06 (c=0)** and **−83.32 (fitted c)** relative to 62146, where a positive gain above 2 log 2 is required. Both joint identities also fail gates. Nothing is adopted.

![Whole-family causal identity test](figures/DS23-0261_family_replacement.png)

[Nomination table](tables/whole_family_candidates.csv), [paired refits](tables/whole_family_refits.csv). This rejects the tested wholesale replacement; it does not establish that 62146 is the true identity of the new CH4 curve or exclude mixed identities, imperfect nuisance models, or other catalogue limitations.

Following-observation TLEs were inspected only as diagnostics. For this CH4 source, the diagnostic 62146 profile RMS changes from 173.24 to 172.81 Hz after independently fitting phase. The fitted phase changes from approximately −0.79 to +0.22 s. The 45565 diagnostic changes from 176.14 to 176.23 Hz. These are uncertainty-marginal diagnostic profiles and must not be confused with the final joint gates above. They provide little evidence that a newer TLE alone repairs the conflict. They never enter the reported position fits. [Following-TLE table](tables/following_TLE_profiles.csv).

## Is the position error an optimization failure, one bad family, or weak information?

The incumbent objective prefers the displaced solutions even when initialized at the evaluation position. Both fitted-c true-position starts return to the original endpoints, to numerical tolerance. Endpoint gradients are near zero; gradients at the true site are not. The RF-selected restart searches achieve only about 9e−8 and 7e−8 objective improvement, far below the 2.773 search penalty. No restart is adopted. More starts alone do not repair these particular incumbent models.

The 10 km loss panels evaluate a spatial grid while refitting nuisance terms and refreshing phase with the original fixed associations. The multistart panels use 81 starting positions and may reselect among up to four pre-nominated assignment branches during descent. They do **not** rerun acquisition, GLRT, graph construction or the entire satellite catalogue at every grid cell or step. They diagnose the incumbent association/position model, rather than proving global optimality for arbitrary unseen identities.

![0239 loss and gradient](figures/DS23-0239_loss_gradient_10km.png)

![0239 multistart paths](figures/DS23-0239_convergence_10km.png)

![0261 loss and gradient](figures/DS23-0261_loss_gradient_10km.png)

![0261 multistart paths](figures/DS23-0261_convergence_10km.png)

Twenty-three satellite-family ablations and 53 curved-track ablations were evaluated in both c arms. The best fitted-c family deletion gives 0239 error 2.370 km by dropping 100195, and 0261 error 2.433 km by dropping 61625. Neither identifies a single deletion that approaches 0.5 km. Removing 66367 from 0239 worsens error to 6.105 km, consistent with its useful geometric constraint. Deletions chosen for GPS improvement are diagnostic and are not adopted. Full results: [family ablations](tables/family_ablations.csv), [all interventions](tables/all_interventions.csv).

![0239 family, source and prior controls](figures/DS23-0239_influence_and_controls.png)

![0261 family, source and prior controls](figures/DS23-0261_influence_and_controls.png)

The phase-prior controls do not suggest a common quick fix. Doubling phase width gives fitted-c errors 2.795 and 2.210 km; using zero phase-prior means gives 2.265 and 2.915 km. The latter helps one scan and hurts the other. We do not select scan-specific priors using the known position.

### Local sensitivity to nuisance uncertainty

We recomputed local position information after projecting out uncertain nuisance coefficients. This uses curved evidence only, holding the fitted Gamma noise precision fixed. Derivatives were checked at 20 m and 10 m steps and the projection independently checked by QR/Schur calculations. Eight endpoint/true-site, c0/fitted-c configurations were audited.

| Fitted-c incumbent endpoint | All nuisance uncertain: major-axis scale, km | Phase coefficients held fixed, km | Receiver smooth coefficients held fixed, km |
| --- | ---: | ---: | ---: |
| 0239 | 1.500 | 0.226 | 0.957 |
| 0261 | 1.253 | 0.168 | 1.057 |

![Local nuisance-projected information](figures/local_information.png)

These scales are local model diagnostics, **not calibrated confidence intervals, achieved errors, or irreversible resolution limits**. “Held fixed” means fixing coefficients at their fitted values as an ideal-information intervention; no real measurement supplies that knowledge. Predictive-only points are excluded from this calculation. The result identifies phase/position ambiguity as a substantial direction to investigate, not permission to assert that phase is known or to tighten priors arbitrarily. Real prior controls above show why that distinction matters.

The [calibration timeline](figures/calibration_timeline.png) locates independent curved evidence by owner/family; [objective decomposition](figures/objective_preference.png) shows why the incumbent objective prefers its endpoint over the true site. Receiver/family residual panels are preserved for [0239](figures/DS23-0239_track_residuals.png) and [0261](figures/DS23-0261_track_residuals.png). Exact local diagnostics: [local_information.csv](tables/local_information.csv), [local_review.json](evidence/local_review.json).

## Controls, provenance and reproduction

Inference starts at [0,0] in the original 25×25 km box centered at **37.906, −122.545**. The evaluation site, **37.849061591561885, −122.48574968092912**, is used for debug prioritization, diagnostic true-site plots and final errors only. Inference retains causal TLE epoch and collection cutoffs, original physical phase bounds, aliases, priors and residual gates. c=0 and fitted-c observations, candidates, other priors and search budgets remain matched. No new RF collection, IQ processing, stationary-history pooling, manually selected identity, point trimming or truth-selected prototype is introduced.

The existing frozen iteration018 batch and recovery fits were reused rather than rerun. This turn completed independent recovery endpoint audits, generated the report/atlas, executed the two new bounded identity experiments, and computed the local information and gate-attribution diagnostics. The base batch, its independent audit, all eight temporal-arm replays, twelve alternative-arm replays and four augmented-family-arm replays completed. Execution success does not turn rejected proposals into associations.

Thirteen targeted tests pass; [test output](evidence/tests.txt). Tests cover queue binding, recovery binding/audit, distributed curvature, the new RF-only alternative and family trigger, and local information calculations. Frozen numerical audits independently replay objectives, density calculations, original gates and accepted measurement IDs. The raw evidence archives contain the original fit histories, proposals, complete residual gates, causal and following-TLE diagnostics, restart/grid outputs and new experiment protocols. [Archive manifest](evidence/archive_manifest.json) gives archive hashes and counts. [Source hashes](evidence/source_hashes.json) identify the report snapshots.

Relevant source snapshots are under [source/tools](source/tools). Run from the repository root with `src`, repository `tools`, and this report's `source/tools` on `PYTHONPATH`. `audit_iteration018.py` verifies saved recovery; `report_iteration018.py` renders the standard atlas; `information_iteration018.py` renders local information; `supplement_iteration018.py` reconstructs gate attribution without fitting. `probe_iteration018_conflicts.py` implements whole-source alternatives and `--family` the augmented-family test. Probe runners intentionally refuse to overwrite completed experiment protocols; reproduce in a separately bound output directory. The source snapshots reuse the ALGO02/03 scientific implementation and earlier published recovery components; they are not a new standalone localization package.

All 48 figures are indexed in [FIGURES.md](FIGURES.md). CSV tables preserve both c arms, rejected trials and exact numerical values. Small visual differences between diagnostic profiled residuals and final conditional residuals reflect their different conditioning and must not be treated as interchangeable gates.

## Decision and next bounded work

Keep the modest graph/native recovery gains as development evidence. Keep the six identity alternatives and whole-family replacement rejected. Preserve the incumbent full-DS23 benchmark: 410 available scans of 413, fitted-c mean/median **1.469/1.178 km**, original GLRT association **70.08%**; the inherited strict-phase exception on 0068 remains disclosed. No population rerun or generalization gain is implied by this two-scan report.

Move the routine debug queue to **DS23-0338 and DS23-0185**, whose frozen fitted-c errors are 2.770 and 2.701 km. For a future shared-method experiment, prioritize independent curved cross-owner evidence and uncertainty-aware phase calibration. Any support-adaptive orbital model must be fitted and penalized as a separate model on identical observations, not obtained by ignoring a failed owner. Before a new ALGO release, freeze the rule and evaluate matched c arms across DS23, including the prior rescued and regressed scans. Do not spend another unrestricted batch on 0239/0261 without new evidence or a transferable model hypothesis.
