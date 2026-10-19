# DS23 position improvement: active research checkpoint

The user goal is mean **and** median error at or below0.5km, without GPS-selected
locations/identities/priors or post-scan TLEs. This goal is **not achieved**.
Continue debugging and prototyping; do not mark the active goal complete.

ALGO01 and DBG01 are published on remote main. Commits e28345ebe and5b9ca757a
publish the specification/debug evidence and the first full weighting benchmark.
The main working branch has extensive unrelated work; publication uses the clean,
sparse checkout `/home/mouse9911/gits/.algo01-publish`. Avoid creating a full
checkout in `/tmp`: the repository has about91,000 files. An attempted new
checkout was canceled/automatically removed; unrelated work was preserved.

## Current independent-scan results

These are the original sealed **20-scan** DS23 sample, not all413 recordings.
Scans217 and45 are development data. Original benchmark outputs are unchanged.

| Fixed rule | c0 mean / median km | Fitted-c mean / median km |
|---|---:|---:|
| ALGO01 |1.771 /1.924 |1.747 /1.913 |
| RX support + paired gates |1.612 /1.325 |1.607 /1.305 |
| RX support + fragment sigma300Hz |1.452 /1.225 |1.427 /1.030 |
| RX support + phase floor3s |1.793 /1.428 |1.782 /1.416 |
| RX support + smooth sigma50Hz |1.884 /1.662 |1.898 /1.664 |
| RX support + all three |1.646 /1.250 |1.617 /1.271 |

All final paired gates pass. The combination reaches0.493/0.415km on217 but
worsens45 to0.841/1.098km. RF-only selection on a common681-point mask chooses
fragment300 on217 at2.846/2.764km, not the geographically best combination.
On45 it chooses the combination. Do not choose priors per scan using GPS error.

RX-support powers are1 for families with curved observations on both RXs,
0.6 for other families with at least two RX/channel owners and conditional
candidate uniqueness≥0.95, and0.2 otherwise. Only retained observations create
confidence/owner votes. The first interrupted counting trial is preserved
separately and is not mixed into the benchmark. Original nuisance support is
retained under masking for controlled comparisons. No linear tracks calibrate.

## Completed scan217 evidence

- All14 family/26 track deletions do not fix the original4.315/4.191km error.
- Confidence-gap weighting alone barely helps; removing the one ambiguous
  RX1 CH1 T002 fragment worsens position.
-52 single identity replacements,43 mixed pair/triple/whole-family proposals,
  and35 two/three-whole-family replacements do not beat incumbent RF loss.
- Same-RX/different-family nearby residual correlation median+0.54, versus
  same-family/different-RX−0.06; small overlapping pair sets are descriptive.
- Shared fast receiver covariance reduces RMS163.5→136.7Hz but not position.
- Two secondary-peak-assisted curved tracks add38 unique probes (29 winning,
  nine secondary) and worsen position jointly and individually. Full final
  gates pass. Adding more associations is not sufficient.
- Frame epochs reproduce an old unresolved negative-range relation. They have
  positive arrival semantics; do not globally negate them into pseudoranges.
  Prior audit: `reports/2026_10_17_dsx01_iteration6/frame_phase_audit/README.md`.
- Shared satellite clock covariance alone worsens217 to4.412/4.315km.

## Latest work / next useful continuation

### 2026-10-19 uncertainty study: completed progress

Previous goal turn was progress: publishedthrough7739f1194 with20-scan
receiver/band/family residual transfer. This turn completed three new20-case
studies and two UTC probes; no goal completion. Mainreport:
`reports/2026_10_19_ds23_uncertainty_study/README.md`.

Band covariance variance-matchedrho1/.5/0: all20pairedgatespass.
rho.5 c0mean/median1.350/.959,fitted1.280/.828;rho0 1.450/.991,
fitted1.338/.852; scalarcontrol1.315/.991 and1.266/.896.
Low-only cases are numerical nullcontrols; no newdefault selected.

