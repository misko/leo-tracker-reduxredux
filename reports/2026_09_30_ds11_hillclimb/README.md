# DS11 single-scan positioning hill climb

The [fixed-height preflight](fixed_height/preflight.json) now passes on original
scans0/16. With externally fixed height zero, predictions and training scores
match the baseline exactly; gradient differences stay below1e-12 and numerical
derivative discrepancies below3.3e-6. Two component tests pass, including
nonzero-height derivatives and held-data isolation. This prepares a physical
fixed-height comparison while retaining all original satellite mixtures.
Independent antenna altitude and datum remain pending; no nonzero-height
position fit or accuracy claim follows from software parity alone.

The read-only [external altitude evidence](altitude_evidence/external-evidence.json)
adds a terrain estimate54.5716m and GEOID18 undulation-32.477m at the operator's
site coordinates. The terrain response reports1m resolution and2018-03-02
acquisition, but does not explicitly return a vertical datum or publication
date. These are not antenna altitude or a direct WGS84 height conversion.
Roof/mount height and datum remain unresolved; a measured-altitude question is
pending with the user. No antenna height is selected and no position fit runs.
The source authorities explain [USGS elevation interpolation](https://www.usgs.gov/faqs/how-accurate-are-elevations-generated-elevation-point-query-service-national-map)
and [NOAA's NAD83/NAVD88 geoid conversion](https://www.ngs.noaa.gov/web_services/geoid.shtml).

`historical_orbit_scale/` finds exploratory evidence for age-dependent orbit
revision uncertainty, independently of radio residuals or geographic errors.
A normalized zero-mean isotropic3D t4 scale learned on921 historical training
cases is exp(0.3501)*(1+age_days)^1.8065km. Against a fitted constant scale,
the exposed validation panel has67/120 satellite wins, mean gain0.04886nats
and median gain0.07483nats per source, passing its exploratory gate. All three
fits qualify and three component tests pass. This is not a Doppler covariance.
The frozen independent confirmation on the next date excludes all256 previously
exposed satellites and samples256 new ones, but finds zero strictly advancing
epoch triplets under the cutoff. Confirmation is unavailable, not negative
accuracy evidence. No cutoff/cohort is retuned, no DS11 weighting changes, and
the primary position goal remains active.

The historical orbit-revision forecast in `historical_orbit_forecast/summary.json`
fails its frozen validation gate. Calibration uses 921 cases from133 satellites;
validation uses396 cases from120 different satellites on later dates. The fitted
bounded revision coefficient is0.8080. Median position-vector reference-proxy
error falls7.520→6.247km (16.9%), but mean error falls23.002→22.247km (3.3%),
below the required5%. There are234/396 case wins. These are differences against
later orbital elements, not orbit truth or receiver position errors. No DS11
forecast correction is applied, and no gate or bound is relaxed after scoring.
All12 corrected propagation exports succeed; the12 initial sampling-grid
failures remain recorded. The primary causal improvement goal remains active.

The separately authorized [offline archived-orbit pilot](offline_orbit_pilot/summary.json)
now completes original scans22/23, selected by newer epochs affecting
training-supported candidates. Replaying original states gives exact agreement.
All eight starts qualify, and training selections precede geographic scoring.
Later orbit states change errors2812.785→2898.242m and3578.736→928.700m;
held Doppler prediction improves on both scans, with four/eight inferred identity
changes. This is a material offline gain on one scan and a loss on the other,
not a causal improvement or general accuracy result. The primary goal remains
active and original causal outputs remain the default.

The [crossed offline state/identity ablation](offline_orbit_ablation/summary.json)
also completes all16 starts with qualification. On scan23, later states with
original fixed labels reduce3578.466m to486.369m; later labels with original
states give3402.852m. On scan22 the same crossed cells give3219.707m and2353.364m
against2794.696m original states/original labels. Fixed labels are diagnostic,
not authenticated identities or the original soft-mixture estimator. No cell
is selected by geographic performance for deployment. The scan23 gain therefore
motivates independent historical orbit-state calibration while leaving causal
accuracy improvement unproven.

Research-local experiments on existing DS11 GLRT tracks. No new RF collection, production changes, golden updates, cross-scan position pooling, or reference-coordinate optimizer prior. The unsurveyed roof reference is used only to score completed estimates. This is exposed-site model development, not surveyed or blind accuracy validation.

The user explicitly keeps **causal positioning primary**. Later archived orbit
updates may be studied separately as offline diagnostics; they cannot count as
achieving the primary improvement goal. The [four-hour availability inventory](delayed_orbit_inventory/README.md)
finds changed elements for 1495/3071 candidate occasions but only a modest
change in median epoch proximity. It includes no propagation or position fit.
The separate [causal availability audit](causal_orbit_inventory/README.md)
finds no fresher elements lost through provider rollback within three days.
It identifies a narrower question: the exporter excludes snapshots timestamped
within 505seconds before recording start. Including them changes meaningful
epochs on two original scans. However, the collector stamps request start,
before downloading and fsyncing the bytes. Separate completion evidence is
therefore required before treating these updates as available at recording
time. The 505second guard's exact rationale remains undocumented; no causal
position experiment may remove it on timestamp evidence alone. Exact completion
receipts have now qualified five specific replacements. Their
[completed causal ablation](causal_fresh/README.md) produces one substantial
single-scan gain, with unchanged full-panel median. A subsequent
[five-scan confirmation](causal_fresh_confirmation/README.md) fails to transfer
that gain: three exact no-ops and sub-metre changes on two scans. Its only
newer-epoch candidate has essentially zero fitted support. The isolated gain
is verified, but a general freshness-driven positioning improvement is not.

## Outcome

The [combined source-policy trade-off audit](policy_tradeoff/summary.json)
keeps all44 attempts explicit, with43 matched qualified outputs and one shared
baseline/policy failure. On those43 pairs, source balancing changes median
2705.981→2807.292m, mean3608.764→3267.132m, andP90 7339.845→6308.478m;
there are24 wins,18 losses and one tie. These matched-only pooled figures do
not provide full44-output metrics. The additional11 matched outputs regress
on median, mean andP90, so pooling does not reverse the failed replication gate.
All228 source bindings in the two original audit documents verify and two
aggregation tests pass. The user's preferred accuracy objective (median,
mean or tail) is pending clarification; no existing gate is changed meanwhile.

No tested model earned promotion as a dependable lower-median-error replacement for original IID. There are measured improvements in mean error, tail error and sub-km yield, but they trade against median error or fail on additional recordings. Retain original IID as the default and preserve the alternatives as research candidates.

A new [direct waveform correction ablation](norad65512_position/README.md)
produces a small scan-0 gain: the longer pilot fit lowers reference error
765.072m→751.262m, while the shorter fit worsens it to773.810m. All eight
starts qualify; neither arm changes any of62 conditional MAP NORAD assignments.
This is a13.810m gain on one exposed recording, not a demonstrated improvement
in typical DS11 error. Both arms remain reported and no policy is promoted.

| Original 32 independent scans | Qualified outputs | Median | Mean | P90 | Sub-km | Paired wins |
|---|---:|---:|---:|---:|---:|---:|
| Original Student-t4, scale100Hz |32/32|2759m|3785m|7708m|2|—|
| IID with verified pre-capture orbit updates |32/32|2759m|3679m|7342m|2|3, two below1m|
| Student-t4, scale200Hz |32/32|3102m|3665m|6692m|7|20|
| Student-t8, scale100Hz |32/32|3089m|3711m|7336m|6|21|
| Tempered source weights, power0.50 |32/32|2695m|3485m|6274m|3|26|
| Full source weights + qualification-only IID fallback |32/32, one fallback|2300m|3257m|6029m|3|21|

The two source-weighting rows fail the additional-panel geographic check. The two Student-t rows improve tails and sub-km counts but fail the all-32 median gate; neither advanced to the additional panel. These comparisons must not be collapsed into a claim that every accuracy metric improved.

## Source-balancing candidate: development gain, failed replication

Balance the original independent Student-t4 track likelihood by physical satellite/RF source, splitting each source's total unit weight equally across receivers and then their repeated tracks. Group identities are frozen using training data at the original same-recording IID solution; conditional candidate confidence must reach 0.90. Ambiguous tracks remain unit-weight singletons. Candidate mixtures remain complete during optimization. The bank IDs are catalogue row indices; `source_balance/catalogue_identities.json` binds them to NORAD identities through the archived roster.

The candidate is a composite weighted objective, not a normalized physical posterior or authenticated satellite identification. It plausibly reduces overweighting of repeated observations with shared modeling errors; these experiments do not establish the physical cause.

The raw source model qualifies on 31/32 original recordings. Original index 26 reaches the west search boundary from all four starts. The explicit policy uses the qualified source fit, falling back to the original IID estimate only when the source fit is unqualified. This rule was declared after observing that failure, then frozen before additional-recording evaluation.

| Original panel | IID median | Policy median | IID P90 | Policy P90 | Paired wins | IID fallbacks |
|---|---:|---:|---:|---:|---:|---:|
| Screen8 |3108.16m|2106.51m|6046.04m|5256.47m|7/8|0|
| Remaining24 |2655.35m|2579.03m|7961.33m|6338.73m|14/24|1|
| All32 |2759.38m|2300.23m|7708.23m|6029.00m|21/32|1|

Across all 32, policy mean error falls 3784.91m→3257.44m; maximum 8540.08m→7748.62m; sub-km count 2→3. The overall median reduction is 16.64%, but the remaining 24 median reduction is only 2.87%. Successful-only raw-model medians must not replace these full-denominator comparisons. Common-IID held score worsens by 948.21 in aggregate; this is a geographic improvement candidate, not evidence of improved likelihood calibration. Median challenger runtime is 28.1 seconds, in addition to obtaining the IID initializer (original median 24.8 seconds).

Exact audited outputs and provenance: `policy-original32-audited.json`, `source_balance/aggregate-source_receiver_equal-32.json`, and per-start records under each family's `runs/`. The preliminary `policy-original32.json` is retained; `policy_audit.py` adds independent input, identity, baseline, receipt and failure-denominator checks.

The separate twelve-recording check in `additional-policy.md` **failed**. It retained all 12 attempts: 11 qualified source fits and one policy failure, with no IID fallback. Additional index 9's original IID fit reached the west boundary from all three starts, so the source model had no qualified initializer. Whole-panel median/P90 are unavailable; the following comparison explicitly uses the 11 matched qualified outputs:

| Additional matched 11 of 12 | Original IID | Source-balanced policy |
|---|---:|---:|
| Median |2568.39m|3089.82m|
| P90 |5972.69m|6363.04m|
| Mean |3096.35m|3295.32m|
| Maximum |6034.92m|6577.66m|
| Sub-km |2|2|

Only 3 of 11 matched positions improved (3 of 12 attempts); common-IID held score changed by -76.33. The gate fails on coverage and geographic metrics. This is not a reliable positioning improvement despite the original-panel gain. See `policy-additional12-audited.json` and the paired plot below.

![Original and additional source-policy errors](policy-paired-errors.png)

## Modeling conclusions behind this iteration

The original ten-model benchmark is preserved in `../2026_09_30_ds11_single10/TABLE.md`. Original independent Student-t had the lowest32-scan median (2759m). Shared scale, frequency contrasts, temporal correlation, q020, directional cones, and shared candidate slope/curvature all had worse medians (3364–3837m), though several changed the tail or sub-km count. Improvements from pooling recordings do not answer the single-recording objective. Free trend terms can absorb the Doppler shape that carries position information.

Satellite association and positioning are coupled: each candidate supplies a position/time-conditioned Doppler curve, a per-track constant CFO is profiled, and candidate likelihoods are mixed. Archived causal TLE selection, visibility, regional candidate construction, alias correction, and time conventions all affect the resulting evidence. A concentrated candidate weight is conditional on those assumptions. It is not a decoded satellite ID, and within-track held points do not independently validate source selection.

The new screens retain the original measurement products, candidate mixtures, search region and optimizer qualification. Four starts include the original same-recording IID endpoint and three generic starts; the best qualified training objective selects the result. No position-error-based endpoint selection is allowed. `PROTOCOL.md` specifies the frozen eight-recording screen and advancement gate. A baseline replay agrees with the saved original fit to micrometres.

Completed rejected families:

- IID Student-t scale50/200Hz and df2/8: all32 attempts qualified. Scale200 and df8 improved6/8 each and increased sub-km counts, but median reductions were below1%; no variant passed the10% screen median gate.
- Zero timing and Gaussian timing priors with SD0.1/0.5seconds: all24 attempts qualified; none improved the screen median.
- Independent robust blocks of1/3/10seconds: all24 attempts qualified; medians3102/3775/3734m, with3/1/2 wins. No advancement.
- Gaussian observations at200/400Hz and source-weighted Gaussian200Hz: each arm qualified7/8 and developed large tails; all failed the screen.
- Receiver-specific repeated-track weighting (`group_sqrt`, `group_equal`): median gains below1%. Balancing across receivers at the satellite/RF level produced the stronger result above.
- Same-recording arithmetic/geometric-median combinations of saved IID/shared/correlated estimates: no screen winner.

Gentler source-weight powers 0.50/0.75 are a separately predeclared exploratory screen. Power 0.50 passed with 8/8 wins and a 2407.22m median; power 0.75 missed the 10% median-reduction gate narrowly (2798.84m). Only power 0.50 advanced to the remaining 24 recordings. All 32 qualify: median 2694.60m versus 2759.38m, P90 6273.92m versus 7708.23m, mean 3485.05m versus 3784.91m, and 26 paired wins. Maximum error rises to 8801.60m. The remaining 24 have 18 wins and a 202.08m median paired gain, but their marginal median rises from 2655.35m to 2694.60m. These are different statistics: an improvement for most matched scans need not lower the middle order statistic. This is a useful mean/tail tradeoff, not replicated median superiority.

The fixed power-0.50 model also failed its separate exploratory evaluation on the now-exposed additional panel: 11/12 model outputs and 11/12 IID outputs, with index 9 retained as unavailable. Among the 11 matched positions, median error is 3152.04m versus 2568.39m IID, P90 6193.19m versus 5972.69m, and only 3 positions improve. Mean error rises to 3187.79m from 3096.35m despite a slightly positive common-IID held change (+6.34). Neither weighting strength should replace IID based on these results. See `source_temper/model-assessment-source_alpha050-additional12.json`. Observation-count weighting was prepared and tested but has not been run.

After the source-policy replication failed, an explicit exploratory extension revisited Student-t scale200 and df8 on the original remaining 24. Their original screen failures remain recorded. Both qualified on all 32 and improved mean/P90/sub-km yield, but both worsened the all-32 median, so neither was selected. On the remaining 24 alone, scale200 improves 14 positions, mean error by 20.92m and P90 by 946.14m, while median rises 446.74m; df8 improves 15 positions, mean by 18.37m and P90 by 469.11m, while median rises 442.76m. The frozen conditional additional-check protocol therefore triggers no new fit. See `robust/WAVE2_RESULTS.md` and its strict `model-assessment-*-original32.json` artifacts.

## Follow-up diagnostics and association control

The single-arm joint-identity screen in `joint_identity/` ties the satellite
identity of high-confidence repeated sources across receivers and RF strata,
while preserving a separate CFO for each track. It qualifies on all eight
screen scans but barely changes their positions: median error is 3107.934m
versus 3108.162m IID, with four wins and a slightly worse P90. The largest
selected-position movement is 5.73m. Candidate weights were already strongly
concentrated at the original endpoints. This rejects this particular
position-conditioned identity coupling as a useful improvement; it does not
authenticate the identities or test grouping directly from waveform evidence.

The [measurement audit](measurement_audit/README.md) finds no timestamp or
canonical-RF convention discrepancy. Its 1,923 conditional MAP tracks have
median training/held absolute residuals of 93.04/101.57Hz, but training RMS
reaches 683.97Hz at P90 and 2642.31Hz at P99. This motivates testing an explicit
whole-track unassociated alternative without simultaneously replacing the
original independent Student-t signal model. That isolated experiment is
declared in `iid_null_full/PROTOCOL.md`; it also requires non-flat geographic
information, so suppressing almost every track cannot pass as a useful fix.
All 24 fits pass both numerical and information checks, but all three null
priors fail geographically: medians are 3433m, 3409m and 3394m versus 3108m
IID, each with only two paired wins and worse P90. See
[the completed screen](iid_null_full/RESULTS.md). No arm advances.

The [exact element-age audit](orbit_age_audit/README.md) joins the actual
newest-per-object bank elements to 1,295 physical source occasions. Element
age has a weak positive relationship with held residual scale (Spearman
0.195 for median absolute residual). The freshest versus oldest age quartiles
have median held absolute residuals of 82.85Hz versus 142.50Hz. This supports
investigating age-dependent model uncertainty, not applying an unmeasured
orbital correction. Conditional identities, satellite cohorts and update
behavior remain confounders.

Earlier RX-difference scale calibration must be read together with its
negative follow-ups: [DS10 weighting](../2026_09_30_ds10_scale_weighting/README.md),
[score diagnosis](../2026_09_30_scale_score_diagnostic/README.md), and
[direct contrast calibration](../2026_09_30_contrast_scale_calibration/README.md).
Variable scales failed to beat receiver-constant controls. Initial scalar
prediction gains are insufficient reason to repeat that geographic recipe.
The DS11 independent-t4 fixed-position follow-up in `rx_relative_scale/`
closes the likelihood-family distinction: training-only paired-RX features
cover 989/1923 tracks, but transferred variable scales lose 560.657 total held
log units to original fixed100, improving only 13/32 scans. Their advantage
over an even worse matched constant control is insufficient to justify fits.

The separately declared `all_observations/` experiment tests the final-estimation
data budget: use all observations within a single scan under original IID,
while retaining the original candidate bank and training-mask visibility rule.
Its control replays the original index0 endpoint within 8.88e-9 fitted units.
That scan contains 3162 available observations, versus 1940 used for historical
training-only estimation. Former held observations become fitting data in
this arm; common held-score outputs are consequently in-sample diagnostics,
not independent predictive evidence. This is a data-budget comparison rather
than a new likelihood or a like-for-like training-only benchmark.
Its [completed eight-scan screen](all_observations/README.md) also fails the
gate: 8/8 qualified, only three wins, median 3048.99m versus 3108.16m,
mean 3499.48m versus 3481.54m, and P90 6344.54m versus 6046.04m.
No additional fits are triggered by this family.

The [same-source CFO audit](same_source_cfo_audit/README.md) finds 76 disjoint
same-receiver, same-RF fragment pairs among the 32 scans. Their native,
alias-wrapped CFO disagreement is 338Hz median and 1273Hz P90; 66/76 pairs
agree more closely than matched different-source controls. Two very large
outliers contradict hard offset sharing. A bounded robust soft-coupling
hypothesis could recover information across disjoint fragments, but requires
its own test. Shared-visit alternatives and cross-receiver pairs should not
be merged on this evidence; cross-receiver disagreement is approximately
10–11kHz median. No positioning improvement follows from this diagnostic alone.

The DS11 source-provenance screen in `source_consistency/diagnostic.json`
finds2221 training probe groups shared across exported tracks, affecting
4487/16016 training rows (28.0%). This establishes shared acquisition evidence,
not duplicate or physically mutually exclusive detections: the later
[probe/candidate census](probe_overlap_semantics/README.md) finds different
candidate IDs in2215 groups and exact candidate reuse in only six groups
(twelve training rows). The training-only deterministic coverage
selector retains 356/489 tracks and 12052/16016 training rows (75.25%), with
70.0–80.8% coverage per scan. The associated source-group sidecar binds every
exported point to its archived candidate provenance. These counts justify
a narrow same-likelihood subset test. Its
[completed assessment](source_consistency/ASSESSMENT.md) rejects this selector:
8/8 fits qualify, but only four improve; median rises to 3514.23m from
3108.16m, mean rises to 3605.88m from 3481.54m, and sub-km yield falls from
one to zero. P90 improves slightly to 5962.70m from 6046.04m. This separates
the established provenance issue from the unsuccessful greedy-deletion remedy.
No remaining-panel fits are launched.

The [completed soft CFO screen](soft_fragment_cfo/screen-strict-assessment.json)
rejects both arms. All 16 fits qualified within 90 seconds. Identity-only
grouping changes the eight-scan median by less than one centimetre; the 1kHz
wrapped-Cauchy coupling worsens it by 4.05m versus IID and wins only two scans.
Against the identity-only control, coupling wins one of eight and worsens
the median by 4.06m. No replication or full-panel run is justified.

The user specifies causal positioning as primary, with offline results
reported separately. Download-completion records now establish pre-capture
availability for all five metadata-selected orbit updates. The
[causal freshness ablation](causal_fresh/README.md) changes only these
orbit states, preserving existing tracks and candidate identities. All five
fits qualify. One scan improves from 8052.49m to 4666.36m, while the other
four change by less than one metre. Over all 32 scans, mean error falls from
3784.91m to 3679.08m and P90 from 7708.23m to 7342.24m; median stays2759.38m.
This is a material exploratory gain on one scan, not a demonstrated reduction
in typical single-scan error. The additional12 panel has no eligible updates;
the later five-scan metadata-selected confirmation produces no material gain.

The [donor-only age-scale screen](orbit_age_audit/AGE_SCALE_RESULTS.md) also
stops before any DS11 position fitting. Exact old-state/frequency replay passes
for9968 donor cases;3983 target cases match the prior verified replay. The
single age parameter fits113.39Hz/day, and the matched constant scale fits
142.32Hz. Both numerical fits qualify. Age-dependent scales beat fixed100Hz
on all three earlier datasets, but lose to the fitted constant on DS8
(-0.000301 nats per held observation), failing the prospectively required
separate-dataset transfer gate. No age-law tuning or DS11 fit follows.

The [source-deletion diagnostic](source_loo/README.md) passes its first numerical
check on original scan indices 0 and 16: all 128 family/source folds have usable
local curvature and stable finite differences. Predicted deletion shifts reach
6.56km, while endpoint convergence residuals account for less than 0.005m.
These are approximate stability measurements, not position errors or gains.
The 16 prospectively selected exact deletion refits all qualify, but only six
meet every approximation tolerance. The approximation is rejected and no
approximate model ranking proceeds. Exact deletion of scan0's most influential
source moves fitted positions by 2.66–3.72km across families; these movements
are not reference-position errors. Ten combined component tests pass. Exact
jobs took 5.3–13.6seconds, providing a measured cost for a potential fully exact
source-holdout follow-up.

The [fully exact runtime pilot](source_loo_exact/README.md) completes all 14
source holdouts for IID and source weighting on scan0. Both robust families
reach the 90-second whole-family cap without a saved result. Only two of four
families are available, so no model is selected and no reference error is
evaluated. This is a measured execution limit, not a scientific rejection of
either missing family. Five component tests pass; the completed folds and
all four terminal receipts are verified. A separate execution revision must
save and bound each individual fit before a wider comparison is feasible.
The [completed per-fit revision](source_loo_exact/atomic/README.md) reuses 32
qualified results and completes 24 missing fits in 6.31–18.64seconds each.
All 56 scan0 folds qualify; the reference-free held-score selector chooses
t4/200 by 1.266647nats over IID. The subsequent
[eight-scan exact screen](source_loo_exact/screen/README.md) stops at index4:
all44 new processes complete, but one t8 source-deletion fit returns an
unsuccessful optimizer status. The frozen complete-comparison rule leaves
one selectable scan, one unselectable scan and six not attempted, retaining
the full eight-scan denominator. No geographic evaluation or model promotion
follows. This numerical qualification failure does not establish that the
underlying source-holdout selection hypothesis is geographically worse.
The separate [same-solver restart diagnostic](source_loo_exact/restart/README.md)
also fails: one fresh L-BFGS-B invocation returns the identical endpoint and
unsuccessful status after19 evaluations. Seven eligibility tests pass. No
reference error is used and no additional same-solver retry is planned.
A subsequent [local precision diagnostic](source_loo_exact/precision/README.md)
finds stable positive-definite curvature and a predicted correction of only
0.47mm. A separately gated [SLSQP continuation](source_loo_exact/recovery/README.md)
then qualifies at effectively the same endpoint. This recovers optimizer
termination status, not position accuracy; the original failed screen remains
preserved. The separately frozen [uniform screen revision](source_loo_exact/screen_recovery/README.md)
completes all448 folds:108 verified caches and340 new qualified fits. Its
source-holdout selector lowers the eight-scan median3108.162m→2649.740m
(14.75%) and mean3481.538m→2912.321m, but improves only3/8 positions and
worsens P906046.037m→6088.620m. The predeclared advancement rule fails;
no wider confirmation or promotion follows. Five new fits use the uniform
small-gradient/stable-curvature SLSQP recovery within the90-second fit cap.
That recovery repairs numerical termination, not positioning accuracy.

The [DS11 full-catalogue IID pilot](catalogue_iid_audit/README.md) closes a scope
gap in the earlier shortlist evidence, which used DS7–9 contrast likelihoods.
All12 new training-only settings (six tracks, two settings each) retain the
full-catalogue leading candidate. The largest omitted likelihood fraction is
approximately2.72e-58, with exact retained-bank prediction and visibility
replay. This rules out meaningful missing mass in these tested cases only;
it is not an all-track or continuous-region completeness claim.

## Next scientific priorities

1. Establish which GLRT detections are alternatives and which can coexist before modeling exclusivity. DS11 probe overlap is verified, but different candidate IDs account for2215/2221 shared training groups; only six groups reuse the exact detection. The greedy one-track-per-probe selector has failed geographically. A future alternative-hypothesis model must account for every observed probe, including detections not explained by a selected track; summing likelihoods over unequal observation sets is not a normalized comparison. Physical-NORAD balancing does not resolve that distinction. Joint waveform evidence for coexistence versus competing detections is needed before imposing an exclusivity constraint.
2. The disjoint-fragment CFO hypothesis and exact source-holdout family selector have failed their controlled screens. Use measured source-deletion sensitivity to prioritize measurement and model audits; do not assume predictive-score improvements rank geographic accuracy. Held points within an already selected track share orbit and extraction errors with training points. Report position-mode changes and weak geometry rather than hiding them behind one selected point.
3. On the existing IQ corpus, test whether known-pilot or coherent phase-derived Doppler improves the actual shape information of the same tracks. Better CFO precision alone will not fix orbit/timing/model bias. Keep the same single-recording comparison and frozen reference-independent endpoint selection. The [completed scan-0 waveform audit](norad65512_waveform/RESULTS.md) extracts and measures all111 training observations of the two influential tracks conditionally assigned to NORAD65512. The long fit improves held-symbol prediction on72/111 excerpts and on average for both tracks; the short fit improves24/111 and worsens prediction overall. Neither hits a search boundary. The subsequent [matched position ablation](norad65512_position/README.md) retains both arms: long improves reference error by13.810m; short worsens it by8.737m. All65 target localization-held values remain unchanged. The small gain has not been replicated, and conditional residual RMS remains115–137Hz on these tracks. Earlier direct waveform corrections covered DS7–9, so they did not settle this DS11 measurement question.
4. Treat source-dependent orbit errors, receiver timing/drift and RF alias uncertainty as distinct hypotheses with constrained, identifiable models. Unrestricted slope/curvature terms can remove position information; the failed timing-prior and block-correlation screens argue against adding nuisance freedom without a measured residual pattern.

Broader improvements from these follow-ups remain unproven; the completed bounded results are reported above. Obtaining a surveyed reference and confirming installation continuity would improve interpretation of absolute accuracy, but must not be substituted for improving measurement-derived estimates.

For the new waveform lead, the next bounded step is a matched replication on
another scan/source selected from training-only influence evidence, retaining
both pilot arms and all attempted observations. The current13.810m reference
gain is too narrow to justify a corpus-wide reprocessing campaign or promotion.

Before executing that replication, the [nominal temporal-support audit](norad65512_position/support_audit.json)
finds a typical4.279ms mismatch between the eight-frame long pilot and retained
GLRT timestamps. Its conditional geometric frequency effect is predominantly
a track constant: median13.15–13.31Hz and median-centered RMS0.71–0.80Hz,
compared with measured correction RMS22.95–33.25Hz. No position effect has
been tested, and actual estimator weights remain unmeasured. A prospective
support-aware comparison takes priority over repeating the mismatch. The
training-influence rule has already selected scan16/NORAD67103, comprising
124 training observations; its waveform replication remains unexecuted.
Causal orbit availability remains the primary evaluation rule. Any later-orbit
offline experiment must be separately labeled and cannot enter causal scores.

The subsequent [nominal support-aware position comparison](waveform_support_position/README.md)
completes all eight fits with qualification. Long-pilot error is745.342m,
19.730m below original IID and5.921m below its unchanged-timestamp result;
short-pilot error is767.233m, still2.160m worse than IID. All62 conditional
MAP satellite assignments remain unchanged. Real-data verification matches
every corrected candidate prediction to independent scalar interpolation
exactly, and five component tests pass. This resolves the nominal timing
sensitivity on scan0, not actual estimator weighting or cross-scan validity.
The fixed [scan16/source67103 waveform replication](waveform_replication16/RESULTS.md)
now completes all124 measurements. Long improves held-symbol prediction on84/124
excerpts with no frequency-search boundaries; short improves27/124 and hits
its+1500Hz boundary twice, on both receivers at visit1308. The predeclared
two-arm boundary-free gate therefore fails before a position plan is frozen:
zero position fits and no geographic evaluation. This is unavailable
replication evidence, not a demonstrated position loss or win. The boundary
excerpts and several large long corrections have held-symbol prediction NMSE
near1, motivating a training-symbol-only audit of frequency reliability before
another positioning experiment. No observations are dropped or gates relaxed
inside the original replication. Causal positioning remains primary.

The [training-symbol reliability audit](pilot_reliability16_revision/README.md)
then completes all124 excerpts and exactly replays both original estimates.
Median alternating-frame-group disagreement is18.10Hz for long versus83.26Hz
for short. At the two suspect visit1308 excerpts, long disagreements are
1918.19Hz and1185.18Hz despite interior full-fit frequencies, with coherent
energy fractions0.00655 and0.00568 versus median0.08604. This rejects search-
interior status as sufficient evidence of reliability. No reliability threshold
or position model is selected in the audit. Next, prospectively test a
fitting-evidence-based pilot/GLRT fallback on both scan0 and scan16, preserving
all rows and explicit measurement timing. That would be a new estimator
experiment; the original replication gate and unavailable outcome stand.

The prospective [pilot/GLRT fallback experiment](pilot_fallback_results.md)
now completes both scans and all16 qualified fits. A fixed100-canonical-Hz
alternating-group agreement rule accepts111/111 long corrections on scan0 and
119/124 on scan16, retaining original GLRT values/times otherwise. Long errors
are745.342m versus765.072m control on scan0, but2171.384m versus2153.140m on
scan16. Short errors are804.019m and2135.687m respectively. Neither arm improves
both scans; the predeclared advancement gate fails. Both scans' training-score
selections are sealed before geography, all conditional MAP identities remain
unchanged, and scalar interpolation/fallback preservation checks pass alongside
28 component tests. No threshold retuning, wider confirmation or promotion
follows this failure. Focus next on separating source-common residual patterns
from receiver-specific errors and competing GLRT interpretations.

The [conditional-source paired-residual audit](source_residual_pairs/README.md)
now finds strong shared structure in12 scan0 cross-band pairs and42 simultaneous
scan16 cross-RX pairs. Long-pilot corrections reduce centered pair-difference
RMS50.28→37.73Hz and133.83→88.45Hz, respectively, while common-component RMS
remains135.01→135.47Hz and256.56→245.77Hz. Rank correlations support the pattern.
This reconciles better pair agreement with inconsistent position improvements;
it does not identify orbit error or authorize subtracting common residuals,
which include position information. Earlier DS7–9 slope/curvature transfer and
differential-drift experiments already warn against that inference. Return to
the unresolved normalized treatment of competing GLRT interpretations before
another free-drift or residual-subtraction positioning model.

The [common-sample pilot coexistence test](probe_coexistence/README.md) now
compares six metadata-selected shared probes. Four joint two-candidate models
beat both single-candidate models and both code-rolled controls on identical
held IQ samples; two do not beat the best single. All three fixed real controls
favor their expected pilot sequence. Three synthetic tests and independent
QR replay pass; all nine cases complete in3.21seconds. This supports additive
pilot contributions in some shared probes and argues against hard one-candidate-
per-probe selection. It does not prove independent satellites or validate
NORAD assignments. The next bounded measurement test is joint versus separate
frequency estimation on common samples, retaining all cases before any
positioning propagation. No position gain follows from this diagnostic alone.

The [single-frame joint-frequency comparison](probe_joint_frequency/README.md)
completes all six probes with12 qualified joint starts. Joint refinement beats
separate refinement on5/6, median NMSE gain+0.000561, passing its narrow
measurement-stage gate. Against cached acquisition frequencies, however, it
wins only2/6 and worsens both mean and median; mean gain versus separate is
also negative. The incumbent comparison prevents treating that gate as a
positioning improvement. No frequencies are propagated into positioning.
Next test the same six probes with eight-frame pooling and independent
frame/carrier gains, requiring improvement against cached as well as separate
predictions before further advancement.

The [eight-frame follow-up](probe_joint_eight/README.md) completes all six
comparisons and12 qualified joint starts. Joint refinement beats cached on5/6
with mean NMSE gain+0.000773, but beats separate on only2/6 and has negative
mean/median gain against separate. Separate refinement itself beats cached on
5/6 with mean gain+0.000949. The joint arm fails its stronger gate; no position
propagation or broader joint-refinement campaign follows. Independent QR
replay verifies all144 frame scores and18 pooled scores.

A separate [bank position/velocity consistency check](state_velocity_audit/README.md)
finds maximum vector discrepancies below0.018m/s on scans0 and16 at zero and
near-fit timing grid points, bounding the corresponding Doppler difference
below0.643Hz. This internal discrepancy does not explain hundred-Hz residuals;
it does not validate absolute ephemerides, frame orientation or identities.

Published accuracy figures also need matched assumptions. Section8.1 of
[Unveiling Starlink for PNT](https://people.engineering.osu.edu/media/document/2025-08-06/kassas_unveiling_starlink_for_pnt.pdf)
corrects TLE/SGP4 temporal and orbital errors using knowledge of the receiver's
position before treating ephemerides as truth. Its positioning results therefore
do not establish the accuracy attainable from DS11's uncalibrated causal orbit
inputs. This is a comparison limit, not evidence that DS11 has reached an orbit
error floor or that waveform improvements cannot help.

The [causal orbit-revision shape diagnostic](orbit_direction_audit/README.md)
uses only earlier-dataset training statistics. Revision directions have median
linear energy fractions of0.931–0.962, but revision size correlates weakly with
residual scale (Spearman0.077–0.093). This offers little support for using
revision magnitude alone as an uncertainty weight. It neither calibrates orbit
covariance nor rules out a more structured source-shared uncertainty model.
No additional position fits or orbit replacements were made.

A [cross-source receiver-offset support audit](cross_source_rx_offset/README.md)
finds no target with three independent conditional donor identities sharing
enough same-RF visits:453 of503 eligible pairs have no donor and50 have one.
The proposed simultaneous donor test is therefore unsupported, without changing
its threshold. Descriptively, all16 eligible scan16 pairs have native cross-RX
offsets near-20kHz, including the influential NORAD67103 pair. Its large offset
alone does not distinguish a bad association from a receiver-path effect.
No new position fit or hardware oscillator calibration follows.

The [cross-band leave-NORAD drift screen](cross_band_rx_drift/README.md) has
enough donors for130 receiver pairs and improves held receiver-difference
prediction on7/8 scans. Mean scan gain is2.55 native Hz and median gain0.27Hz;
79/130 pairs improve. The narrow measurement gate passes, but the typical gain
is small and common receiver drift remains unidentified. The
[unchanged remaining-24 confirmation](cross_band_rx_drift_confirmation/README.md)
also passes:16/24 positive scans, mean gain2.86Hz and median0.60Hz. Independent
scalar replay reproduces donor fits and all10,140 held errors across both
panels exactly. This supports a fixed-position receiver-allocation ablation,
with repeated-track conflicts left unchanged. It does not supersede the earlier
negative differential-drift position results or demonstrate geographic gains.

The [fixed-position receiver-allocation comparison](cross_band_rx_fixed/README.md)
finds RX1 unchanged/correct RX0 improves held prediction on6/8 scans, total
gain152.20nats and median4.32nats. Symmetric and RX0-fixed allocations worsen
aggregate held prediction and fail their gates. Original training scores replay
exactly, all conditional MAP identities stay unchanged, and scalar replay
verifies15,462 corrections exactly. This supports a bounded geographic
comparison retaining all allocations; it does not identify the physical common
drift or establish lower position error.

The [cross-band drift geographic screen](cross_band_rx_position/README.md)
completes96 starts (95 qualified) and all24 scan/allocation outputs. The
predeclared RX1-fixed primary lowers median error3108.16→2836.48m (8.74%) with
5/8 wins, missing the10% and6/8 advancement requirements. Its P90 is slightly
worse. Symmetric and RX0-fixed medians worsen. All training selections were
sealed before geographic scoring; no allocation is promoted and this version
does not advance to additional scans. Multiple qualified basins on scans16/20
also limit claims of optimizer uniqueness.

The [drift-derived basin recovery check](drift_basin_recovery/README.md) returns
28 deduplicated corrected-model endpoints to the original uncorrected IID
objective.27 qualify; none improves training score beyond1e-6nats. All eight
original endpoints and errors remain unchanged. This particular initializer
path is exhausted without altering the failed drift policy or claiming global
optimality of the original fits.

A distinct [independent-error CFO integration feasibility audit](offset_integral_audit/README.md)
passes numerical checks on24 fixed training-MAP cases in3.07seconds. It
integrates the baseline's per-track CFO under its Gaussian prior while keeping
independent Student-t errors. Earlier shared-scale and contrast experiments
do not directly test this likelihood. Between-track correction differences
include track-length constants, so within-track candidate/position sensitivity
must be established before geographic optimization. No accuracy gain is claimed.

The [within-track CFO-integral sensitivity audit](offset_integral_sensitivity/README.md)
passes24 scalar/vector and derivative checks. Candidate-pair gaps change by
at most1.80nats with no leading/runner-up reversals; +/-100m perturbations change
the profile-to-integral correction by at most0.0154nats per sampled track.
The correction is position-dependent but small in this sample. Full-candidate
cost and numerical convergence remain prerequisites to a bounded fit.

The [full-candidate CFO quadrature benchmark](offset_quadrature/README.md)
passes across all1,426 retained candidates on scans0 and16.32/64-node values
agree within2.28e-13nats and gradients within3.11e-11;24 adaptive-oracle cases
also agree. Order32 integration costs about0.8seconds per scan at these points,
making a bounded full-mixture fit feasible without candidate pruning. Numerical
checks must still cover fitted endpoints; no geographic gain follows yet.

The [full-mixture marginalized-CFO position pilot](offset_position/README.md)
completes all eight starts with qualification and endpoint quadrature checks.
Scan0 improves765.072→762.928m; scan16 worsens2153.140→2167.100m. The frozen
both-scan improvement gate fails, so this version does not advance. Profiling
versus marginalizing the constant CFO has a small mixed effect on these two
recordings; no general accuracy improvement or error floor is established.

A [local shared-drift information audit](shared_drift_information/README.md)
finds free per-source slopes retain median horizontal information fractions
0.275/0.559, versus0.751/0.993 for per-receiver slopes. This conditional design
calculation quantifies why unrestricted source-error correction can remove
position information. It is not covariance calibration, an accuracy estimate,
or a rejection of finite independently calibrated source-error priors.

A [symmetric orbit-revision uncertainty transfer test](orbit_uncertainty_transfer/README.md)
learns a finite zero-mean coefficient prior fromDS7/DS8 training data, then
passesDS9 held-prediction gates:275/336 changed sources beat zero correction
and213/336 beat a matched linear-direction mixture. Independent expanded-state
replay agrees within1.37e-12nats. This supplies new evidence for revision shape
as an uncertainty direction, distinct from the failed shared mean correction.
It remains a historical conditional residual test, not calibrated ephemeris
covariance or a DS11 position improvement; source dependence and association/CFO
uncertainty must be retained in any geographic extension.

The [DS11 causal revision-support inventory](ds11_revision_support/README.md)
finds older records for all102/92 physical candidates on scans0/16, with
changed element bytes in every case. Existing joint-identity groups and all
singleton tracks remain accounted for. Exact archive occurrences are now bound
by provider, collection time and digest, avoiding ambiguity from repeated
identical snapshots. Five archive occurrences and194 candidate occasions
verify through read-only ports. State propagation and a matched zero-revision
joint-identity control are still required before a position experiment.

The [causal revision-state export](ds11_revision_states/README.md) now covers
all120 pilot tracks and1,426 candidate-track occasions. Original position and
velocity arrays replay exactly. Separate older banks preserve all slots/time
grids; independent serialized coverage and boundary spot propagation checks
pass. This enables position-dependent uncertainty directions, with no change
to the original baseline banks and no geographic accuracy claim yet.

The [joint candidate/revision model](joint_orbit_uncertainty/README.md) passes
zero-revision parity and finite-difference gradient checks on scans 0 and 16.
The [held-prediction bridge](joint_orbit_prediction/README.md) also passes:
orbit beats zero by 320.703/208.822 nats and matched linear uncertainty by
146.643/26.276 nats. Priors learned from DS7/DS8 remain frozen; original and
older orbit data are causal. Shared physical identity and revision coefficients
are marginalized jointly, conditional on per-track profiled CFOs. This warrants
a bounded geographic pilot, not an accuracy claim.

The subsequent [causal orbit position pilot](joint_orbit_position/README.md)
fails its advancement gate despite all 12 starts passing numerical qualification.
Orbit errors increase from 765.072 to 1512.799m on scan 0 and from 2153.140 to
2337.572m on scan 16. Zero-revision controls reproduce baseline accuracy;
matched linear uncertainty yields 3204.420/4466.518m. Training-selected endpoints
were sealed before reference scoring, and source/receipt/selection/geographic
verification passes. Improved held Doppler prediction did not translate into
improved positioning. No broader geographic expansion or prior tuning follows
from this failed pilot; the causal baseline remains primary.

An [original-objective basin recovery](orbit_basin_recovery/README.md) tests
all ten unique qualified zero/orbit/linear endpoints as original-IID initializers.
Ten processes complete, nine fits qualify, and none improve the original
training score enough to replace either baseline endpoint. Errors remain
765.072/2153.140m. This closes the particular alternative-seed route without
claiming global optimality; source/receipt/selection verification passes.

The [classical signal travel-time audit](light_time_audit/README.md) finds
roughly 6.4Hz absolute Doppler corrections, but at most 0.0124Hz of
training-mean-centered shape across all retained candidates on scans 0 and 16.
Per-track CFO profiling absorbs almost all the constant component. Synthetic
radial and rotating-frame derivative checks pass; source hashes verify. This
deprioritizes geometric retardation as a large residual explanation without
claiming a geographic error bound or complete relativistic validation. No new
position campaign is launched for this effect.

The [unknown-height sensitivity audit](height_sensitivity/README.md) identifies
a potentially material physical assumption: baseline receiver height is zero,
while station metadata leaves altitude/datum unknown. A hypothetical 100m
height perturbation aliases locally into 324–349m horizontal displacement on
scan 0 and 34–42m on scan 16. These conditional design projections are not
actual altitude estimates, calibrated covariance or accuracy gains. Zero-height
parity, derivative step checks, tests and source hashes pass. Independent
antenna altitude is needed before selecting a physical fixed-height correction.

The [single-scan free-height pilot](free_height/README.md) completes four
qualified fits with all original candidate mixtures retained. Heights converge
to +553m on scan 0 and -490m on scan 16; held gains are +27.47/+8.96 nats.
Despite that predictive improvement, horizontal errors change from
765.072/2153.140m to 2801.210/1821.649m, failing the both-scan geographic gate.
No reference-driven height tuning follows. The roughly 1km disagreement in
height also prevents treating these results as measured antenna altitude.

The [holdout-support audit](holdout_support_audit/README.md) verifies all 32
exports and whole-visit partition consistency. All 41,789 held measurement rows
share tracks with training, 93.594% lie within their training-time span, and
median nearest-training separation is 0.401s. This quantifies why conditional
held Doppler improvement can coexist with geographic worsening; it does not
measure error correlation or establish a coding leak. The earlier failed
448-fold source-holdout selector also remains negative evidence. New physical
corrections need independent identification evidence, not interpolation gains
alone, before broader geographic expansion.

The [capture-bound pose audit](pose_evidence_audit/README.md) validates all 32
original companions, including content/authority digests, manifest binding and
validity intervals. They repeat one authority, with no measured altitude/datum,
RF phase-center baseline or receiver elevation; receiver mappings remain
provisional. Thus the missing calibration is not merely omitted from the current
repository configuration. These records cannot supply a defensible fixed-height
or interferometric correction, and do not independently verify installation
continuity or surveyed horizontal truth.

The previously prepared [count-sqrt weighting screen](source_count/README.md)
now completes all eight scans with 32/32 qualified starts. Median error rises
3108.162→3492.574m and P90 rises 6046.037→6153.003m, with only two paired wins.
Scan 16 improves to 327.813m, but that isolated gain does not justify a
scan-specific policy. The frozen screen gate fails; no stronger count weighting
or additional-panel run follows. Sources, receipts and training selections are
verified and sealed before geographic scoring.

## Joint receiver association and geometry

Following the user's confirmation of RX0-west/RX1-east with nominal outward
tilts, the [joint receiver association experiments](joint_receiver_association/README.md)
implement exact soft RX matching, unique raw-detection ownership alternatives,
physical satellite mixtures, compatible prior-DS10 receiver calibration, and
joint position fitting. Causal orbit banks remain unchanged. Calibration supports
only six of the original 32 scans and one of the additional twelve at the exact
5MS/s/RF settings; other settings are explicitly excluded.

Independent receiver-state geometry improves five of six development positions,
median 2401→1601m against joint Doppler, but fails separate-record confirmation
(5973→6136m). A donor-calibrated time-correlated model then improves only three
of seven positions, median 2650→2628m, and still regresses on the additional
record (5973→5993m). Both final accuracy gates fail; neither replaces the baseline.
All 25 component tests pass, including exact enumeration, normalization, temporal
filter derivatives, held-CFO isolation and complete objective parity. Across the
two experiments 63 bounded fits execute, 60 qualify, and all failures remain
reported. See the [comparison figure](joint_receiver_association/sequence-comparison.png).

Receiver-state prediction transfers better than position accuracy. Calibration
also merges multi-track physical-source hypotheses that the position graph can
only pair one-to-one across receivers. Whole-source fragment assignment and
explicit absence/clutter modeling remain unresolved, before adding further
orbit corrections. The accuracy goal remains active, not falsely completed by
successful software tests or attractive development examples.

The subsequent exact whole-source experiment now sums all satellite assignments
and permits multiple fragments per receiver, with no candidate pruning. It also
fails its three-record gate: the additional error remains 5973→6136m, and two
cells fail optimizer qualification. An equivalent structural DP acceleration
reduces evaluation time by roughly 3–5x and completes the preserved scan-0
timeout under the same 90s cap. There are now 34 unique component tests.

A calibration-provenance audit found that one contributor to the old pooled
DS10 geometry finalized after the earliest DS11 target, although its RF capture
was earlier. Consequently the preceding receiver results demonstrate causal
orbit use, not fully online calibration availability. A new qualified N23 fit
excludes that dependency and uses only earlier available seeds/data. The full
acquisition inventory spans eight rate/RF settings; receiver calibration must
now be rebuilt on the corrected geometry across those settings, with the
absence/clutter/activity model still unresolved. The baseline remains retained.

That receiver rebuild is now complete for the 23 available numerical donors.
All six acquisition settings with distinct validation donors pass signed RX
geometry versus all receiver/elevation/swap/permutation controls, with 292/379
source-group wins. All 24 selected calibration fits qualify and 39 unique
component tests pass. Both 2.5 MS/s settings remain unvalidated; further earlier
recordings exist but still need RF/track eligibility checks. The new calibration
has not demonstrated lower DS11 position error. See the
[acquisition-specific results](joint_receiver_association/acquisition_calibration/summary.json).

Two subsequent eleven-record pilots fail across those six settings. The fully
joint model raises original median error 2291.6→2472.1m and additional median
2568.4→2577.2m, with 3/11 wins and 11/22 qualified fits. Freezing receiver
geometry at the original IID estimate for association alone raises original
median to 2517.8m and leaves additional median essentially unchanged at 2567.4m;
it also has 3/11 wins, with 21/22 qualified fits. Both worsen P90 in both cohorts.
All 44 processes finish under the caps; failures are retained without selective
retries. Direct receiver angular gradients are therefore not the sole explanation.
The next diagnosis is candidate posterior changes and ambiguity, not promoting
these models. See [joint pilot](joint_receiver_association/acquisition_position/summary.json)
and [association-only pilot](joint_receiver_association/association_only/summary.json).

The [exact posterior diagnosis](joint_receiver_association/posterior_diagnostic/summary.json)
finds that both receiver variants remove majority probability from 40 original
identities among 668 tracks, including 24 originally at ≥.99 Doppler probability.
These are inferred changes, not verified corrections. A subsequent
[earlier-data persistence screen](joint_receiver_association/temporal_acquisition/summary.json)
fits 4.95–11.12s correlation times and greatly reduces the apparent signed-geometry
held-score advantage. Four acquisition families pass and two fail the temporal
geometry gate. This motivates time-correlated whole-source inference with
calibration-gated fallback, not dropping failed settings from position evaluation.

The resulting [whole-source temporal policy](joint_receiver_association/temporal_whole/summary.json)
finishes with all 22 fits qualified but fails accuracy: original median
2291.6→2351.8m, additional median2568.4→2585.0m, and worse P90 in both cohorts.
Additional index3 improves613→227m, an isolated gain rather than a passed result.
Fallback records stay in the denominator and exactly reproduce Doppler controls.
Posterior majority-loss counts fall40→19 overall, but only23→18 on active
temporal records; the rest is due to fallback. The baseline remains retained.

The subsequent [geometry likelihood-ratio pilot](joint_receiver_association/geometry_ratio/summary.json)
also completes all22 fits with qualification but fails accuracy: original median
2291.6→2291.8m and additional2568.4→2570.5m, with slightly worse P90s.
Subtracting receiver-only source likelihood removes all ten previously observed
high-confidence identity changes, but does not establish lower position error.
The remaining seven majority-probability changes involve less confident original
identities; none are verified satellite corrections. Detection/clutter and
source-strength selection modeling remain unresolved, and the baseline stays.

## Verification and limits

Inputs, candidate banks, plans, identities, source bytes, every optimizer start, terminal receipts, failures and execution times are retained. Each fit has a90second process cap, each additional export a180second cap, and numerical work uses at most three single-thread workers. Component tests cover normalized profiles, derivative agreement, training/held independence, source identity binding, weighting, numerical gates, and fallback selection. The initial robust implementation's interrupted engineering attempt and pre-vectorization source are preserved separately.

The configured center already lies about809m from the reference. Shrinkage toward that center would therefore look attractive without demonstrating measurement-derived positioning; it is not used. Reference uncertainty, unconfirmed installation continuity, conditional candidate banks, and exposure of the original benchmark constrain all accuracy claims. The twelve additional recordings share the same site and are interleaved in time; they are not an independent deployment validation.
