# DSX01 polynomial satellite analysis checkpoint

The current user review focuses on DSX01-S01, one original Graph fragment at a
time. `scan1_track_review/README.md` indexes all 170 fragments (4,487 original
points); the first receiver/channel has 14 individual figures. Original fragment
IDs are retained, and review order is receiver/channel/start time. These figures
reproduce the frozen fitted-c fit without recalibration.

The first fragment, S01-RX1-CH1-T008, has 28 points from 0.718 to 26.976 seconds.
Its quadratic residual RMS is 113.1 Hz; the NORAD 47357 model has 136.7 Hz RMS,
mean -1.55 Hz and residual slope +6.44 Hz/s. It passes the existing screen and is
the sole passing candidate, but the upward residual trend merits inspection.
Passing a screen is not evidence that residuals are perfectly white or that a
satellite identity is authenticated. The next fragment is T004. The first
rejected fragment in this lane is T012, rejected by the component bias bound.

The all-five-scan fixed-known-position shared-phase fits are complete under
`cohort/`, paired c=0 and fitted-c. Original Graph membership and measured-curvature
calibration eligibility are fixed. Hardware drift prior sigma is 0.5 Hz/s with
bound 1 Hz/s. Linear fragments associate but do not calibrate hardware or orbital
phase. Fitted-c associated counts are 1,975 / 1,857 / 2,649 / 1,995 / 1,876,
total 10,352 of 20,084 raw GLRT points. The c=0 total is 10,371. These are
frequency-fit results at supplied GPS, not localization improvements.

`audit/` tests all candidates against the existing gates before selecting a
winner; it adds only eight points. `phase_split_audit/` contains diagnostic
independent phase grids and fixed midpoint splits, which are not promoted
associations. `common_mode/` finds descriptive correlation between residuals of
different candidate satellites sharing a receiver/band. This motivates a
multi-track hardware-error investigation but does not establish its cause.

Separate complete-point refined-CFO experiments are under
`../2026_10_17_continuous_track_cfo/`. They do not remove the wrong-position
preference in the DSX01-S01 objective. No sub-0.5 km result is established.

Remaining work: review individual tracks, test common residual explanations
without introducing arbitrary per-track slopes, and write the consolidated
deep-dive figures/report. Do not interpret diagnostic upper bounds as accepted
matches, or alter earlier sealed reports.

## Continuation: tracks 2 and 3 and a stricter merge check

`first_track_join_checks_v2/README.md` reviews T004 and T011 and tests four
selected pairs against all 1,707 candidates, paired c=0/fitted-c. T008 + T011
has one passing candidate, 47357, and shares one constant at 120.98 Hz RMS over
all 41 points. The two fragment displays require different integer alias lifts;
v2 corrects a v1 plotting error without changing numerical fits. This remains
conditional on the frozen hardware/phase fit, which included reviewed curved
tracks. It is not independent identity validation.

Cross-receiver and cross-band same-candidate pairs fail a shared-constant check;
one cross-receiver example has only 148 Hz pooled RMS yet fails member means.
Do not promote all same-NORAD proposals to one track or fit extra slopes.

`identified_track_merging.consolidate` now has an optional
`accept_joined_residual` callback. Its historical default exactly reproduces both
frozen S01 baseline arms. `scan1_pooled_merge_check/` holds a matched 3-way
experiment: original 10-second limit gives 69/68 groups c0/fitted-c; adding the
pooled residual check gives 74/71; using the pooled check with a 30-second limit
gives 68/68 and joins T008 + T011. All retain the same 1,975 points and candidate
labels. No new association coverage or location improvement is claimed.

Eighteen targeted tests passed for merger, shared-constant profiling, residual
screen parity and selected-pair checks. The next chronological fragment in the
RX1/CH1 review is T005, followed by T000 and first rejection T012.