Satellite-specific scale usesa variance-one population log-scale mixture,
moment-matched posterior variance, pre-RF chronologicalqualification only.
4/20qualify, c0mean/median1.309/.989,fitted1.261/.896,allgatespass.
Its gain is tiny. Source `learn_ds23_satellite_phase_scale.py`,
`probe_ds23_satellite_phase_scale.py`, `run_ds23_satellite_phase_scale.py`.
Rawoutputs `reports/2026_10_19_ds23_satellite_phase_scale/`; newhistory
receiptsin`...ds23_causal_phase_mean/history/*_satellite_scale.json`.

Local Schur-information studyall20cases: medianlocalRMSradiusc0
all-uncertain1.029km,receiver-known.704,phase-known.221,
orbits-known.183,fragment-known.765,all-known.012. These are conditional
generalized widths with Gamma precisions fixed, not calibrated intervals or
new localizationresults. UTCuncertaintyexcluded, so widths optimistic.
All40 informationmatrices positive; derivative.01/.02kmrelativechange<6.1e-10.
Source `diagnose_ds23_position_information.py`; outputs
`reports/2026_10_19_ds23_position_information/`.

RecordedUTCuncertaintywasomittedfrompositionfit. Preparedmetadatahas
`utc_half_width_s` forbothformats: adaptive~.183s,fast~.125s.
`probe_ds23_utc_bracket.py` shiftsgeometryquerytimesonly, notelapsedhardware
times, keepsoriginalearliestTLEcutoff andlabels/masks. Fiveclocknodes
in[-half,+half], no trimminginsidegrid, pairedc fits. Both257/202 RFselect
earlybound. 2573.722/3.699→2.877/2.859butRFgainonly.104c0
(weaklyidentified);2023.061/3.060→2.943/2.942. Clock0replayexact.
No clockdefaultadopted; notafullcohortrun.

Rao-Blackwell importanceaudit257sameprior/data atincumbent/challengerRF
endpoints: 1024then4096draws, no positionrefit, c0-onlyobjectiveaudit.
4096 estimates−2logevidence5120.115/5135.449, nominalMCSE.015/.014,
ESS3340/3426. ELBO5122.631/5137.900;gaps2.517/2.451.
Challengerstillloses15.334vsELBOgap15.268. Mean-fieldapproximationdoes
notexplainthisdecisionwithin thisaudit. Rawreceipts
`reports/2026_10_19_ds23_marginal_evidence/`, includingpreservedn1024.

Tests19passed: bandcov8,information3,satellitescale4,UTC2,evidence2.
No runtimecomponentchanges,newRF,IQreread orQNAPmutation. ALGO01research
statusandDBG01timing/informationaddendumupdatedforpublication.

Extra read-onlyarchiveinventory: latest3pre-scan257snapshotscontain0
regionalfuture-referenceepochs; `/tmp/ds23-prepublished-epoch-inventory.json`.
Donotrelaxepoch/collectioncausalrules. Fastmetadatahasdeliveryclocks per
visit whileRFprobesomit skippedvisits; alignbyexplicitvisit_index, notarray
length. Quickunpublishedtiminginventoryon11fastcases: lower-envelope
device/hostratesabout−.6..+.25ppm,minimumdeliveryupperanchorabout+70ms
frommidpoint. Unknowntransportlatency prevents treatingthisasactualUTC.
No timing-calibrationprior wasadoptedfrom thatinventory.

Use structuredJSON reads ofselectedscalarfields: fasttrackingJSONisone
huge line and containsnestedsource/probes. Do nothead/printwholemetadata.

Next meaningful tests: variance-matched shared frequency constants for
same-satellite/same-RF fragments (physicallycommontransmitter clock), and
causal full-state signed orbitforecasts, notonlyphase. Currentphysicalmode
means arezero; old/new projectedradiuscoefficientsaremostly−1on217,
suggesting a signedforecast hypothesis toqualify using pre-RFTLEtriples.
Avoid more arbitrary GPS-selected prior sweeps. Untouched-scan validation
andfullDS23scope remainoutstanding; goal staysactive.

