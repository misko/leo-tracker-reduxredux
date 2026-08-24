# Research evidence ledger

## Motivation

LEO Tracker needs a durable answer to two different questions: “what did a
particular investigation observe?” and “what is the project currently willing
to claim?” Dated reports preserve the first; this ledger maintains the second
without rewriting research history.

## Problem

The repository's reports span acquisition diagnostics, detector ablations,
trajectory failures, phase models, orbital controls, scanner work, UI changes,
and deployment receipts. Some reports are current support, some are the reason
the code changed, and some used recordings or assumptions later superseded.
Chronology alone does not tell a reader which conclusion still governs.

## Solution

This page maps each current scientific claim to its strongest versioned
evidence, controls, caveats, implementation status, and next falsifier. It also
indexes every one of the 45 versioned Markdown assets under `reports/` by role.
Canonical concept and pipeline pages link here for provenance; reports remain
dated, immutable receipts.

## Method

The ledger was assembled by reading all 41 top-level versioned reports, three
versioned scanner-rendered samples, the TLE figure README, their figures and
machine-readable results, current analysis/pipeline/application code, tests,
contracts, and the Qin and Kozhaya primary signal-structure papers. Four local,
unversioned draft reports were also reviewed but are explicitly excluded from
published authority below. The latest report is not automatically preferred:
input integrity, controls, independence, replication, and deployed contract
status determine weight.

## Status vocabulary

| Status | Meaning |
|---|---|
| **Established** | Repeated, controlled evidence supports the bounded claim |
| **Supported** | Evidence is substantial but an important independent gate remains |
| **Intermittent** | The effect is real in qualified intervals but not reliably available |
| **Operational** | Implemented and verified as a workflow, not a scientific discovery |
| **Hypothesis-generating** | Useful result whose input or evaluation does not support present authority alone |
| **Not established** | The repository must not make the claim |

“Deployed” and “established” are orthogonal. An estimator can be deployed as a
shadow product while its physical interpretation remains candidate-only.

## Current claim matrix