The exact S01 phase bank and receipt are now durable under
`frozen_inputs/DSX01-S01/`. Current merge/review sources and relevant tests are
snapshotted in `first_track_join_checks_v2/code_snapshot/`. Both new result
directories have verified hash seals. All eight selected-pair numerical outputs
were checked identical before and after correcting the alias display.
Complete-point IQ measurement records for DS22-001 and DSX01-S01 are archived
losslessly in `../2026_10_17_continuous_track_cfo/frozen_measurements/` with
original and compressed hashes; they no longer depend on temporary files.

## Continuation: tracks 4–6

`tracks_four_to_six/README.md` reviews RX1/CH1 T005, T000 and first rejection
T012. A paired anchor-only phase profile excludes each target and freezes
nomination labels and exact grids across c arms. T005 transfers from curved
CH2/T002 at -2.406 s, target RMS 127 Hz; T000 transfers from two RX2/high-band
curved anchors near +0.485 s but retains its +10.3 Hz/s trend. These are
conditional diagnostics with frozen hardware, not new independent identity or
position validations. No short fragment selects a usable phase calibration.

T005 + CH2/T002 (68 points) and T000 + CH3/T008 (37 points) pass shared-constant
checks in fitted-c; both fail in c=0. The first c0 failure is near the pooled BIC
threshold, while the fitted-c T000 pooled slope z=2.91 is near its limit of 3.
Do not interpret these frequency-fit differences as location improvements.

The seven current 64936 nominations are 118 points, all unqualified for
individual curvature calibration. None of the 81 qualified curved S01 tracks
passes for 64936 on an 81-point phase grid across its ±5.163 s prior bound.
An unsupported short-family counterfactual at phase -0.774 s reduces pooled RMS
to 167.7 Hz and passes the pooled screen, but individual means fail. It remains
unassociated; do not promote that counterfactual phase or widen the bias bound.

The exact original-vs-qualified CFO replay fixes hardware/phase/labels/weights
and retains all points. Fitted-c slopes T005/T000/T012 change from
-1.74/+10.33/-30.87 to -1.71/+7.22/-30.32 Hz/s. Refined T012 still needs
+3,903 Hz, outside the unchanged 3,000 Hz bound. Existing qualified measurement
refinement does not remove these problems. Twenty-eight targeted tests passed.
Next chronological RX1/CH1 review: T013, then T009, both currently rejected.

## User correction: T009's isolated endpoint

The user specifically identified the final T009 point as unsupported curvature.
`t009_robust_order/README.md` and `polynomial_comparison.png` implement and
illustrate a radio-only Gaussian/clutter EM order comparison, degrees 1–4,
with fixed 150 Hz noise and k log(n) penalty. All 27 points contribute to the
score. Default selection is degree 2, 26 points at 115.4 Hz RMS, with the final
point retained unassociated at +9.451 kHz residual after an 8.166-second gap.
Degree 3 is nearly tied; the robust degree 2/3/4 fits all exclude the endpoint.
The old quartic endpoint leverage is 0.993. Sensitivity: 8/9 tested settings
reject the endpoint; noise200Hz/clutter0.5% retains all-point quartic. Do not
claim a universally calibrated robust fitter or ban genuine quartic curves.

Matched c0/fitted-c candidate-phase audits use the exact same radio-only
partition, all 1,707 candidates and 51 phase vectors. Original 27-point curve:
no passing candidate. Repaired core: sole candidate 67920, phase -1.553 s,
116.4 Hz RMS, bias -1,138/-1,328 Hz c0/fc. Raw core curvature qualifies (411 Hz
affine residual, 26.26 s span), so short fragments do not calibrate this phase.
Hardware and phases of already-supported satellites are frozen.

`incremental_association_overlay.json` proposes 26 new compatible points,
1,975 -> 2,001 in each S01 arm, preserving existing assignments and all 4,487
Graph IDs. No existing admitted fragment uses 67920. Original baseline files
are unchanged. This is fixed-known-position compatibility, not authenticated
identity or new localization accuracy. Goal remains unachieved.