### Latest completed refinements and failure controls

Published complete follow-up reports/raw receipts/source snapshots inremote
main b9faf9768. The20-scan learned residual audit also completed:
`reports/2026_10_18_ds23_learned_residuals/`, replayloss exact,3new matching
tests pass. High-band evidence occurs in11 short_window_iq_recording scans;
the9 adaptive scans are low-band-only inthis cohort (do not reverse these).
Atc0 pooled residual correlations: sameRX/sameband/differentfamily+.459
(593trackpairs/20scans),sameRX/differentband/differentfamily+.329
(444/11),differentRX/sameband/samefamily−.020(124/19).
Medianofscanmedians+.449,+.304,−.039 respectively. Pairsoverlap and are
conditionedonjointfit: descriptive, notcausal identification orindependent
significance tests. RX1low/highmedianRMS119.4/147.9Hz;RX279.7/108.6Hz.
Possible next controlled prototype: variance-matched receiver smooth
covariance split into common and independent per-band terms; current
smooth basis is shared across bands. Keep linear drift and marginal
per-band variance unchanged, and use low-only cases as exact null controls.

The causal scalar-history cohort and inputs/source snapshots are published to
remote main in1bf3a7853771b5044d2dc3de8513d485167710ab. ALGO01 and DBG01
were already pushed; no new production default has been promoted.

Both subsequent20-scan cohorts completed. Summary:
`reports/2026_10_18_ds23_prior_refinements/README.md`.
All final paired gates pass; scalar replay is exact. Variance law qualifies
on historical TLE prediction for18/20, but selected policy worsens mean/median
to1.420/1.109 c0 and1.380/1.038 fitted-c. Unit powers under scalar prior:
1.443/1.354 and1.365/1.223; confidence-only powers1.560/1.354 and1.500/1.325.
Keep scalar+RX support as best current fixed rule1.315/.991 and1.266/.896.

`reports/2026_10_18_ds23_remaining_failures/README.md` contains full controls
and figures for257/202/273. Best single-family GPS-oracle deletions still
leave2.861/2.820,2.406/2.402,1.913/1.922km respectively. Receiver deletions
also fail to solve them. Thirteen fixed regional starts all converge to the
same displaced endpoint on each scan (spread<3e-8km), using fixed learned
labels/masks. These are not association-reselecting full pipeline restarts.

New receiver RF-dependent linear-rate mode (one/RX, within band, sigma0/.25/1
Hz/s/GHz) barely helps2171.025→1.009km and does not fix257. Seed-state and
receiver-basis dimensions both expanded; zero mode replays to~1e-8km.

257 whole-family search:26 all-bank single-family alternatives and35 pairs/
triples,114.25s, no budget truncation, no accepted RF improvement. One valid
single replacement63070→48482 on both RXs gives1.083/.831km, but full
normalized generalized c0 RF loss is15.268 worse than incumbent. Data cost
only+2.804; phase quadratic+5.318 and phase Gamma+4.972 dominate the
disadvantage. Challenger phase−5.612s vsincumbent−.980s. Do not GPS-select
it or label it true. Plot and decomposed receipts in remaining-failures report.
This is a useful next focus: conditional causal uncertainty/identity ambiguity,
not more regional starts or an arbitrary location-selected prior.

No analysis subprocesses remain intentionally running after these cohorts.
No new RF, IQ reread or QNAP mutation. Tests passed: history/calibration/
variance10, likelihood weights6, RF-rate basis/seed-state3. Old intermediate
script failures were missing SciPy (removed dependency), a seed-dimension
mismatch (fixed and tested), and a nested pytest.approx literal (fixed).
Goal stays active;0.5km mean+median is not achieved. Need untouched-scan
validation and eventually broader DS23 coverage, not just these development20.