| Claim | Status | Strongest current evidence | Controls and caveats | Implementation |
|---|---|---|---|---|
| Exact Qin edge-pilot structure is present in recorded IQ | **Established** | [20 ms comparison](../../reports/2026_08_26_20ms_window_comparison.md), [edge-pilot phase-slope replication](../../reports/2026_08_22_edge_pilot_phase_slope.md), [scanner Standard analysis](../../reports/2026_08_23_scanner_standard_analysis.md) | Exact template repeatedly beats the 17-symbol roll; known pilot does not identify payload or spacecraft | Standard and scanner acquisition/QAM paths |
| The 300 × 8 published pilot matrix demodulates as useful 4QAM | **Established, candidate-only** | [20 ms comparison](../../reports/2026_08_26_20ms_window_comparison.md) | Accuracy applies only to known pilot states; no user/header bits are decoded | Pilot scan and report tools |
| Independent probes contain coherent CFO-time structure | **Established** | [dense independent GLRT](../../reports/2026_08_21_dense_independent_glrt.md), [residual-Hough segmentation](../../reports/2026_08_22_residual_hough_segmentation.md), [alias canonicalization](../../reports/2026_08_26_cfo_alias_canonicalization.md) | Receiver/LNB/transmitter terms remain mixed with propagation Doppler | Standard trajectory products |
| Parallel raw CFO ridges can be one symbol-rate alias family | **Established** | [alias canonicalization](../../reports/2026_08_26_cfo_alias_canonicalization.md) | 235/236 high-gate points collapse to one quadratic; grouping does not select the correction lift | Alias map + de-aliased bank |
| Same-IQ replay is required to choose the absolute correction lift | **Established** | [alias canonicalization](../../reports/2026_08_26_cfo_alias_canonicalization.md), [trajectory accounting](../../reports/2026_08_22_4e2a0c111a30_alias_aware_trajectory_accounting.md) | Upper lift: 400/401 positives; lower representative: 1/401 in the canonicalization case | CFO-lift replay v4 + final bank |
| Frame-local pilot phase can be coherent modulo π | **Established intermittently** | [frame-local qualification](../../reports/2026_08_22_frame_local_phase_qualification.md), [edge-pilot phase slope](../../reports/2026_08_22_edge_pilot_phase_slope.md), [pilot PNT Kalman](../../reports/2026_08_22_pilot_pnt_kalman.md) | One 80 ms case improves 1.695→0.151 rad; only 3/40 additional selected windows fully lock | Local pilot-Doppler monitor |
| A local CFO/rate model predicts better than the frozen multi-second derivative | **Supported** | [sub-second structure](../../reports/2026_08_22_subsecond_pilot_structure.md), [piecewise pilot Doppler](../../reports/2026_08_23_piecewise_pilot_doppler_rate.md) | Local 10 ms held-out RMS 16.48 Hz near 16.16 Hz measurement uncertainty; carrier-bias steps remain unexplained | Additive 75 ms Standard product |
| Current final banks are deployed multi-target associations | **Not established** | Current `run_receiver_standard` call graph | Multi-target code and tests exist, but the runner does not invoke it | Final bank remains residual-Hough/dealias/replay selection |
| A radio track is securely associated with one catalogued satellite | **Not established** | [deep three-dwell tracking review](../../reports/2026_08_24_recent_three_starlink_tracking_deep_review.md), [five-dwell TLE cone](../../reports/2026_08_21_five_dwell_tle_cone.md) | The latest full-search audit has zero secure named associations; true-time orbit/line wins are common in matched wrong-time fields and no candidate clears the runner/family gates | Research-only sky comparison primitives |
| Timing estimate is code phase, pseudorange, or absolute range | **Not established** | Phase/PNT report family and contracts | Current timing is receiver-relative and modulo a frame/sample coordinate; no transmit-time authority | No qualified navigation observable |
| Starlink payload is decoded | **Not established** | Code and product inventory | Only published known pilot symbols are evaluated | No payload decoder |
| Scanner captures support retune-bounded known-pilot/local-rate evidence | **Operational and supported** | [scanner Standard analysis](../../reports/2026_08_23_scanner_standard_analysis.md) | No state crosses a retune; five stored scans had 3/32 qualified segments and zero negative-control locks | Capture-first scanner pipeline |

## Evidence synthesis by topic

### Waveform specificity and acquisition geometry

Independent acquisition was the decisive methodological improvement. Earlier
shared or guided seeds could create one-second blocks that looked like carrier
continuity. The current detector searches every probe over the full configured
CFO interval, retains ranked basins, and evaluates exact and rolled templates
on the same samples.

Across the six trial-132 geometries, the best QAM median remains strong while
track-family retention changes non-monotonically with probe count and duration.
Standard's 2 × 20 ms schedule and Research's 3 × 20 ms schedule are therefore
resource/evidence policies, not waveform constants.

![Real-data QAM comparison across six independent probe schedules](../../reports/figures/2026_08_26_20ms_window_comparison/qam-comparison.png)

### Alias geometry and selection

The symbol-rate ambiguity is `1 / 4.4 µs = 227,272.727… Hz`; it is not the
234.375 kHz OFDM subcarrier spacing. Raw values, modulo-alias family identity,
and IQ correction lift are separate persisted facts. Residual-Hough is useful
for bounded association, but its outputs require replay accounting because a
conditioned hypothesis can recover, lose, or duplicate independently acquired
evidence.

![Recorded transition accounting for conditioned replay](../../reports/figures/2026_08_22_4e2a0c111a30_alias_aware_trajectory_accounting/trajectory-conditioned-transition-accounting.png)

### Phase, timing, and local rate