The endpoint has a uniquely qualified pilot measurement (22 Hz reported
uncertainty), only -43.8 Hz from its old native CFO. Retain it as a measurement;
do not call it bad data. Qualified replay on the same 26 core IDs still passes,
144 Hz RMS, residual slope +1.26 Hz/s, with hardware/phase/label fixed.
Twenty-six targeted tests passed including seven new robust-polynomial tests.

T013 review was started before the user's T009 steering: its 17-point current
56413 match has 379 Hz RMS and -65.3 Hz/s residual slope; no proposed repair or
relaxed calibration has been promoted. Resume it after integrating/validating
the T009 repair pattern across the existing corpus.

## Generalized robust-membership comparison

`../2026_10_17_robust_curve_reassociation/README.md` completes the bounded
all-five-DSX01 partition and DS22-001 comparison. There are just two explicit
background points among 18,338 DSX01 Graph points; DS22-001 membership is
unchanged. S01 gains the same 26 T009 IDs in both c arms. A public lossless
partition port binds raw values/times/IDs and the merger consumes that same
population. Unchanged numerical inputs have explicit reuse receipts.

Important new finding: raw S02 fitted-c refitting drops 1,857 -> 98 compatible
points while improving the old scalar objective on the same repaired population.
A new curved-only, whole-member-noise-gated score rejects that state in favour
of the old parameters at identical supplied GPS. This is a saved-state pool
safeguard, not a fully optimized new localization algorithm. Safe all-DSX01
totals are 10,397 / 10,378 points c0/fitted-c, +26 in each arm.

Matched independent cold studies remain inaccurate (S01 ~41.6 km with a sparse
one-basin grid, DS22-001 14.816 km). Matched resumed S01 studies all end at the
same 12.5298 km / 1,814 points before and after repair. New-score saved-state
ranking prefers the known-position fits over these wrong-position proposals,
but contains a GPS proposal and is not blind validation. No sub-0.5 km claim.
Twenty-eight current focused tests and changed-file Ruff checks pass. Sources,
protocols, point accounting, figures and checkpoint are preserved in the new
report directory. All bounded jobs have completed; the larger goal is active.

## Noise-gated score inside actual independent-position fitting

`../2026_10_17_noise_gated_position/README.md` now implements monotonic
whole-track-feasible curved-only updates and state ranking, with exact nonlinear
finalists. Four matched legacy-score controls and four new searches share
geographic/seed caps and causal inputs; each c pair uses a common earlier blind
c0 initializer. These are resumed local searches, not global/cold results.

S01 legacy control error is 11.9679 km in both arms. New c0/fitted-c errors are
8.3671 / 8.5015 km, with 2,490 / 2,509 associated points and 70 / 91 merged
tracks. DS22-001 legacy is 12.9237 km in both arms; new errors are 3.2411 /
1.8947 km, with 1,632 / 1,602 points and 50 / 47 tracks. Thirty-five tests pass.

Important remaining problem: all four new wrong endpoints score better than
both tested GPS parameter initializations in separate post-search diagnostics.
Noise-like residuals remain insufficient for correct localization. New c arms
agree on all shared point labels (S01 2,334; DS22 1,567). Conditional frozen-state
random-intercept controls have far lower support, but are not optimized nulls or
identity FDR. All point IDs, traces, mergers, RMS tables and figures are saved.

Next diagnostic is fixed-label family transfer to GPS with only allowed
curved-calibrated hardware/phase refits, kept separate from blind results. This
should distinguish an initialization failure from incompatible families or a
frequency-model error before more geographic search. The <0.5 km / full-corpus
goal remains active and unachieved; all current bounded jobs have completed.

## Fixed-family transfer identifies phase clipping

