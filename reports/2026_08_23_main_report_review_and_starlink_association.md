# Main-report synthesis: modulo-π structure and Starlink association

**Date:** 2026-08-23 UTC

**Committed-report authority reviewed:** `main` and `origin/main` at
`292dd4dc3864334a909bc41e10884903b1d323e4`

**Fresh radio authority:** 13 newly sealed Standard runs at release
`e71412cf7ff716e7a25dd846fc926f0b80dd9b12`

**Association result:** **0 of 37 eligible tracks is securely associated with a
known Starlink satellite.**

## Executive conclusion

The reports on `main` support three signal-level findings:

1. Independently acquired CFO candidates repeatedly form coherent, mostly linear
   tracks over seconds.
2. Exact Qin-pilot-compatible observations sometimes support local carrier phase
   when phase is treated modulo π.
3. Inside qualified local support, independent per-frame CFO measurements often
   predict held-out frames to tens of hertz.

They do **not** establish that the visible 20 ms teeth or the 50–75 ms analysis
windows are Starlink transmission slots, that a satellite physically changes RF
frequency at those boundaries, or that any measured track belongs to a named
spacecraft. The fresh 13-dwell orbital test strengthens that last boundary: the
primary bounded-orbit model loses to a radio-only straight line in 36/37 tracks and
all 13 dwell aggregates.

The most accurate reading is:

- the samples and known-pilot response inside a tooth are real measurements;
- the **20 ms extent and placement of each tooth are analyzer probe geometry**;
- a vertical offset between teeth is still present in the receiver-relative CFO
  estimates, but its cause is unresolved among acquisition gauge, carrier-bias,
  receiver/LNB, transmitter, and branch-assignment effects;
- a **50 or 75 ms qualification window is selected by the monitor**, not inferred as
  a transmitter cadence; and
- `modulo-π-qualified` describes a bounded receiver observable, not a satellite
  identity or a physical phase-reset event.

## What `modulo-π-qualified` means

The measured complex pilot-channel phase is modeled as

\[
z_m \approx a_m h_m \exp\{j[\phi(t_m)+\pi b_m]\}+\epsilon_m,
\qquad b_m\in\{0,1\}.
\]

The receiver cannot safely distinguish `φ` from `φ + π` in this observable. The
tracker therefore wraps its pre-update phase innovation into
`[-π/2, +π/2)`. A window is internally `modulo-π-qualified` when it has at least
20 supported frames, applies phase updates to at least 80% of them, and has
modulo-π innovation RMS no greater than 0.50 rad. The production segment is fully
`qualified` only after separate support coverage/gap, exact-versus-rolled-pilot,
local-line, interleaved-holdout, and local-versus-Kalman-rate gates also pass.

The π branch bit is analyzer bookkeeping. The data analyzed here do not determine
whether the ambiguity originates in a transmitted sign state, a pilot/channel
convention, or a receiver/estimator gauge. In particular, a branch transition is not
evidence that the spacecraft reset phase or hopped RF frequency.

### Error estimate for this section

The five-dwell raw-IQ audit reproduced all 216 sealed fully qualified windows. The
maximum absolute innovation-RMS reproduction error was
`2.22e-12 rad`; phase-update counts and Boolean lock results had zero disagreements.
That is numerical reproduction error only. Model-selection uncertainty is much
larger: the 216 raw ablations were selected by a modulo-π gate, a shorter angular
quotient naturally reduces wrapped RMS, and symmetry orders finer than π were not
tested. The result establishes operational consistency and reset avoidance, not an
unbiased Bayes factor proving that π is the unique physical symmetry.

## Five fresh dwells

All five inputs were rerun before the modulo-π audit. Candidate windows were fixed
from sealed track/probe geometry before the audit examined phase continuity.

| Dwell | Analyzed 75 ms windows | Inner modulo-π locks | Fully qualified | Descriptive 95% Wilson interval for full yield |
|---|---:|---:|---:|---:|
| `cap-20260821T201522-841b2a20e151` | 588 | 109 | 55 (9.4%) | 7.3%–12.0% |
| `cap-20260821T193701-87f96f47e73f` | 656 | 118 | 64 (9.8%) | 7.7%–12.3% |
| `cap-20260821T193440-17c2e0ebef6a` | 574 | 54 | 10 (1.7%) | 0.9%–3.2% |
| `cap-20260821T190912-ffd441556880` | 537 | 110 | 70 (13.0%) | 10.4%–16.1% |
| `cap-20260821T190701-7a5d980ec1c6` | 336 | 28 | 17 (5.1%) | 3.2%–8.0% |
| **Total** | **2,691** | **419** | **216 (8.0%)** | — |