### Causal-history cohort completed

`reports/2026_10_18_ds23_history_calibrated_phase/` now contains all20 cases,
protocol, validation, source/input hashes, CSV and figures. All20 qualified on
strictly earlier historical TLE prediction, all final paired gates pass.
The declared primary mean+distribution rule reaches mean/median1.315/.991km
c0 and1.266/.896km fitted-c. Mean-only:1.435/1.220 and1.407/1.055;
distribution-only:1.399/1.094 and1.359/1.002. Baseline weighted fragment300
replays1.452/1.225 and1.427/1.030. No GPS-based per-scan selection.
217 primary1.025/.869km. Target remains unmet; no goal completion.

`tools/learn_ds23_phase_variance_law.py` separates phase floor and causal
age/disagreement gain. SciPy is unavailable; deterministic bounded 2D grids
with refinement implement the numerical search. `tools/run_ds23_phase_variance_law.py`
is running a two-worker20-case cohort, output
`reports/2026_10_18_ds23_phase_variance_law/`, log
`/tmp/ds23-variance-law-cohort.log`, exec session36166. It qualifies against
the scalar learned prior using earlier-TLE predictive density only; otherwise
falls back. On217 it qualifies but worsens1.025/.869 to1.332/1.245km.
Keep that regression; do not GPS-select between models. Ten relevant tests
passed including history provenance, prior mean units, Gaussian fallback and
variance law monotonicity. Next: test equal weights under learned priors,
diagnose worst257/202, and validate a frozen rule on untouched scans.

Signed phase prior means from *past* TLE differences are being tested:
`tools/probe_ds23_causal_phase_mean.py`. It uses the frozen RX support weights
and300Hz fragment priors. Mean = −rho*clip((age+150)/epoch_gap,0,2)*old_new_alignment,
capped at3 prior sigma and15s. rho is0,.5,1, fixed sensitivity values. Means
are independent of RF and GPS; covariances are unchanged. Five phase rounds,
48 steps and four paired gate rounds remain matched. rho=0 exactly reproduces
the weighted fragment300 control. Posterior mean bookkeeping uses latent
prior penalties, not incorrectly penalizing the nonzero absolute mean.

Initial outcomes:

| Case | rho0 c0/fitted km | rho.5 | rho1 |
|---|---:|---:|---:|
|217 |2.846/2.764 |2.557/2.478 |2.266/2.179 |
|45 |0.551/0.947 |0.529/0.905 |0.510/0.866 |

Next: qualify history-selected forecast shrinkage/phase uncertainty without GPS,
using three or more earlier TLEs and prefix-only prediction. The existing
`tools/dsx01_causal_forecast.py::select_history_shrinkage` is a useful numerical
reference but contains DSX01-specific paths in its class; avoid importing a
DSX01 fitted state or old future-TLE report into inference. Broader orbital
mean/covariance forecasts can be tested only with causal input receipts.

`tools/export_ds23_causal_history.py` reads the protected archive through the
read-only TleArchiveReader and prints per-case JSON. Passwordless sudo is
available for this read; no archive mutation is performed. Normal user access
fails permission checks. An export for217 is currently/most recently running
with output `reports/2026_10_18_ds23_causal_phase_mean/history/DS23-0217.json`.
Check completion/JSON before using it. It selects only epochs and collection
times before that scan,72h history, genuine epochs separated by≥1s, earliest
publication per exact epoch. Do not use a later scan's history for an earlier
scan. Train/select shrinkage from pre-RF TLE transitions only, not location error.

An optional user question is pending: independent scans versus also evaluating
stationary multi-scan pooling. Default remains independent scans; no pooling has
been run. Keep25×25km regional initialization centered37.906,−122.545, paired
c0/fitted-c controls, true GPS only in evaluation, and all failures in denominators.

## Tools and reports