`../2026_10_17_fixed_family_transfer/README.md` freezes source blind c0 candidate
families in both c arms, keeping all curved observations and excluding linear
members even from nuisance-constant calibration. S01 transfer to GPS exposes
NORAD 100320's phase clipped at -3 s. With hardware and other phases frozen,
three curved RX2 arcs jointly prefer -3.7 s; all 1707 candidates are audited on
601 phase states (supported satellites stay locked). Only 100320 passes all
three arcs on this grid, in both c arms.

The phase-only repair adds 173 known-GPS points, including 141 curved and two
16-point linear fragments associated afterward. Counts are 2009 -> 2182 per c
arm, no lost/relabelled existing IDs, 45.49% raw GLRT coverage. Baseline 2009
already includes eight gate-ordering gains above the previous 2001 repair.
This is conditional compatibility, not external satellite identity validation.

Exact fixed-family blind local searches reach S01 6.3555 km (separate constants)
or 6.4793 km (merged); both c arms agree. Releasing the phase box alone does not
move those endpoints. DS22-001 gives 2.1393 km, worse than the prior 1.8947 km.
Thus phase clipping explains missed tracks but not the whole position bias.
44 tests pass. Reports, matrices, figures, immutable IDs and source snapshots
are preserved. No <0.5 km result and no goal-completion claim; all jobs terminal.

## Cohort phase repair and nuisance-information audit

`../2026_10_17_cohort_phase_repair/README.md` completes the five-scan phase-family
inventory, 16 scalar profiles and ten full-bank comparisons. Use `curved_only/`:
the preserved parent-level v1 incorrectly locked phases with linear-only support.
The corrected policy allows only admitted measured-curved tracks to lock phases;
old linear associations cannot rank or veto a phase. All five approved families
remain unique on the tested candidate/phase grid in both arms after this fix.

Known-GPS gains are +282 / 0 / 117 / 105 / 0 points by scan, +504 per arm (400
curved, 104 linear). Totals: c0 10909 / 20084 (54.3169%), 335 merged tracks;
fitted-c 10890 / 20084 (54.2223%), 312 tracks. No old losses/relabels occur.
This includes the earlier 173-point gain; new beyond that experiment is 331.
Three other nominated families remain rejected; no member pruning. Hardware
is frozen and only the newly curved-calibrated phases change.

The same report contains completed RF/timing binding audits and twelve matched
RF-coefficient plus twelve phase-prior sensitivity runs. No confirmed metadata,
timestamp or RF normalization bug was found. Alternative RF coefficients can
produce nearer endpoints but fail the frequency-fit/compatibility comparison,
so they are rejected. Phase-prior floors leave substantial position bias.

`../2026_10_17_position_information/README.md` adds a tested nuisance-projection
kernel and six actual local-information audits. S01 conditional major axes grow
from 13 m with nuisance fixed to about 0.62 km after profiling; DS22-001 grows
from 15 m to 0.85 km. These are conditional Gaussian mean-model diagnostics,
not calibrated position bounds or full-score covariances. Actual errors remain
6.36 / 6.48 km S01 separate/merged and 2.14 km DS22 separate.

Two new merged DS22 searches retain the same 29 curved constants, so produce
the same 2.1393 km position, 1515 extended points / 47 groups. A separate blind
common-position pilot assumes S01/DS22-001 share one stationary position while
keeping all frequency calibration scan-local. Both arms end at 5.5575 km after
49 locations; all 2642 fixed curved points remain costed. This does not solve
the bias or outperform DS22 alone. No known-GPS labels seed the pilot.

65 focused tests and changed-source Ruff checks pass. All bounded jobs are
terminal and sources/IDs/matrices/evaluations are preserved. Goal remains active,
unachieved and without an external blocker. Next: per-satellite position-score
conflicts and full causal TLE orbital discrepancy beyond scalar phase; blind
S02–S05 labels before any larger shared-position fit, plus wider DS22 validation.

## User review: longest unassociated curve