Complete-frame pilot observations sometimes cluster into two phase families
separated by π. A modulo-π model can support efficient coherent stacking and a
causal local rate, but coverage is intermittent and bias changes occur between
adjacent segments. The phase state is reset at failed gates and capture
discontinuities; it is never bridged by interpolation merely to draw a smooth
line.

![Recorded complete-frame phase and CFO structure](../../reports/figures/2026_08_22_subsecond_pilot_structure/subsecond-pilot-structure.png)

### Orbital association

Radio trajectories are repeatable, but constant rate alone is not a secure
orbital fingerprint. The causal five-dwell analysis allowed comparable nuisance
terms for true-time and wrong-time TLE controls and found no true-time advantage.
Observer coordinate, LO arithmetic, and measured two-LNB drift checks did not
explain the full rate discrepancy. Transmitter/beam steering, catalog
incompleteness, timing uncertainty, and signal-model error remain live.

![Five-dwell true-time and wrong-time TLE controls](../../reports/figures/2026_08_21_five_dwell_tle_cone/five-dwell-linear-rate-null-summary.png)

## Versioned report index

The index assigns each report a present role. “Supporting” means it contributes
evidence or design context; it does not mean every historical conclusion is
still current.

### Acquisition, detector, and performance studies

- [Line-finder study](../../reports/2026_08_20_line_finder.md) — early
  trajectory-loss localization; supporting history.
- [Recent CFO alias history](../../reports/2026_08_20_recent_cfo_alias_history.md)
  — historical cross-dwell alias survey.
- [Dense independent GLRT](../../reports/2026_08_21_dense_independent_glrt.md) —
  current methodological support for independent per-probe acquisition.
- [Edge-pilot IF/DC centering](../../reports/2026_08_21_edge_pilot_if_dc_centering.md)
  — current RF/IF arithmetic reference.
- [Scanner burst duty cycle](../../reports/2026_08_21_scanner_burst_duty_cycle.md)
  — scanner acquisition geometry and timing support.
- [T1 dense degree-one-only](../../reports/2026_08_21_t1_dense_degree1_only.md)
  — dense-search trajectory study with permutation control.
- [T1 GLRT search parameter study](../../reports/2026_08_22_t1_glrt_search_parameter_study.md)
  — cost/recovery frontier and rank sensitivity.
- [T1 hardware-aligned parameter study](../../reports/2026_08_22_t1_glrt_hardware_aligned_parameter_study.md)
  — host-aligned execution comparison.
- [T2 coarse-acquisition batch prototype](../../reports/2026_08_22_t2_coarse_acquisition_batch_prototype.md)
  — prototype performance evidence, not a production dependency.
- [T3 GLRT hardware execution alignment](../../reports/2026_08_22_t3_glrt_hardware_execution_alignment.md)
  — execution-alignment benchmark evidence.
- [20 ms window comparison](../../reports/2026_08_26_20ms_window_comparison.md)
  — current probe-geometry and QAM synthesis.

### Trajectory, alias, replay, and retention investigations

- [405bcced track loss](../../reports/2026_08_21_405bcced8e67_track_loss.md) —
  historical retention failure and policy before/after.
- [470384 alias offsets](../../reports/2026_08_21_470384_alias_offsets.md) —
  alias-decision diagnostics and geometry audit.
- [e2ac389 track loss](../../reports/2026_08_21_e2ac389247f3_track_loss.md) —
  replay-gate loss investigation.
- [e7935fe recovery](../../reports/2026_08_21_e7935fe8_recovery.md) — bounded
  recovery case.
- [e975 replay investigation](../../reports/2026_08_21_e975ebaac089_replay_investigation.md)
  — paired replay funnel and loss accounting.
- [Paired Hough gallery](../../reports/2026_08_21_paired_hough_gallery.md) —
  cross-path visual evidence; supporting rather than identity proof.
- [Seeded alias EM d6a](../../reports/2026_08_21_seeded_alias_em_d6a.md) —
  historical de-alias comparison; the current deployed path uses Huber linear
  refinement plus lift replay.
