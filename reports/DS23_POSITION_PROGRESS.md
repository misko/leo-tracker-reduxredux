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