`../2026_10_17_s01_association_views/` supplies complete native-CFO all/associated/
unassociated views for all 4797 S01 raw GLRT points, with per-channel IDs. It
uses the previous2291-point fitted-c overlay and preserves all170 retained
polynomial cores (4486points) plus311 raw marks outside
those cores, including T009's retained background point.

`../2026_10_17_longest_unassociated_s01/README.md` then investigates the longest
duration fragment, RX1CH6T001,71points/72.033s. Full1707-candidate x601phase
competition, paired c arms, finds sole passing candidate63474 /STARLINK-33735
near-2.7s. The old+/-0.616s phase box excluded it. TargetRMS1556->132Hz with
no changed/dropped points. The quartic itself is credible (131Hz, strong raw
curvature). No new per-track slope or satellite-independent shape is adopted.

CH2T001 andCH7T001 are curved companions; each of the three passes when phase
is learned from the other two, conditional on frozen hardware. Old nominee
CH3T002 does not fit this curve and had vetoed the all-member family. Existing
whole-member clutter evidence retains its27-point cost while supporting153
curved points. The resulting per-fragment overlay gains231=153curved+78linear
points in both arms,2291->2522 /4797 (52.5745%), no old losses/relabels;
85/79merged groups c0/fc. Original sealed reports and baseline files stay fixed.

Important qualification: pooled153-point residuals are correlated. All member
checks pass, but pooledlag1 is.492 at-2.7s and.476 at-2.75s, above.323. A
diagnostic shared residual polynomial up todegree4 neither resolves this nor
wins an incremental complexity comparison. Do not call the whole family one
noise-white track, authenticated identity or a position improvement. Keep
fragment/group residual checks and investigate correlation separately.

Concurrent ../2026_10_17_family_conflicts_ds22_expansion/ completes four tangent
influence audits and ten genuinely cold searches on predeclared DS22indices
001/034/069/102/137 (both formats, sealed137prefix). Commonphase sigma1s/bound3s
is an explicit sensitivity hypothesis, different from older priors. Errors range
3.856..247.269km. Strong c/basin disagreement shows cold discovery remains
unreliable. No cherry-picked best-arm or whole-corpus accuracy claim.069c0
was verified terminal143 then resumed only at its saved exact stage. Alljobs
are terminal.70focused tests pass, with new influence/basin/consensus tests.

Goal active and unachieved, no external blocker. Next: curve-first robust-family
rescue within independently selected blind states; a smoother regional physical
proposal score with strict final gates; and validation of cross-track residual
correlation. Never seed independent position work with these known-GPS labels.

## S01 phase sensitivity and next-longest track: retrospective TLE test

New outputs: ../2026_10_17_s01_phase_sensitivity/ and
../2026_10_17_s01_ch4_t001_diagnosis/. The former keeps original graph-derived
polynomials, hardware, established phases and labels frozen. Three multiply
nominated new curved families are tested with unchanged priors out to ±15s.
62052 at −1.0s adds 86 points; 63474 at −2.7s adds 231 (the previous result).
Both c arms therefore reach 2608/4797 raw points (54.37%), 2189 unassociated:
1878 on 57 polynomial fragments plus 311 outside retained polynomials.
No further gain above the 2.7s floor in this restricted experiment. This is not
a global refit of already supported phases. Both recovered identities pass
all-bank competition on their declared curved witnesses; 63474's pooled
correlation remains unresolved. The population helper's 4487 original Graph
points are explicitly distinguished from all 4797 raw detections in new outputs.

The next longest unassociated fragment is RX1 CH4 T001, 45 points/59.968s,
empirical quartic RMS69.683Hz. No member of the causal 1707-candidate bank
passes all physical gates at any sampled phase in ±15s. Leading69333's
current RMS234.61Hz improves only to168.97Hz by phase alone and stays structured.
One shared extra rate (~11.83Hz/s at11.5GHz) makes all nine69333 curved nominees
pass in-sample, but exceeds the small LNB drift assumption. The omitted-target
transfer remains marginally correlated and fails. This rate cannot be declared
hardware drift. Unbounded radial/cross tangents require implausibly large
displacements; bounded sensitivities and all parameter penalties are retained.