In an explicit same-settings order-1/order-2 raw-IQ ablation, order 2 lowered
wrapped innovation RMS in 216/216 of these fully qualified windows. The five
post-hoc mechanism examples retained 260 exact-pilot-supported frames while the
matched 17-symbol-rolled pilot supported 0/260; the descriptive Wilson 95% upper
bound is 1.5%. Their direct line RMS was 12.3–27.6 Hz, interleaved holdout RMS was
12.6–28.2 Hz, and formal slope uncertainty was 77–174 Hz/s.

### Error estimate for this section

The per-window Wilson intervals are anti-conservative because windows in one track
and dwell share samples, hardware, and selection rules. The stronger replication
unit is the dwell: all five have nonzero fully qualified yield, but five is still a
small cohort. The five displayed examples are deliberately chosen for mechanism
clarity and cannot estimate prevalence. Rolled-pilot rejection is a useful matched
control, not a corpus-wide false-alarm calibration.

The complete per-window evidence is in the
[five-dwell modulo-π report](2026_08_23_five_dwell_modulo_pi_qualification.md) and
its [machine-readable result](figures/2026_08_23_five_dwell_modulo_pi_qualification/five-dwell-modulo-pi-results.json).

## What the 20 ms teeth mean

The full-capture diagnostic on `cap-20260821T140820-470384cc9284` scheduled a
fresh 20 ms GLRT acquisition every 10 ms. It completed 5,999 overlapping windows;
2,127 passed the declared GLRT margin and 1,258 of those also had within-window
line RMS at or below the report's 75 Hz display reference. Each tooth normally
contains 14–15 separately measured 750 Hz frames.

Therefore two statements can both be true:

- the CFO samples and smooth slope **inside** a supported tooth come from raw IQ and
  can be validated with an exact known pilot, rolled control, robust line, and held-out
  frames; and
- the fact that the plotted run stops after approximately 20 ms is imposed by the
  analysis window. The next probe starts a new independent acquisition and may choose a
  different timing/CFO basin or gauge.

The analyzer does not observe a continuous carrier, discover a transmitter boundary,
and then decide that it lasted 20 ms. It asks a predetermined 20 ms question repeatedly.
Consequently, the teeth are **not fake data**, but their boundaries cannot be used as
evidence of 20 ms Starlink frequency hopping.

The measured local slopes are also not one universal number. In the full-capture
diagnostic, the clean-window median was `-3.666 kHz/s`, the 10th–90th percentile was
`-4.829` to `-2.645 kHz/s`, and the robust population trend retained
`1.203 kHz/s` residual RMS. This spread is far larger than the tens-of-hertz local
line residuals in selected qualified examples.

### Error estimate for this section

The frame cadence gives approximately 1.33 ms sampling inside a tooth, but there is
no transmitter-boundary timing estimate: the start, duration, and stride are fixed by
the analyzer. Adjacent 10 ms-stride windows overlap and are not independent. Local
line residual and holdout error measure interpolation/prediction inside selected
support; they do not include errors from selecting a wrong acquisition basin or from
receiver/transmitter frequency bias between probes.

## What the 50–75 ms windows mean

The current dwell monitor lays out non-overlapping 75 ms windows from eligible
persisted source probes. Historical 80 ms scanner recordings use a 50 ms window; a
120 ms scanner frame uses 75 ms when placement permits. Those durations are declared
analysis horizons chosen to obtain enough 750 Hz frames while avoiding likely
reacquisition boundaries. A window qualifies only if its measurements pass the full
gate set.

The reports sometimes use “50–100 ms segment” descriptively because exploratory
windows and reset-delimited support had varying lengths. That phrasing must not be
read as a measured Starlink slot duration. The deployed contract uses explicit 50 or
75 ms analysis geometry, and the qualified phase span within a window may be shorter.

The evidence does support intermittent local smoothness: the five fresh dwells contain
216 fully qualified 75 ms windows, and their showcased held-out errors are 12.6–28.2
Hz. It does not support a physical RF hop at the next window boundary. A carrier-bias
change, independent acquisition gauge, receiver/LNB behavior, transmitted sign state,
or branch assignment can all change the receiver-relative estimate without an orbital
frequency discontinuity.