- `tools/probe_algo01_0217_improvements.py`, `report_algo01_0217_improvements.py`
- `tools/evaluate_ds23_family_weighting.py`, `report_ds23_family_weighting.py`
- `tools/probe_ds23_weighted_priors.py`, `run_ds23_weighted_prior_controls.py`,
  `report_ds23_weighted_priors.py`
- `tools/probe_ds23_rf_prior_selection.py` (two diagnostic cases completed)
- `tools/probe_ds23_receiver_smooth_prior.py` (217 unweighted0/50Hz controls)
- `tools/probe_ds23_shared_clock.py` (217 completed)
- `tools/probe_ds23_delay_curvature.py` (217 diagnostic only)
- `reports/2026_10_18_ds23_family_weighting_active_support/`
- `reports/2026_10_18_ds23_weighted_prior_controls/`
- `reports/2026_10_18_ds23_causal_phase_mean/`

Use `.venv/bin/python`, PYTHONPATH=src:tools, OPENBLAS_NUM_THREADS=1,
OMP_NUM_THREADS=1; use apply_patch for handwritten edits. Keep numerical work
bounded and share progress at least every60s. No new RF or QNAP mutation.

## Checkpoint, 2026-10-19: current causal evidence studies

This checkpoint supersedes the older progress table above. The active target
remains mean AND median <=0.5 km; it is not achieved. These are the original
20 development scans, not all413 DS23 scans or untouched validation.

| Fixed rule | c0 mean/median km | Fitted-c mean/median km |
|---|---:|---:|
| RX support + causal-history Student phase prior |1.315/0.991 |1.266/0.896 |
| Equal weights, same retained points |1.411/1.361 |1.320/1.175 |
| Confidence-only, paired fallback |1.364/1.131 |1.306/1.010 |
| Support × confidence, paired fallback |1.308/0.999 |1.260/0.902 |
| Confident-only, paired fallback |1.395/1.298 |1.393/1.255 |
| RF-selected same-family/RF fragment covariance |1.289/1.130 |1.254/0.957 |
| Pre-RF qualified shape ensemble |1.318/0.969 |1.266/0.843 |
| Statistically supported extra graph curvature |1.298/0.901 |1.243/0.881 |
| Curvature + causal shape, fixed composition |1.302/0.941 |1.245/0.851 |

Confidence soft controls have exact incumbent masks and no additional trimming;
paired trial failures cause a recorded incumbent fallback. Conditional confidence
does not certify orbital accuracy or geometric information. Confidence-only,
support×confidence and confident-only fail respectively6,7,5 of20 paired trials.
All final policy outputs pass gates. Rho0.5/.9 pass17/15 cases, selected by c0
normalized ELBO among paired-valid candidates; marginal fragment sigma300 Hz
stays fixed. This does not improve both mean/median metrics.

Shape interpolation/extrapolation is learned only on causal earlier TLE triples
with the old chronological pre-RF split and complexity penalty.19 cases qualify,
17 choose interpolate.125,2 interpolate.25,1 zero. Original state uncertainty
modes and phase priors stay fixed. Derived arrays are large; keep full local
files but publish compact distinctly named receipts with hashes/rebuild commands,
small model-choice files and lossless result archives, not fake replacement inputs.

Statistical curvature promotes29 existing graph fragments/705 calibration points
with >=12 points, span20s, degree<=4, nonlinear weighted deltaBIC>=10 and existing
noise screen, only when both c arms already agree on frozen family/alias.
Original calibration never removed. Many were already associated output tracks,
so705 is not a new unique association count.217 improves to.845/.685 km with
curvature alone;257/273 have no eligible extra old graph curve. Fixed composition
with shape mean passes all20 but gains are not additive. ALGO01 default unchanged.