User additionally requested post-observation TLEs. The existing leo service UID
can read the local archive through TleArchiveReader (sudo -n, no archive writes,
no credentials or network collection). Exported past catalogue exactly
reproduces the causal bank. First post-collection still contains the same69333
element. The first future-epoch69333 element is epoch2026-10-16 20:21:53.962UTC,
collected23:04:06.164UTC, versus causal epoch07:50:09.495UTC. Future element
selection uses earliest epoch after scan end then earliest collection within48h,
independent of radio fit. Of1707 candidates,1671 have a future element;36 retain
causal elements explicitly. All nine tested family hypotheses have future TLEs.

For69333, future TLE + phase gives target RMS113.05Hz and passes. Only69333
passes the full matched bank/grid in both c arms. A shared future phase in
[+0.14,+0.23]s retains target and all three old curved members; +0.23s gives
7/9 curved nominees,177points,target RMS119.9Hz. No phase fits all nine. This is
retrospective compatibility, not a causal production update or authenticated ID.
Future-minus-past at65s is about[R+1.116,A−12.099,C−0.066]km, plus velocity
differences: a single along-track phase does not represent the full update.
Future TLE helps60372 and66163 but worsens62811 and100168; do not cherry-pick
post-observation elements as truth. Nine-family, matched c0/fitted-c results
and figures are retained. Direct SGP4 validates target interpolation below1Hz.
Endpoint leverage0.803 and leave-endpoint-out quartic error−299Hz remain
diagnostic; all45 points retained. No localization experiment or accuracy claim.

### Direct TLE element fits and retrospective attribution for69333

New nested output: ../2026_10_17_s01_ch4_t001_diagnosis/tle_parameter_fits/.
Actual SGP4 reinitialization at the causal element epoch tests one correction
to mean motion, inclination, RAAN, e*cos(omega), e*sin(omega), or B*, plus phase
and nine existing component constants. Hardware and known GPS fixed; nine raw
curved fragments/254points; matched c0/fitted-c. For e components, preserve
mean argument of latitude rather than injecting another phase when omega flips.
Final rows use direct SGP4, with interpolation below1Hz; clones reproduce the
original orbit exactly. Four owned scientific tests pass, including e-vector
zero crossing without artificial 180deg phase. No published TLE overwritten.

At common scan time65s, causal versus later averaged eccentricity components:
e_cos −2.14434e−6 → +1.21764e−5; e_sin +1.78519e−4 → −4.19746e−5.
Semi-major axis6840.504→6840.624km. Raw omega91.9071→285.5681deg must not be
interpreted as a huge geometric rotation in this almost circular orbit. Printed
ndot/nddot are ignored by SGP4 and cannot implement the desired extra correction.

One-parameter fits recover BIC improvements184..186 for motion/plane/e-vector
versus phase-only, but target residual RMS~118..119Hz still fails correlation;
omitted-target transfers~121..122Hz also fail. Empirical shared rate RMS111.4Hz
and BIC improvement~197 remains better; it too fails pooled independent-noise.
Inclination hits its predeclared bound; B* mostly unhelpful and also bound-limited.
Mean-motion refinement follows its phase covariance ridge; do not confuse
epoch accumulated phase with independent shape evidence. Projected element
signatures correlate~0.98 with the empirical linear-rate signature. This scan
does not identify a unique wrong orbital element; c0/fitted-c results coincide.

Retrospective, fixed later-TLE eccentricity substitutions are evaluated at the
causal epoch, with mean argument latitude preserved and the same phase/rate
profiling on the same curved data. Remaining rates,Hz/s at11.5GHz:
causal11.831; replace_e_cos_only11.234; replace_e_sin_only6.527;
replace_both_e_components5.927; full_later_TLE5.106. Most of the change between
the two TLE-dependent empirical rates is attributable to the eccentricity
update, especially e_sin. This is not a percentage decomposition of true orbit
versus radio error, and the remaining rate has no established physical owner.