- [Alias-aware trajectory accounting](../../reports/2026_08_22_4e2a0c111a30_alias_aware_trajectory_accounting.md)
  — current transition-accounting support.
- [Carrier continuity case](../../reports/2026_08_22_carrier_continuity_case.md)
  — bounded continuity and refill/shard audit.
- [Residual-Hough segmentation](../../reports/2026_08_22_residual_hough_segmentation.md)
  — current segmentation-method evidence.
- [CFO alias canonicalization](../../reports/2026_08_26_cfo_alias_canonicalization.md)
  — current canonical-family and correction-lift synthesis.

### Phase, timing, Kalman, and local Doppler investigations

- [Edge-pilot phase slope](../../reports/2026_08_22_edge_pilot_phase_slope.md) —
  current multi-dwell exact/control and intermittent modulo-π evidence.
- [Frame-local phase qualification](../../reports/2026_08_22_frame_local_phase_qualification.md)
  — verified local phase gate and held-out prediction.
- [Kalman phase tracking comparison](../../reports/2026_08_22_kalman_phase_tracking_comparison.md)
  — historical Standard Kalman comparison.
- [Pilot PNT Kalman](../../reports/2026_08_22_pilot_pnt_kalman.md) — five-state
  known-pilot experiment; timing remains receiver-relative.
- [PNT Kalman comparison](../../reports/2026_08_22_pnt_kalman_comparison.md) —
  phase reset and gate-sensitivity evidence.
- [CH2L scanner Kalman-rate diagnosis](../../reports/2026_08_24_scan_2b2a98cc_ch2l_kalman_rate_diagnosis.md)
  — single-scan supporting evidence that coherent 1.333 ms frame-CFO trends
  can disagree with an overconfident full phase-coupled endpoint state; the
  phase-disabled-after-initialization control remains closer to the robust
  75 ms slope.
- [PNT phase/Doppler comparison](../../reports/2026_08_22_pnt_phase_doppler_comparison.md)
  — short-coherence and rate comparison.
- [Sub-second pilot structure](../../reports/2026_08_22_subsecond_pilot_structure.md)
  — current structure-aware holdout evidence.
- [Within-segment frame phase](../../reports/2026_08_22_within_segment_frame_phase.md)
  — **hypothesis-generating** because the principal historical input was later
  found to contain a manifest-mismatching shard; use newer verified-IQ phase
  reports for current proof.
- [Piecewise pilot Doppler rate](../../reports/2026_08_23_piecewise_pilot_doppler_rate.md)
  — current deployed local-monitor evidence.

### TLE, calibration, and multi-dwell comparisons

- [TLE Doppler alignment](../../reports/2026_08_21_tle_doppler_alignment.md) —
  initial geometry/alignment study and candidate inventory.
- [Five-dwell degree-one-only rerun](../../reports/2026_08_21_five_dwell_degree1_only_rerun.md)
  — independently rerun radio-line distribution.
- [Five-dwell TLE cone](../../reports/2026_08_21_five_dwell_tle_cone.md) —
  current causal true-time/wrong-time control and no-identity conclusion.
- [Three continuity-v2 dwell TLE screen](../../reports/2026_08_24_recent_three_continuity_tle_matching.md)
  — reproducible original nine-track candidate screen; its interpretation is
  superseded by the deeper matched-search review below.
- [D2 `9981b9c27853` CFO curvature and causal TLE comparison](../../reports/2026_08_24_9981b9c27853_cubic_cfo_tle_comparison.md)
  — dense same-episode evidence that a cubic is the minimum adequate radio
  model and that candidate 67930 predicts a retrospective tail better than
  train-only polynomials; it has no matched catalogue/time-search null.
- [Deep three-dwell Starlink tracking review](../../reports/2026_08_24_recent_three_starlink_tracking_deep_review.md)
  — current synthesis: TLE-blind physical episodes, complete matched search,
  scanner reset/timing audit, candidate ledger, and zero secure identities.