### Error estimate for this section

Window duration has no statistical uncertainty because it is a configuration choice.
Signal support within it is resolved at roughly 1.33 ms cadence and the production gap
gate is 4.1 ms. Conditional formal slope errors in the five examples are 77–174 Hz/s,
but the empirical local-rate spread between windows and dwells is the more honest
systematic bound. Selection, overlapping source evidence, uncalibrated receiver clocks,
and unknown transmitter bias dominate the formal fit error.

## Fresh 13-dwell linear-track population

Thirteen historical dwells were rerun and sealed at the same current Standard release.
Each fresh `standard.pilot-scan` V3 product was then reopened and refitted with
`polynomial_degrees=(1,)`. No persisted mixed-order family, de-aliased, replay, or final
membership was reused. The result contains 181 raw degree-1 tracks and 180 selected
pre-replay families.

This corrects a major interpretive risk in the older five-dwell TLE reports: all 15/15
formerly displayed top-three tracks and 47/61 formerly described post-replay tracks
had degree-2 or degree-3 membership. Those reports remain useful history for
candidate geometry and failure modes, but their membership is not strict-linear
association evidence.

The 37 tracks eligible for orbital testing last 6.95–31.83 s, contain 85–2,312
observations, and have degree-1 in-sample residual RMS of 427–1,358 Hz (median
967 Hz). Manifest channel/edge RF reconstruction agrees within 2 Hz for all tested
tracks.

### Error estimate for this section

The fresh refit removes polynomial-order contamination but is still conditioned on
the Standard pilot-scan candidate field and family-selection rules. Its 427–1,358 Hz
track residuals are empirical radio-model errors, not per-sample thermal uncertainties.
Tracks from one dwell are correlated. The refit is pre-replay, so “selected” must not
be interpreted as an independently replay-verified physical carrier.

The detailed cohort is in the
[fresh 13-dwell degree-1 report](2026_08_23_thirteen_dwell_degree1_fresh.md).

## Known-Starlink orbital association

For each of 37 eligible tracks, the first 60% chose a Starlink identity and nuisance
parameters; the final 40% was held out and scored once. The primary model permitted a
constant frequency offset, drift bounded to ±200 Hz/s, and epoch adjustment bounded to
±0.30 s. It was compared with a radio-only line, a free-affine orbit diagnostic,
wrong-time controls, adjacent causal TLE snapshots, shared-satellite and one-to-one
multi-track hypotheses.

| Association quantity | Fresh result |
|---|---:|
| Secure known-satellite associations | **0 / 37** |
| Median radio-only linear holdout RMS | 1,314 Hz |
| Median primary bounded-orbit holdout RMS | 6,059 Hz |
| Primary orbit beats linear | 1 / 37 tracks; 0 / 13 dwells |
| Primary orbit beats linear by at least 100 Hz | 1 / 37 |
| Primary orbit holdout RMS at most 500 Hz | 0 / 37 |
| Free-affine orbit beats linear | 16 / 37 tracks; 5 / 13 dwells |
| Wrong-time scalar-rate specificity passes | 3 / 37 |
| Identity stable across nuisance models | 6 / 37 |

The only primary-model near miss is a 7.175 s track in
`cap-20260821T193701-87f96f47e73f`, whose least-bad candidate is
STARLINK-3999 / NORAD 52704. It has 724 Hz held-out RMS versus 938 Hz for the line,
but its wrong-time empirical p-value is 0.634 and it misses the absolute 500 Hz gate.
It is a coincidence candidate, not an association.

### Error estimate for this section

- The secure yield is 0/37, with a descriptive Wilson 95% upper bound of 9.4%.
- Capture-time uncertainty changes raw predicted frequency by 637–1,188 Hz, but after
  removing the allowed offset/drift nuisance its shape effect is 0.53–29.70 Hz RMS.
- A ±50 m site perturbation changes affine-removed orbital shape by only
  0.02–0.81 Hz RMS.
- Adjacent causal TLE snapshots change affine-removed shape by 0–259 Hz RMS;
  33/37 winners pass the declared 100 Hz stability gate.
- TLE ages are 3.6–50.2 h, median 14.3 h.
- Zero of 37 path bindings declares a calibrated receiver frequency reference. The
  ±200 Hz/s nuisance bound is policy, not a measured oscillator limit.