## Two S01 shared satellite-association prototypes

New output ../2026_10_17_s01_shared_satellite_prototypes/ implements the user's
two requested approaches. Fixed supplied GPS and existing hardware; same170
robust graph fragments/4486points, all4797raw GLRT retained in accounting.
Both start from2608/4797 (54.37%),113associated fragments. No later TLE enters
either fit. Archived past-only48h elements are exported read-only through the
existing leo service UID; consecutive mean eccentricity-vector differences at
a common epoch give a heuristic covariance, eigen-sigma floor2e-5/cap3e-4.
Phase sigma floor1s, |phase|<=15s; no claim of calibrated orbital covariance.

A: seeded family extension uses one phase + one empirical frequency slope per
satellite (|rate|<=20Hz/s at11.5GHz), fixed median-curved reference times,
whole-curve clutter and complexity cost, paired curved proposals, and30s
neighborhoods. Old accepted curved labels retained; linear tracks never select
or veto corrections. B: EM-like curved-only soft signal/clutter assignments
alternate with MAP SGP4 corrections (phase + e_cos/e_sin) per satellite;
Gaussian prior charged once per satellite, 5-sigma radius and |delta_e|<=8e-4.
Both require two curved channels to own a new correction and evaluate all1707
candidates with unchanged point/noise gates. Three bounded iterations each;
counts stabilize at iteration1, parameters still change, so do not claim full
parameter convergence or globally optimal EM.

Matched c0/fitted-c yield identical final point sets:
A3494/4797=72.8372%,129associated polynomial fragments,27.085points/fragment,
28candidate satellite IDs;942gained and56lost versus2608baseline. All56losses
are previously accepted linear points; no old retained label changes.
B3403/4797=70.9402%,132fragments,25.780points/fragment,29candidate IDs;
803gained,8lost (one linear fragment), no retained label changes. Shared3260
points all have identical IDs across methods, Jaccard0.896343; A-only234,
B-only143. Full original4797raw set is partitioned losslessly in every output;
311outside retained polynomials remain unassociated. These are associated
fragments, not newly merged carrier tracks or authenticated satellite identities.

69333: A accepts all10fragments/264points, rate11.878Hz/s, phase−1.1885s;
CH4T001112.3HzRMS passes. B accepts9/219, leaves45point CH4T001 unassociated
at129HzRMS; its e-vector correction reaches the declared5sigma boundary.
A67954 approaches its20Hz/s rate box. All accepted members pass individually,
but pooled curved-family tests pass only20/24(A) and18/25(B). Remaining common
correlation and some pooled step/trend flags prohibit asserting whole-family
independent noise or forcing those families into one merged track.

Validation reconstructs the original2608baseline IDs and labels in both c arms,
rechecks every final residual, point/alias binding, covariance causality and
curved-only calibration membership.16focused tests pass, including new shared
kernel tests (single native alias, no linear calibration, singular-direction
prior, satellite prior charged once and complete signal/clutter mass).
Figures: coverage_and_iterations.png, associated_glrt_and_tracks.png,
unassociated_glrt_and_tracks.png,69333_method_comparison.png; summary.csv,
association histories/parameters and family diagnostics retained. Executed
runner snapshot matches protocol source hash. pre_support_policy_fix/ retains
superseded initial outputs: that evaluator unnecessarily demanded a curved
owner for zero-phase unadjusted TLEs; corrected policy restores the130baseline
linear points that needed no satellite calibration. No production changes,
RF acquisition, golden-fixture updates, commit or push. No new localization
accuracy measurement; broader goal active and unachieved.
Files include parameter bounds/protocol, results, common-epoch comparison,
identifiability, validations and figures. No production association or position
accuracy claim changed; broader localization goal remains active/unachieved.