Dynamic pilot-only delay/Doppler synthetic control uses pinned acquisition.py
from remote commit772633600, never dirty unrelated workspace DSP changes. Both
edges yield positive delay curvature gain.999882 and RMS.376 samples at2.5MHz;
negative delay misses2902samples. This is reference integer epoch, noiseless,
truth-seeded CFO search, not production dense GLRT fractional timing qualification
or a resolution of the unexplained negative real frame-phase relation.

Current user-requested association diagnostics use217 plus worst primary cases
257/202/273. Same-RX/different-family conditioned residual correlations remain
larger than same-family/cross-RX; descriptive, not causal proof. Six valid new
secondary-assisted curves add111 genuinely unused probes,46 secondary selections,
without removing original calibration:217 error1.025/.869→1.193/1.140km;
2573.722/3.699→3.866/3.725;2023.061/3.060→3.034/3.034;273no additions.
This does not solve the error and should not be promoted by point count alone.

New tools and reports: tools/probe_ds23_fixed_confidence.py,
probe_ds23_joint_family_search.py, probe_ds23_secondary_curves.py;
reports/2026_10_19_ds23_association_evidence and
reports/2026_10_19_ds23_curvature_shape_study.33 focused tests pass. The joint
search tests three alternatives/family and all72 two/three/four-family beam
operations.217 has no c0 gate-passing replacement;257 has39 singles/72 joint
and no RF improvement.273 accepts a slight RF gain but worsens2.412/2.345→
2.837/2.797km.202's75-fragment model hit420s; the retry uses2×12 proposal
steps with all finalists fully refined5×48 in BOTH arms. Preserve initial
attempt receipts/source_v1 and exact masks/priors. Final202 search still running
at the initial checkpoint. It subsequently completed all60 singles and72 joint
operations: no proposal passed c0 gates. The retry hit480s after completing60
singles and54 joint operations; exact checkpoint reuse and two numerical workers
finished the remaining18, with unchanged data, priors and proposal budget.
All four diagnostic cases are now complete. The source_v1 snapshot reproduces
the first three searches; the source-version receipt and resumption driver
document202's bounded computation. This is a finite beam, not proof that all
labels are correct. No GPS-favored replacement was promoted.

Next physically useful qualification: predict receiver/family evidence from
other families' calibration, and qualify the actual dense GLRT fractional epoch
kernel with dynamic delay/Doppler controls. Do not infer better localization
from lower CFO RMS, more associations, narrower conditional widths or GPS-favored
identity changes. Full413 and untouched validation are still outstanding.

The new before/after satellite-correction comparison is important: same-family,
cross-RX/same-band median correlation is+.461 before phase/orbit corrections
and−.020 afterward (124 matched track pairs/19 scans). Same RX/band, different
family is+.326 before and+.459 after (593pairs/20scans). Both receiver-common
and satellite-common discrepancies coexist; remaining residual correlation
alone cannot assign the localization bias entirely to hardware. Both stages
condition on the same jointly fitted receiver; no independent validation claim.

## Checkpoint: predictive calibration and native CFO response, 2026-10-19

Previous goal turn was progress: full weighting/identity/recovery studies were
pushed to remote main as5b010d735. This continuation also made progress; goal
remains active and0.5km mean/median remains unmet. All numbers below are the
original20 development scans or explicitly identified diagnostic/synthetic tests.

New shared satellite carrier-rate model (active curved support on both RX only),
otherwise identical causal-history Student phase model and fixed primary masks:
rate_prior0.25Hz/s gives c0mean/median1.3147/.9894km, fitted1.2655/.8949;
rate_prior1 gives1.3117/.9932 and1.2661/.8943. RF-only normalizedELBO selection
among paired-valid widths0/.25/1 chooses1 on10 cases and0 on10, yielding
1.3135/.9763 and1.2635/.8853km. No GPS selection, no point removal or identity
change, both c arms same data/prior/budget. All final outputs pass native gates.
This is too small a gain to explain the main error.