- [Dual-LNB drift reference](../../reports/2026_08_22_dual_lnb_drift_reference.md)
  — hardware frequency-drift bound used as a nuisance check.

### Scanner, operations, browser, and delivery reports

- [Capture pause/start UI](../../reports/2026_08_21_capture_pause_start_ui.md) —
  operational control-surface receipt.
- [Dead-code and obsolete-infrastructure audit](../../reports/2026_08_21_dead_code_and_obsolete_infrastructure_audit.md)
  — architectural cleanup inventory.
- [Durable acquisition queue](../../reports/2026_08_21_durable_acquisition_queue.md)
  — durable scheduling/restart authority.
- [Fast test and deploy plan](../../reports/2026_08_21_fast_test_and_deploy_plan.md)
  — delivery plan; use current operations guides for procedures.
- [HTTP Matplotlib PNG rendering](../../reports/2026_08_21_http_matplotlib_png_rendering.md)
  — historical renderer design evidence; current API serves registered PNGs
  without recomputing science.
- [Scanner Standard analysis](../../reports/2026_08_23_scanner_standard_analysis.md)
  — current stored-sweep analysis and five-scan evaluation.

### Auxiliary versioned Markdown assets

- [TLE figure data README](../../reports/figures/2026_08_21_tle_doppler_alignment/README.md)
  — provenance for the TLE alignment figure bundle.
- [Scanner sample ee6a5829](../../reports/scanner-rendered-samples/20260821T103718Z_scan-ee6a5829b7054a1a.md),
  [sample eb189e76](../../reports/scanner-rendered-samples/20260821T121316Z_scan-eb189e7612af41d6.md), and
  [sample 8c903aa6](../../reports/scanner-rendered-samples/20260821T122805Z_scan-8c903aa6d2be496e.md)
  — concrete rendered scanner receipts, not population-level conclusions.

## Local drafts reviewed but excluded from authority

At the time of this synthesis, the working tree also contained four unversioned
draft reports:

- `2026_08_21_0b45a2531e70_basin_recovery.md`;
- `2026_08_21_replay_slope_distribution.md`;
- `2026_08_22_multi_dwell_starlink_association.md`; and
- `2026_08_22_thirteen_dwell_degree1_rerun.md`.

They were read for consistency and helped identify open questions, but this
documentation change does not stage or modify them. Their stronger basin,
replay-slope, and multi-dwell association interpretations are not cited as
durable project authority until their authors choose to version them with
reviewed inputs, controls, tools, and tests.

## Known unknowns and next falsifiers

| Unknown | Evidence that would materially change the ledger |
|---|---|
| What causes segment carrier-bias steps? | Independent paths/dwells showing a repeatable model that predicts held-out steps and beats clock/LNB/discontinuity controls |
| Can phase lock become common? | Higher coverage across independent verified dwells with unchanged rolled-control rejection and held-out prediction |
| How many physical emitters are present? | Deployed multi-target association with crossing/birth/death controls, duplicate suppression, replay support, and cross-path consistency |
| Which satellite emitted a carrier? | True-time orbital curve-shape advantage over wrong-time/wrong-satellite controls, robust to timing and frequency nuisance models |
| Is timing navigationally useful? | Calibrated transmit-time authority and qualified absolute observable, not only receiver-relative fractional timing |
| Is unknown payload recoverable? | A separately reviewed decoder with legal/ethical scope, independent validation, and no misuse of known-pilot accuracy as payload accuracy |

## Maintenance

When a new report lands, add it to the index and update the claim matrix only
if its evidence changes the current synthesis. Record input-integrity
dispositions explicitly. A canonical claim should link to the smallest set of
strong sources that establishes it; the index preserves the full research
trail. Follow the [Research pipeline](../pipelines/research-analysis.md) for
experiment design and the [documentation standard](../contributing/documentation.md)
for report and figure conventions.