The known timing/site/TLE shape terms are too small to explain the typical 6 kHz
primary orbital holdout error. The uncalibrated common frequency reference remains a
major unresolved systematic, but allowing a free affine drift removes the orbital
curvature needed for identity and makes selected identities unstable. The statistical
intervals do not correct for trying multiple tracks, satellites, nuisance models, or
report iterations and are not discovery p-values.

The complete result is in the
[fresh 13-dwell Starlink association audit](2026_08_23_thirteen_dwell_starlink_association_fresh.md).

## Hypothesis discrimination across 13 dwells

| Hypothesis | Prediction | Observed evidence | Disposition |
|---|---|---|---|
| The 20 ms teeth are transmitter slots | Boundaries should be inferred from signal changes | Starts, durations, and strides are scheduled analyzer geometry | Rejected as an inference from these plots |
| The 50/75 ms windows are transmitter slots | Qualification endpoints should be signal-defined | Window endpoints are configuration choices; gates decide only pass/fail inside them | Rejected as an inference |
| Exact-pilot response is accidental noise | Rolled and exact templates should behave similarly | 260 exact-supported showcase frames, 0/260 rolled | Disfavored for the five examples |
| Ordinary 2π tracking is sufficient | Explicit order 2 should not systematically improve continuity | 216/216 selected full windows have lower wrapped RMS and far fewer resets | Disfavored operationally; model-selection caveat remains |
| π-periodic phase is a useful local observable | Causal order-2 tracking should reproduce gates across dwells and agree with independent CFO lines | Reproduced in 5/5 dwells; local fit and holdout checks pass | Supported locally |
| π branch changes are physical phase resets | Branch count should have representation-independent event meaning | Branch index changes with the quotient representation and is not a qualification input | Unsupported |
| One independently chosen satellite explains each radio track | Bounded orbital curves should beat a line on held-out samples | Wins 1/37 tracks and 0/13 dwell aggregates | Strongly disfavored |
| One shared satellite explains a dwell's tracks | A common identity should reduce aggregate holdout error | Multi-kHz errors; no systematic improvement | Disfavored |
| Simultaneous tracks map one-to-one to different satellites | Assignment should improve aggregate prediction | No systematic held-out improvement | Disfavored |
| Scalar Doppler-rate proximity identifies a satellite | True-time match should be rare under wrong-time controls | Only 3/37 pass p≤0.05 | Insufficient for identity |
| Arbitrary clock/LNB drift plus an orbit identifies a satellite | Free-affine orbit should predict and preserve identity | Beats line in 5/13 dwells, but median is worse and identity is stable in only 6/37 tracks | Diagnostic only |

## Reconciliation of every committed report

The committed inventory contains 51 Markdown assets and 50 distinct contents:
`2026_08_21_five_dwell_degree1_only_rerun.md` and
`2026_08_21_tle_doppler_alignment.md` are byte-identical. A prior report formally
reviewed the 41 assets present at `eb9dfb4`; this audit checked that inventory against
current `main`, reviewed the ten subsequently added reports and the later amendment to
the edge-pilot phase report, and reconciled all claims with the fresh reruns above.