tools/probe_ds23_receiver_prediction.py tests reciprocal omission of the largest
cross-RX family's RX1/RX2 curves, training position/nuisance from remaining data,
then predicting test CFO with local joint position/nuisance covariance. Test
groups use their Gamma(2,2) prior noise, not their own fitted residuals; shared
family phase is learned on the opposite training RX. Test identities/aliases
and radio-only noise proxy remain frozen from the incumbent, so this is a
conditional calibration test, not blind-ID validation or raw-data independence.
3phase×24steps diagnostic fold;5×48 full paired fits restore every point.
Cases217/257/273 and smallest-fragment high-band case274 all reject both added
fast receiver and half-shared band covariance, requiring gains in BOTH directions.
On217 fastRX improves RX1 predictive score7.27 but worsens RX2 by1.65 and moves
c0position1.025→1.509km. No new receiver default.

Native timing controls use .build-short-window-native-host/libleo-adaptive-detector.so,
SHA110c3e8f74952ef6950e35d264854f7acd4024dbeeca18279ce33f09ddaa2768,
matching its receipt. THREE current C sources also exactly match the build:
full_search.c, fine_precision.h, native_presence/presence.c. This does NOT prove
the binary used for each DS23 capture. Blind native search over26 dynamic pilot
scenes gives positive range-delay curvature gain.999984, epochRMS.105/.110samples
at2.5MHz (~42/44ns). No IQ, GPS or TLE needed. Prior negative real frame timing
is still not qualified pseudorange.

Matched ±2000Hz/s chirps, same envelope/epoch, expose effective-CFO-time local
sensitivity. Most320pairs across2rates×2edges×10CFOfrequencies×8phases are within
.459ms of midpoint; one near-DC upper2.5MHz peak switch reaches10.6ms. No global
8ms timestamp shift is justified. Stationary OFF-GRID signals show much larger
error than exact-bin signals: the native500Hz FFT three-magnitude-bin parabola
pulls estimates toward bin centers. This is a concrete noiseless estimator bias.

tools/probe_native_fft_bias.py predicts the response solely from published pilot
template power over the same alternating OFDM symbols and the known500Hz
interpolator, without training on native results. Its inverse reduces RMS on
64 eligible independent cases/rate/edge from~10.8Hz to.572/.319Hz at2.5MHz and
.125/.107Hz at10MHz. Near-DC/boundary cases explicitly remain uncorrected.
No correction has been applied to DS23. Match actual capture binary/config,
qualify noise/fading and propagate uncertainty before any deployment claim.
Canonical measured CFO must be used BEFORE graph integer alias lifting: the
alias period is not divisible by500Hz. Do not quietly alter golden GLRT fixtures.

Independent modulation-clock warp ±20/40ppm changes synthetic native CFO by
roughly10–32Hz RMS. An oracle SFO-resampling control only partly removes dynamic
error; it is not a real-data algorithm. Literature provides an independent
reason to distinguish frame/carrier clocks and jointly estimate arrival/CFO/SFO:
https://arxiv.org/html/2501.05302v1 (frame/carrier can differ by beam; timing
precompensation is a hypothesis), and ION2026 Psiaki/Bowman abstract20760
(joint edge-pilot carrier, code/carrier divergence, arrival estimation). These
do not prove the cause of DS23 errors or calibrate our rate priors.

New report reports/2026_10_19_ds23_clock_measurement_controls/README.md includes
all20 paired rate results,4receiver probes, native controlled figures, exact
binary/receipt, source snapshots and lossless evidence.13 focused tests pass.

NEXT ACTION: bounded re-analysis of EXISTING DS23 IQ windows, fixed by RF-only
criteria, to compare native CFO to local pilot CFO/SFO refinement and verify
native bin-bias applicability. Never collect new RF, mutate QNAP, use future TLE,
or fit calibration to GPS. Raw roots/manifests are in DS23 manifest raw_recording
and must be read via existing recording ports; keep reads bounded to selected
chunks, not a multi-hour corpus sweep. Avoid printing raw_recording/chunks:
it has thousands of entries (one accidental full-dict diagnostic output was
truncated; no scientific input changed). Print scalar keys/path/count only.
Existing code src/leo/storage/scanner_analysis_source.py / short_window.py
provides read-side ports. The current root no longer has scanner_tracking_source.py;
use the frozen public exports for prior fits, not an invented replacement path.