| Report group | Committed reports | Current disposition |
|---|---|---|
| Acquisition, CFO aliases, line finding, trajectory retention and replay | `2026_08_20_line_finder`; `2026_08_20_recent_cfo_alias_history`; `2026_08_21_405bcced8e67_track_loss`; `2026_08_21_470384_alias_offsets`; `2026_08_21_dense_independent_glrt`; `2026_08_21_e2ac389247f3_track_loss`; `2026_08_21_e7935fe8_recovery`; `2026_08_21_e975ebaac089_replay_investigation`; `2026_08_21_paired_hough_gallery`; `2026_08_21_seeded_alias_em_d6a`; `2026_08_21_t1_dense_degree1_only`; `2026_08_22_4e2a0c111a30_alias_aware_trajectory_accounting`; `2026_08_22_residual_hough_segmentation`; `2026_08_22_t1_glrt_search_parameter_study`; `2026_08_23_140820_glrt20ms_robust_slope`; `2026_08_23_cap_144200_missing_track_rca`; `2026_08_26_20ms_window_comparison`; `2026_08_26_cfo_alias_canonicalization` | Reusable evidence that exact-pilot-compatible candidates and coherent radio lines exist, plus documented alias/basin/selection failure modes. A line or replay tier is not a satellite. Strict degree-1 membership is taken only from the fresh refit. |
| Pilot phase, local CFO and PNT-like tracking | `2026_08_22_carrier_continuity_case`; `2026_08_22_edge_pilot_phase_slope`; `2026_08_22_frame_local_phase_qualification`; `2026_08_22_kalman_phase_tracking_comparison`; `2026_08_22_pilot_pnt_kalman`; `2026_08_22_pnt_kalman_comparison`; `2026_08_22_pnt_phase_doppler_comparison`; `2026_08_22_subsecond_pilot_structure`; `2026_08_22_within_segment_frame_phase`; `2026_08_23_glrt_phase_segment_comparison`; `2026_08_23_piecewise_pilot_doppler_rate` | Reusable for intermittent local known-pilot coherence and receiver-relative rate. The fresh five-dwell audit supplies the explicit order-1/order-2 ablation. Neither branch flips nor segment endpoints are physical event detections. |
| TLE and satellite-candidate reports | `2026_08_21_five_dwell_degree1_only_rerun`; `2026_08_21_five_dwell_tle_cone`; `2026_08_21_tle_doppler_alignment`; figure `README.md` | Candidate-only historical screens. Scalar-rate proximity and cone visibility are not identification. Mixed-order membership and absence of held-out orbital prediction are superseded by the fresh 13-dwell audits. |
| RF and oscillator interpretation | `2026_08_21_edge_pilot_if_dc_centering`; `2026_08_22_dual_lnb_drift_reference` | RF/IF arithmetic is reusable. Absolute frequency/rate remains limited by uncalibrated per-path receiver/LNB reference and unknown physical LNB mapping. |
| Scanner and long-monitor science | `2026_08_21_scanner_burst_duty_cycle`; `2026_08_23_eight_hour_dwell_scanner_science_agent`; `2026_08_23_scanner_standard_analysis`; `2026_08_23_six_hour_live_dwell_scanner_monitor` | Supports intermittent yield, retune boundaries, and local 50/75 ms monitor behavior. Scanner frames cannot establish cross-retune phase or a multi-second orbit. |
| Operations, UI, deployment and infrastructure | `2026_08_21_capture_pause_start_ui`; `2026_08_21_dead_code_and_obsolete_infrastructure_audit`; `2026_08_21_durable_acquisition_queue`; `2026_08_21_fast_test_and_deploy_plan`; `2026_08_21_http_matplotlib_png_rendering`; `2026_08_22_t1_glrt_hardware_aligned_parameter_study`; `2026_08_22_t2_coarse_acquisition_batch_prototype`; `2026_08_22_t3_glrt_hardware_execution_alignment`; `2026_08_23_eight_hour_dwell_scanner_operational_agent` | Reviewed for lineage, runtime, failure, and product-boundary effects. These reports do not add independent RF or satellite evidence. |
| Rendered scanner samples | the three Markdown files under `reports/scanner-rendered-samples/` | Presentation snapshots only; no quantitative association claim imported. |

### Important corrections and supersessions

1. The current `tools/report_pilot_pnt_kalman.py` labels one comparison
   “ordinary 2π” while constructing the current default
   `phase_symmetry_order=2`. A new run of that helper is not a valid order-1
   ablation. The fresh modulo-π report uses explicit order 1 and order 2.
2. The older five-dwell degree-1/TLE documents imported mixed-order family and replay
   membership. Their descriptive sky and scalar-rate tables remain historical, but the
   fresh degree-1 cohort supersedes them for association.
3. The original piecewise report's statement that the rise inside a tooth is real is
   compatible with the later full-capture diagnosis: sample values inside the probe can
   be real while the 20 ms boundary is imposed by the probe.
4. The phrase “50–100 ms segment” in exploratory reports does not establish a physical
   cadence. The production dwell/scanner geometries are declared 75/50 ms windows.
5. The recurring ±227.273 kHz structure is a symbol-rate CFO alias and must not be
   counted as separate satellites without independent replay and canonical separation.

## Bottom line

The fresh evidence supports local, intermittent, exact-known-pilot carrier tracking
modulo π. It does not support a claim that Starlink changes frequency every 20–75 ms.
The teeth and segment boxes are measurement geometry; the receiver-relative values
inside qualified support are the observations. Across 13 freshly rerun dwells, those
radio tracks still cannot be uniquely correlated to known Starlink satellites. The
next decisive inputs are capture-bound timing and observer authority plus a calibrated
shared frequency reference, followed by the same predeclared held-out orbital test.