## Checkpoint: bounded archived-IQ refinement, 2026-10-19

This continuation made measurable progress; the 0.5 km mean/median goal remains
active and unmet. No new RF was collected and no original scientific fixture,
tracking contract, satellite label or causal input was changed.

New read-side tools export whole original graph curves via ShortWindowReader
using declared segment authorities and validated chunk/window hashes. Selection
is radio-only: largest eligible early curved track per RX/band, 12–96 points,
all visits below 1024. Scans 202 and 274 provide three and four curves, 74 and
166 observations. Raw NPZ panels are local replay prerequisites, not published
payloads. Both numerical jobs are complete; do not restart them as missing.

tools/local_pilot_refinement.py uses a Fourier-interpolated known-pilot template,
independent complex amplitude/DC per frame, direct local carrier fitting, and
optional epoch/rate search. Its one rate ties frame cadence and intra-frame
sample rate; it is not a fully independent clock model. Same polynomial degree,
selected only from original data, gives RMS Hz (original -> joint):
202 RX1 CH2 66.84->62.18, RX1 CH7 87.51->89.67, RX2 CH2 41.11->11.84;
274 RX1 CH4 147.73->144.16, RX1 CH6 135.35->129.64,
RX2 CH3 43.50->9.36, RX2 CH7 98.86->9.80. Some bounded fits hit search limits;
raw radio tables retain them, and position trials revert boundary/control
failures to original CFO. All original points remain present.

Partial matched c position interventions retain the original noise, times,
calibration masks, labels, aliases and priors; five phase rounds x48 steps,
regional-center cold start. All four new paired trials pass final gates.
202 c0/fitted baseline3.0609/3.0602 km -> joint3.0653/3.0645; only37 active
calibration points change. 274 baseline1.3173/1.2769 -> fixed1.3080/1.2673 ->
joint1.2980/1.2563; fixed152 and joint165 active points change. Strong radio
RMS gains do not establish position improvement or solve phase degeneracy.

The experimental native binary matches its own build receipt but not every
archived CFO. Its500Hz inverse is NOT applied. The clean owned public GLRT64
scorer exactly reproduces67/74 and141/166 archived scores; bounded acquired-CFO
reconstruction over residual bins0,+/-1,+/-2 resolves no further cases. Seven
and25 exceptions remain explicit. Actual acquisition binary/config provenance
is not proven. Score normalization differs from the local projection energy;
their magnitudes cannot be compared as evidences. The actual alias period is
1/(4.4e-6)=227272.72727272726Hz, imported from the repository constant.

Six focused tests pass: original three local-model controls plus alias-preserving
updates/boundary fallback, wrong-peak rejection and a synthetic case that
reconstructs an unpersisted acquired CFO. Report, figures, numerical evidence,
source snapshots and receipts are under
reports/2026_10_19_ds23_raw_pilot_refinement/. ALGO01 and DBG01 link this study;
the baseline algorithm remains unchanged. Raw NPZ panels and partial/initial
exploratory files are excluded from publication.

NEXT ACTION: qualify actual acquisition/config support and RF-only uncertainty
after refinement. The old receiver-blind radio law/floor40Hz underweights the
new apparent RX2 precision. Do not silently lower floor40: WindowNoise enforces
it and a residual normalization uses reference40Hz. Any new precise-noise
research model needs consistent normalization and matching c0/fitted controls,
preserving every unmodified observation's exact effective original noise.
Use independent-frame/predictive radio checks, account for differing effective
times, optimize the measured local-fit cost before widening re-analysis, and
then test untouched scans. Full413/locality generalization is still pending.
