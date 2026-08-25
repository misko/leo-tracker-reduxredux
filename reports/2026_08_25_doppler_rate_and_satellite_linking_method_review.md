# Refill-aware review of Doppler-rate estimation and satellite linking

Date: 2026-08-25

Repository baseline reviewed: `b25443f00c7816c9fa1626175e3383adb8d7d6c8`

Status: research synthesis; no estimator or named-satellite promotion

## Executive conclusion

The repository now contains three scientifically different generations of
evidence, and they must not be pooled without labels:

1. **PRE-FIX legacy recordings** lack authoritative device-sample counters.
   Most Aug-21 long-duration slopes are biased by omitted RF time at Pluto
   application-refill handoffs. Their within-refill frame measurements remain
   useful, but their stored-time multi-second slopes are quarantined.
2. **POST-FIX counter-authoritative recordings** carry device counters, account
   for the full device span, and have no missing-sample or continuity events.
   These are the appropriate data for Doppler-rate and orbit-shape work.
3. **MIXED studies** combine both generations and therefore require stratified
   interpretation.

On POST-FIX data, the best presently supported Doppler-rate direction is a
**source-bound, causal robust line over roughly 500 ms of qualified 1.333 ms
frame-CFO measurements**. Those measurements are independent of the downstream
rate fit but are conditioned on a frozen Standard source, epoch, and alias. The
line substantially improves future CFO prediction over 125 ms history in every
development dwell and in the one fully evaluable fresh holdout dwell. The
planned promotion cohort was not operationally complete, so this is a strong
direction rather than a promoted estimator. The two long, clean POST-FIX arcs
tested also require **low-order curvature**: quadratic and sometimes cubic CFO
models greatly outperform a single line. The practical next model is therefore
a lean CFO/rate/acceleration state with conservative change detection,
benchmarked against the fixed 500 ms line.

No real-IQ experiment in this repository has a known physical Doppler-rate
truth. A difference between two estimators, a TLE curve, or two receiver paths
is a **rate disagreement**, not a truth error. Likewise, held-out CFO RMS is a
frequency-prediction error in hertz, not a rate error in hertz per second. Only
the synthetic rows below have genuine known-truth rate error.

For satellite linking, the data now strongly support three increasingly narrow
claims:

- the RF structures are real and repeat across receiver paths;
- many tracks have satellite-like orbital curvature;
- **no tested method has securely identified a NORAD object**.

The strongest conditional single-arc candidate is STARLINK-31640 / NORAD 59748
on the counter-continuous `150802` dwell, but its fitted time shift is unstable,
a wider time search changes the winner, and the dual-receiver common-orbit fit
loses to an alternative satellite and to a simpler shared-curvature null.

## 1. Provenance and terminology

### 1.1 Refill-era classification

Classification is based on the capture contract, not the report date.

| Label | Required evidence | Scientific use |
|---|---|---|
| **PRE-FIX affected** | Legacy/counterless recording plus a demonstrated refill-compression signature | Local, within-continuity measurements only; quarantine stored-time long slopes |
| **PRE-FIX unverified** | Legacy/counterless recording without a demonstrated bias in the selected interval | Useful control or local evidence, but not proof of repaired continuity |
| **POST-FIX** | Manifest V2/device counters; `sample_loss_observable=true`; observed samples equal device span; one continuity segment; zero gap, missing, overflow, and enqueue loss | Authoritative elapsed-RF-time analysis |
| **SCANNER SEGMENT** | Counter-authoritative only within a returned target segment | Valid inside the target; continuity across retunes is not available |
| **MIXED** | Study contains PRE-FIX and POST-FIX captures | Report strata separately; do not pool as exchangeable data |
| **SYNTHETIC** | Injected waveform with known coefficients | Genuine estimator truth error, subject to simulation realism |

The refill mechanism is established in the
[refill time-compression report](2026_08_24_refill_time_compression_sawtooth.md):
262,144 samples correspond to 104.8576 ms, 383 of 391 large CFO cuts bracket a
refill, and only three preserve the expected timing. The first completed
60-second POST-FIX Standard dwells were
`cap-20260824T192019-9023840c8e9f`,
`cap-20260824T192252-9981b9c27853`, and
`cap-20260824T192531-491832825b97`, as documented in the
[recent-three continuity report](2026_08_24_recent_three_continuity_tle_matching.md).

**Important:** PRE-FIX does not mean every sample is unusable. Short fits that
remain inside one continuous refill interval can still measure receiver-CFO
locally. It means that elapsed time across refills is not authoritative.

### 1.2 What the error columns mean

| Quantity | Unit | Meaning |
|---|---:|---|
| Estimated rate | Hz/s | Slope or instantaneous derivative of a chosen receiver-CFO model |
| Rate disagreement | Hz/s | Difference between two estimators or between an estimator and a candidate TLE; **not truth error** |
| Held-out/future CFO RMS | Hz | Frequency prediction error on observations excluded from the current update or fit |
| Conditional slope SE/CI | Hz/s | Regression uncertainty conditional on membership, masks, model, and noise assumptions |
| Rate MAD or block spread | Hz/s | Dispersion/stability diagnostic, not calibrated uncertainty |
| Synthetic truth error | Hz/s | Estimate minus a known injected coefficient; the only literal rate-error metric here |

The frequency chain still includes satellite motion, transmitter carrier
behavior, receiver/sample clock behavior, and LNB/LO drift. This report follows
the requested scope: estimate receiver-CFO rate well first, while treating the
clock/LNB decomposition as a related but separate calibration problem. The
[dual-LNB drift study](2026_08_22_dual_lnb_drift_reference.md) did not establish
a stable correction: the conducted estimates were unresolved at 2 sigma and a
nearby 60-second run showed nonstationary wander.

Here, **causal** means that the rate prediction uses only prior frame-CFO rows
after the source, epoch, and alias have been frozen. The complete pipeline is
conditional on that upstream Standard selection, which can use both Qin
parities and wider source context; an odd-Qin score is therefore locally
fit-withheld, not an end-to-end untouched observation.

## 2. Doppler-rate estimators tried

### 2.1 PRE-FIX long-slope retrospective

All T01-T10 recordings below are Aug-21 PRE-FIX captures. T01-T05 and
T07-T10 exhibit the known refill-compression mechanism. T06 is a useful
near-real-time legacy control, but it still lacks authoritative device counters
and is therefore not POST-FIX evidence.

| Dwell | Sealed stored-time GLRT | Reset-local frame rate | Local - GLRT | Held-out odd-Qin CFO RMS, GLRT -> local |
|---|---:|---:|---:|---:|
| T01 | -6.171 kHz/s | -3.842 kHz/s | +2.329 kHz/s | 71.8 -> 35.2 Hz |
| T02 | -5.498 | -3.231 | +2.267 | 61.1 -> 26.6 |
| T03 | -5.223 | -3.376 | +1.846 | 64.9 -> 49.9 |
| T04 | -5.743 | -3.362 | +2.380 | 70.4 -> 31.0 |
| T05 | -4.964 | -3.196 | +1.768 | 46.4 -> 27.1 |
| T06 | -3.473 | -3.470 | +0.003 | 27.1 -> 27.1 |
| T07 | -6.019 | -4.028 | +1.991 | 59.0 -> 33.5 |
| T08 | -5.586 | -3.772 | +1.814 | 59.4 -> 30.7 |
| T09 | -5.733 | -3.545 | +2.187 | 70.1 -> 49.2 |
| T10 | -4.298 | -3.040 | +1.258 | 57.0 -> 50.9 |
| **Aggregate** | **median -5.542** | **median -3.423** | **median +1.919** | **pooled 60.202 -> 33.996 Hz (-43.529%)** |

The reset-local method fits a shared robust slope while allowing an independent
intercept in each 20-125 ms ramp, using even Qin symbols for fitting and odd Qin
symbols for scoring. Whole-ramp bootstrap standard deviations range from 18 to
271 Hz/s. The dramatic improvement is strong evidence for the refill diagnosis,
not a ten-dwell validation on repaired recordings. See the
[ten-dwell raw Doppler report](2026_08_24_ten_dwell_raw_doppler_pipeline.md).

![PRE-FIX stored-time slopes close after refill-local correction](figures/2026_08_24_refill_time_compression_sawtooth/ten-dwell-rate-closure.png)

### 2.2 Complete rate-method matrix

The following tables place all material approaches on one scale. Ranges and
representative values are shown where a method produces many local rates.

#### PRE-FIX and continuity-unverified results

| Approach | Data / fitted parameters | Estimated rate or range | Comparator and rate disagreement | CFO prediction / residual error | Assessment |
|---|---|---:|---|---|---|
| Stored multi-second GLRT degree-1 line | T01-T10; one intercept and slope | Median -5.542 kHz/s | Reset-local median -3.423 kHz/s; +1.919 kHz/s correction | Odd RMS 60.202 -> 33.996 Hz after local correction | **Rejected for long PRE-FIX slopes**; local ramps remain useful ([report](2026_08_24_ten_dwell_raw_doppler_pipeline.md)) |
| Blind full-epoch raw-IQ cells | `470384`, 12 ms cells / 4 ms hop; local CFO and slope | Median local -3.656 kHz/s | Stored global -7.013 kHz/s; +3.357 kHz/s | Median local-line RMS 14.2 Hz versus 269.6 Hz global | Independent confirmation of refill mechanism, not truth ([report](2026_08_23_470384_blind_timing_cfo_comprehensive.md)) |
| Independent 20 ms GLRT-window slopes | `470384`; 1,258 clean windows | Population trend -3.706 kHz/s at 38.04 s; acceleration +23.4 Hz/s^2 | Hough long slope roughly -7.510 to -5.950 kHz/s | Rate-population residual RMS 1.203 kHz/s | Very short, noisy local rate population; diagnostic ([report](2026_08_23_140820_glrt20ms_robust_slope.md)) |
| Piecewise Standard frame-CFO line | `470384`; 21 qualified 50-75 ms segments; free intercept per segment | Median -3.769 kHz/s | Frozen -6.919 kHz/s; +3.150 kHz/s | Median line residual 13.20 Hz; conditional slope SE 124 Hz/s | Strong local estimator on legacy data ([report](2026_08_23_piecewise_pilot_doppler_rate.md)) |
| Five-dwell qualified frame-CFO | `470384`, T01, T06, T04, T03; free refill intercepts | -3.806 to -3.150 kHz/s, except `470384` -3.772 | Model disagreement -0.121 to +3.257 kHz/s | Odd RMS local/model: 19.1/63.7, 28.7/46.6, 112.1/111.9, 25.8/48.0, 48.9/62.3 Hz | Estimator gates largely work, but all data are PRE and retention gate failed two dwells ([report](2026_08_25_frame_cfo_dwell_prototype.md)) |
| Qualified per-frame CFO front ends | `470384`; discrete, parabolic, phase-refined, robust, and differential-phase frame estimates | Not a standalone rate fit | Not applicable | Even-to-odd RMS 32.5, 31.2, 31.3, 32.5, and 1,562.8 Hz | Establishes the ordinary profile-based CFO measurement; robust only helps under contamination and differential phase is rejected ([report](2026_08_24_frame_cfo_estimator_study.md)) |
| Modulo-pi phase-supported local slopes | Five Aug-21 dwells; phase plus CFO in selected arcs | Showcase -3.996 to -3.112 kHz/s | Direct line and phase generally within tens of Hz/s, with selected larger deviations | Held-out RMS 12.6-28.2 Hz; only selected arcs qualify | Phase can corroborate a rare local arc; not a primary rate observable ([report](2026_08_23_five_dwell_modulo_pi_qualification.md)) |
| Phase-first Kalman | Aug-22 legacy windows; phase, CFO, rate, fractional timing, timing rate | Examples -3.983 to -2.906 kHz/s | Frame-line disagreements from -599 to +292 Hz/s; only 3/40 extra-dwell locks | Ordinary phase tracker had 87.81% slips and 13.497 kHz/s median absolute disagreement | **Rejected** as a general estimator; phase feedback can bias rate ([PNT report](2026_08_22_pilot_pnt_kalman.md), [comparison](2026_08_22_kalman_phase_tracking_comparison.md)) |
| Alias-aware Hough / RANSAC / DP and residual changepoints | Legacy tracks; alias lifts, parent lines, piecewise Theil-Sen segments | Example parent -6.624 kHz/s split into -5.128, -5.662, -6.165, -5.953 | No authoritative post-fix comparator | Segment residual medians 41.6-122.3 Hz | Valuable acquisition/changepoint machinery, but rates use PRE-FIX stored time ([report](2026_08_22_residual_hough_segmentation.md)) |
| Alias-canonicalized polynomial trajectory | PRE-FIX trial 132; integer 227,272.727 Hz alias lifts plus one polynomial | Quadratic rate evolves -2.594 to -5.296 kHz/s over 10 s | No truth comparator | Held-out RMS line 1,254.9, quadratic 797.5, cubic 817.6 Hz | Alias grouping helps trajectory consistency; it is not post-fix rate validation ([report](2026_08_26_cfo_alias_canonicalization.md)) |

#### POST-FIX and scanner-segment results

| Approach | Data / fitted parameters | Estimated rate or range | Comparator and rate disagreement | Held-out / future CFO error | Assessment |
|---|---|---:|---|---|---|
| First-three continuity closure | First POST-FIX D1/D2/D3; accepted 75 ms local/modulo-pi segments | Median local -2.026, -3.808, -3.862 kHz/s | Frozen disagreements +127.9, -105.5, +31.2 Hz/s | Selection-conditional local evidence | Cleanest PRE/POST closure: disagreements contract from roughly +1.7 kHz/s historically, but still are not truth ([report](2026_08_24_recent_three_continuity_tle_matching.md)) |
| 125 ms frame maxima | Aug-25 D1/D2/D3; robust line over even-Qin 1.333 ms frames | Median 125 ms block rates -3.788, -3.655, -3.761 kHz/s | Recentered GLRT: -3.699, -3.614, -3.568; disagreements -88, -41, -193 Hz/s | Equal-dwell odd RMS **50.98 Hz**, versus GLRT 52.35 | Best of the tested 125 ms frame methods, but no truth ([report](2026_08_25_recent_frame_cfo_rate_prototype.md)) |
| Summed-profile / occupancy-mixture 125 ms fits | Same D1/D2/D3; joint profile or 20% outlier mixture | D3 -3.793 / -3.806 kHz/s; D1/D2 collapse to GLRT centers | D3 disagreement -225 / -237.5 Hz/s | Equal-dwell odd RMS 51.09 / 51.40 Hz | More likelihood structure did **not** beat simple frame maxima on strong data |
| Fixed 500 ms causal frame-CFO line | D1-D3 development; past even Qin predicts future odd Qin | Central rates remain near -3.71, -3.64, -3.63 kHz/s; paired 500-125 changes +6.8, +9.8, +108.2 Hz/s | 125 ms history is the operational comparator, not truth | Equal-dwell RMS 55.75 -> **41.06** at 125 ms, 141.37 -> **74.47** at 500 ms, 233.99 -> **98.28** at 1 s | **Strongest current direction**; improved every dwell/horizon ([tracking report](2026_08_25_recent_adaptive_cfo_tracking.md), [rate-change audit](2026_08_25_adaptive_cfo_rate_change.md)) |
| Current adaptive history selector | Same D1-D3; always choose longest compatible past window | Similar central rate family | Fixed 500 ms comparator | 69.01 / 172.60 / 368.30 Hz at 125/500/1,000 ms | **Rejected current rule**; worse than fixed 500 ms |
| Pre-registered H1-H7 holdout | Seven Aug-25 captures intended; fixed 125/500 and adaptive | Only H7 fully evaluable; fixed medians about -3.218 / -3.210 kHz/s, paired change -12.7 Hz/s | No truth comparator | H7 fixed RMS 103.15 -> 70.70, 276.31 -> 102.10, 558.06 -> 234.23 Hz | Encouraging H7, but **holdout is inconclusive** because only 6/21 cells were numeric ([preregistration](2026_08_25_recent_adaptive_cfo_holdout_preregistration.md), [outcome](2026_08_25_recent_adaptive_cfo_holdout.md), [rate-change audit](2026_08_25_adaptive_cfo_rate_change.md)) |
| Robust polynomial long-arc CFO | POST `9981`, 30 s; line through quintic | Cubic instantaneous rate -3.828 -> -2.855 kHz/s | Frame cubic differs +26, -17, +63 Hz/s at start/middle/end; candidate TLE rate RMS disagreement 13.36 Hz/s | Blocked RMS line 1,152.54, quadratic 163.44, cubic **63.50** Hz; 6 s cubic/quartic 104.23/109.65 | Strong evidence for low-order curvature; cubic minimum adequate on this arc ([report](2026_08_24_9981b9c27853_cubic_cfo_tle_comparison.md)) |
| Joint CFO cubic + template-delay quadratic | POST `150802`, 13.825 s; separate CFO and integer-epoch likelihoods | At reference: CFO rate -3.578078 kHz/s; acceleration -8.637 Hz/s^2; jerk +2.721 Hz/s^3 | Timing-equivalent -3.591771 kHz/s; 13.693 Hz/s same-convention disagreement | Held/rolling RMS line 95.94/112.33, quadratic 64.94/77.45, cubic **59.38/74.85** Hz | Useful curvature diagnostic; timing shares selection and clock/channel gauge, so not independent truth ([report](2026_08_25_joint_cfo_delay_acceleration_prototype.md)) |
| Continuous-recovery 2-state Kalman | POST D1/D2/D6 and long `150802`; CFO/rate state | Local track rates | Causal trailing-20 ms frame line | D1/D2/D6 pooled 46.944 vs line 46.482 Hz, wins 1/3; `150802` 50.401 vs 47.719, line wins 13/14 blocks | Frame recovery succeeds; current dynamics do **not** improve prediction ([report](2026_08_25_continuous_frame_recovery_prototype.md), [long arc](2026_08_25_counter_continuous_frame_timing_and_delay.md)) |
| Robust jump and phase-gated filters | Five POST fixed-design dwells; D4 non-estimable; four-dwell complete-case sensitivity | Central rates not published as a common truth table | Causal trailing-20 ms line | Common-mask RMS line 52.4, V2 131.0, robust jump 54.3, phase-jump 78.4 Hz | Primary five-dwell effect unavailable; in the post-observation complete-case sensitivity, jump rescues V2 but remains 3.2% worse than the simple line, and the phase gate worsens it ([report](2026_08_25_five_dwell_pilot_filter_prototypes.md)) |
| RX0/RX1 frame-CFO replay | POST `150802`; separate robust receiver-path lines | RX0 -3.589828 kHz/s; RX1 -3.578230; research RX0 -3.587933 | RX0-RX1 disagreement -9.703 Hz/s | RX0 fit 25.058 Hz; conditional future 27.874 Hz; pair-difference line RMS 69.009 Hz | Excellent same-emitter reproducibility, but paths share one Pluto clock/LO ([report](2026_08_25_rx0_cross_receiver_anchor_replay.md)) |
| Frequency/phase Kalman diagnosis | Counter-proven 120 ms scanner segment CH2L | Direct RX0/RX1 -3.560825/-3.742859 kHz/s; full-phase KF -2.869647/-2.637142 | Full-phase minus direct: +691/+1,106 Hz/s; phase-disabled much closer | Direct held-out RMS 19.064/27.063 Hz | Phase coupling is harmful and overconfident; use CFO-only ([report](2026_08_24_scan_2b2a98cc_ch2l_kalman_rate_diagnosis.md)) |
| PNT V3 | Mixed corpus plus POST `150802`; phase-safe five-state tracker | Arc-dependent | POST fixed-dwell one-step RMS beats line 4/4 modestly; selected `150802` arcs worsen median rate disagreement 138.2 -> 171.1 Hz/s, while the larger conditional cohort improves 599.2 -> 351.2 | POST fixed-dwell predictive geometric RMS ratio 0.9736; full-cohort `150802` tracked-CFO **local-line residual** 87.4 -> 15.0 Hz | Better frequency tracking, but rate bias remains unvalidated ([review](2026_08_25_pnt_kalman_v3_comprehensive_review.md), [`150802` selection](2026_08_25_150802_v3_tracking_comparison.md), [full dwell](2026_08_25_150802_v3_full_dwell.md)) |
| PNT V4 | POST `150802`; source-bound seeded acquisition, then unchanged V3 tracking | No new rate estimator; supplied rate only centers acquisition | Not applicable | 50 selected V3 losses recovered; 261 both complete, 5 V3-only, 221 neither | Acquisition/yield work only; **no V4 rate-accuracy result** ([report](2026_08_25_150802_pnt_kalman_v4_experimental.md)) |
| 24-hour cross-path repeatability | 89 POST captures / 178 streams | Normalized slope spreads: 11.10, 1.91, 10.77 Hz/s in three leading multi-path examples | Same-event cross-radio differences 0.133, 2.508, 5.291 Hz/s in `065355` | Not a held-out prediction metric | Strong reproducibility, but still no absolute Doppler truth ([retrospective](2026_08_25_post_refill_24h_retrospective/README.md)) |

![POST-FIX fixed-history versus adaptive future-CFO performance](figures/2026_08_25_recent_adaptive_cfo_track/comparison.png)

![POST-FIX long-arc rate and acceleration](figures/2026_08_24_9981b9c27853_cubic_cfo_tle_comparison/06_rate_and_acceleration.png)

#### MIXED and SYNTHETIC results

| Approach | Refill class | Estimated result | Error / disagreement | Assessment |
|---|---|---|---|---|
| PSS blockwise rate | MIXED: 11 Aug-25 POST plus 10 Aug-21 PRE | Rates in 10/21 dwells: nine POST and legacy T06 | POST-recent median absolute PSS-GLRT disagreement 1.694 kHz/s, RMS 2.881 kHz/s, sign 7/8; all ten 1.549/2.633 kHz/s; every 95% CI crosses zero | PSS is useful timing corroboration, not a quantitative rate estimator at 2.5 MS/s ([report](2026_08_25_multi_dwell_pss_sss_doppler.md)) |
| Independent SSS | MIXED | 3/60 recent blocks and no dwell rate in 21 | No rate estimate | Rejected at current sample rate |
| PSS-timed SSS | MIXED; conditional on PSS timing | Ten rate fits | Median absolute disagreement 46.9 kHz/s; RMS 64.9 kHz/s; sign 4/10 | Not independent and unusable quantitatively |
| V2 aggregate | MIXED: eight PRE plus four POST estimable dwells | Internal CFO/rate state; no pooled known-truth rate result | One-step CFO prediction loses 12/12 to the causal trailing-20 ms frame line | Rejected for CFO prediction; does not directly quantify rate error ([V3 review](2026_08_25_pnt_kalman_v3_comprehensive_review.md)) |
| Raw-waveform frame phase/CFO injection | SYNTHETIC | Truth -1,800 Hz/s; frame-CFO -1,799.928; phase -1,799.990 | **Truth errors +0.072 and +0.010 Hz/s** | Clean component qualification only ([report](2026_08_25_frame_phase_rate_investigation.md)) |
| Joint polynomial injection | SYNTHETIC | Truth -3,550 Hz/s; estimate -3,548.8755 | **Truth error +1.1245 Hz/s**; acceleration error -0.2825, jerk error -0.2186 in their respective units | Useful arithmetic test; not yet injected into real POST backgrounds ([joint report](2026_08_25_joint_cfo_delay_acceleration_prototype.md)) |

### 2.3 What worked, what failed, and what remains untried

| Category | Tried result | Current decision |
|---|---|---|
| Qualified frame-CFO with free local intercepts | Repeatedly removed PRE refill artifacts and predicts held-out frame CFO | Keep as the primary measurement family |
| Fixed 500 ms robust history | Large future-CFO gains on D1-D3 and the evaluable H7 holdout | Highest-priority estimator candidate; requires a feasible untouched POST cohort |
| Low-order long-arc curvature | Quadratic/cubic strongly beat one line on `9981` and `150802` | Add acceleration only when rolling/blocked validation supports it |
| CFO-only state estimation | Phase-disabled paths are substantially safer | Continue; calibrate process noise and innovation statistics against fixed 500 ms |
| Adaptive history | Current longest-compatible rule is worse | Reject current policy; redesign with sustained past-only evidence and hysteresis |
| Summed profile / occupancy mixture | No improvement over frame maxima on strong D1-D3 | Do not default-enable; consider only behind a frozen weak-frame gate |
| Phase feedback | Sparse locks, slips, biased rate, and overconfident covariance | Keep phase diagnostic and decoupled from CFO/rate |
| PSS / SSS rate | PSS uncertain and SSS effectively absent | Keep PSS for timing only; stop quantitative rate work at 2.5 MS/s |
| V4 | Improves acquisition availability | Benchmark downstream rate separately; completion counts are not rate accuracy |
| Higher digital sample rate | 3 MS/s is capture-qualified but `CAPTURE_ONLY`; 5 MS/s first live dwell is fragmented | Scientific rate/curvature comparison is **not yet tried** ([deployment report](2026_08_25_3m_5m_production_capture_deployment.md)) |

The highest-value untried rate experiment is a **known polynomial-phase signal
injected into real, counter-authoritative POST backgrounds**, spanning SNR,
occupancy, rate, acceleration, jerk, alias changes, discontinuities, and sample
clock offsets. That would finally produce rate bias, RMSE, and interval coverage
against truth rather than against another receiver-CFO estimator.

The highest-value real-data promotion experiment is a fresh, source-bound
cohort of at least ten POST captures, selected from actually supported episodes
rather than arbitrary wall-clock tiles. Compare, on identical causal masks:

1. fixed 125 ms robust frame line;
2. fixed 500 ms robust frame line;
3. a lean CFO/rate/acceleration state;
4. the existing causal trailing-20 ms line;
5. V3/V4 downstream tracking after identical acquisition.

Predeclare block-first future-CFO RMS, rate stability, support, innovation/NIS,
and change-point behavior. Treat physical clock/LNB calibration as a separate
campaign rather than absorbing it into the estimator score.

## 3. Satellite-linking approaches

### 3.1 What “success” means

The repository has sometimes used “match” for four different achievements.
They should be kept separate:

1. **RF presence:** a repeatable coherent signal exists.
2. **Same-emitter linkage:** multiple paths or fragments carry the same local
   frame-bearing signal.
3. **Orbital-shape evidence:** a TLE family predicts held-out CFO shape better
   than a fair radio-only null.
4. **Named identity:** one NORAD object survives runner separation, epoch/time
   sensitivity, family-wise controls, and independent replication.

Current evidence strongly supports (1), often supports (2), gives population
evidence for (3), and has achieved **zero** secure cases of (4).

### 3.2 Method comparison

| Method | Refill class | Observable and fitted parameters | Best reported outcome | Specificity/control result | Overall verdict |
|---|---|---|---|---|---|
| Five-dwell scalar Doppler-rate cone | PRE-FIX | One radio slope compared with visible-TLE scalar slopes; frequency offset irrelevant | Multiple plausible candidates per dwell | Median nearest true-time discrepancy 1.387 kHz/s versus wrong-time 1.333 kHz/s | Superseded for identity and long-rate truth ([report](2026_08_21_five_dwell_tle_cone.md)) |
| Thirteen-dwell fresh association | PRE-FIX | Identity, constant offset, bounded drift, and time shift | Some visually plausible curves | Orbit holdout 6,059 Hz versus radio line 1,314 Hz; orbit wins 1/37; no IDs | Rejected; nuisance fit and legacy timing do not identify a satellite ([report](2026_08_23_thirteen_dwell_starlink_association_fresh.md)) |
| Recent-three matched orbital shape | POST-FIX | Candidate TLE plus offset/time alignment against seven clusters; held-out orbit versus radio polynomial and wrong-time null | Orbit beats line in 6/7 deep-search clusters | Equal-dwell matched rank 10/41 (p=.244); no runner margin >=100 Hz; no IDs | Satellite-like shape, insufficient specificity ([continuity report](2026_08_24_recent_three_continuity_tle_matching.md), [superseding deep review](2026_08_24_recent_three_starlink_tracking_deep_review.md)) |
| `9981` 30-second curved-CFO/TLE comparison | POST-FIX | Robust radio polynomial; candidate identity, constant offset, bounded nuisance drift, and bounded epoch shift | Candidate 67930 derivative agrees with radio cubic at 13.36 Hz/s RMS | Time/identity remains conditional; not a secure association | Strong orbit-like curvature, candidate only ([report](2026_08_24_9981b9c27853_cubic_cfo_tle_comparison.md)) |
| Last-ten population matched field | POST-FIX (hash-cited external audit) | Per-cluster orbital curve versus radio polynomial over wider +/-2 s epoch search | Orbit beats line in 22/26 clusters; equal-dwell matched rank 1/41 (raw p=.02439) | 17/29 epoch fits hit a boundary; minimum named FWER .48780; no catalogue recurrence | Best population-level orbital-shape evidence, **zero named IDs** ([synthesis](2026_08_25_satellite_identity_recovery_v2.md)) |
| `150802` all-visible single-receiver TLE fit | POST-FIX | 550 direct-CFO rows; all horizon-visible Starlinks; `y=D_j(t+tau)+b` | NORAD 59748: fixed-tau held-out RMS 54.45 Hz; fitted-tau bidirectional 68.36 Hz; runner 445.52 Hz | Directional tau diverges; fixing tau improves holdout; +/-30 s changes winner to 58219 | Strong conditional candidate, no identity ([report](2026_08_25_150802_visible_starlink_tle_fit.md)) |
| `150802` RX0/RX1 common-orbit fit | POST-FIX | Common identity and tau; separate receiver offsets and bounded residual drifts | Training winner 59748; train/holdout 90.415/158.151 Hz | Runner gap 1.085 Hz; alternative 65438 holds out at 112.746 Hz; shared-curvature null 143.143 Hz beats winner | Fails named identity ([report](2026_08_25_150802_alias_aware_common_orbit.md)) |
| RX0 anchor replay | POST-FIX | Full epoch and local CFO search around RX1 anchors; no TLE | 126/126 paired frames within two samples; 66 exact | Same Pluto clock/LO; no catalogue specificity | Strong same-emitter evidence only ([report](2026_08_25_rx0_cross_receiver_anchor_replay.md)) |
| 24-hour physical-RF path census | POST-FIX | Counter-authoritative captures; path/episode census before naming | 89 committed dwells / 178 streams; multiple repeated multi-path geometries | Descriptive screens; no method passes all identity controls | Establishes abundant physical RF, not satellite count or identity ([retrospective](2026_08_25_post_refill_24h_retrospective/README.md)) |
| `065355` multipath candidate | POST-FIX | Shared candidate with per-path nuisance offsets and episode selection | Candidate 62124 shape can fit selected paths | Wrong-time -300 s control remains competitive; conditional episode DP | Named association rejected; candidate remains conditional ([report](2026_08_25_post_refill_24h_retrospective/related_reports/2026_08_25_065355_satellite_activity.md)) |
| `073628` raw catalogue activity | POST-FIX | Catalogue identity, delay, offset, and episodes over 36,408 candidate states | Winner 58636, delay +0.2 s, RMS 126.21 Hz | Top candidates hit search/candidate caps; no matched family control | Finite single-object screen exhaustive; upstream peak inventory and unrestricted multi-object search/control family incomplete; no identity ([report](2026_08_25_post_refill_24h_retrospective/related_reports/2026_08_25_073628_raw_satellite_activity.md)) |
| `085623`, `103607`, and cross-dwell shared candidates | POST-FIX | Per-path/joint multipath fits and shared-NORAD tests | Winners 58610 and 66811 produce low selected-path RMS; cross-dwell fit also selects 66811 | Dense-path and fixed/permutation controls remain active; historical producer provenance is partial | Repeated candidate behavior, specificity failure ([retrospective notes](2026_08_25_post_refill_24h_retrospective/SNAPSHOT_NOTES.md)) |
| `115401` four-path association | POST-FIX | Joint candidate across four paths | Winner 58937 | All four permutation controls activate | Rejected ([retrospective](2026_08_25_post_refill_24h_retrospective/README.md)) |
| `135219` catalogue association | POST-FIX | Actual-time catalogue search plus wrong-time diagnostics | Actual-time winner 58789 | A +30 s wrong-time candidate 63280 fits better | Rejected ([retrospective](2026_08_25_post_refill_24h_retrospective/README.md)) |
| Structural-penalty calibration | MIXED Aug-21 through Aug-25 | Empirical activation penalty across 74 clusters / 120 paths | 1 activation, 1 inconclusive among 59 holdout clusters labeled null | Best-case upper bound .0779 exceeds .05; 70/74 “null” clusters have active siblings | Null construction is contaminated; not a valid identity gate ([related-report index](2026_08_25_post_refill_24h_retrospective/related_reports/README.md)) |
| PSS/SSS waveform lane | MIXED | Synchronization sequence acquisition and rate | PSS can corroborate timing | Independent SSS yields no dwell rates and no payload identity | Not a satellite-linking solution ([report](2026_08_25_multi_dwell_pss_sss_doppler.md)) |

![All-visible Starlink CFO fits on the POST-FIX 150802 arc](figures/2026_08_25_150802_visible_starlink_tle_fit/all-visible-satellite-fits.png)

### 3.3 Why attractive candidates still fail

The failures are consistent rather than contradictory:

- A short Doppler arc admits many nearby Starlink curves after a free constant
  frequency offset.
- A fitted time shift can absorb TLE age, UTC error, source mismatch, and curve
  shape. When its optimum hits the search boundary or changes direction between
  folds, it is not a measured clock correction.
- Adding per-receiver drift improves flexibility but can erase the very
  curvature that should distinguish candidates.
- Two receiver channels on one Pluto establish same-emitter repeatability, but
  do not provide independent sample clocks or LNB references.
- A population rank can show that orbital curves beat radio polynomials more
  often than expected while still failing to name any individual satellite.
- Wrong-time, permutation, runner, alternate-catalogue, and shared-curvature
  controls repeatedly remain active.

The current status is therefore:

| Claim | Status |
|---|---|
| Coherent physical RF is present | **Established** |
| Multiple paths can be linked to the same local emitter | **Established in selected episodes** |
| The population contains satellite-like orbital curvature | **Supported** |
| NORAD 59748 is a useful conditional candidate for `150802` | **Supported conditionally** |
| Any named NORAD identity is secure | **Not established** |
| Absolute orbit state or physical range is measured | **Not established** |
| Payload has been decoded | **Not established** |

### 3.4 Most credible next satellite-linking experiments

1. Freeze TLE-blind, source-bound episodes before inspecting the catalogue.
2. Require the same NORAD to recur across separated portions of one pass or
   across repeated, independently predeclared dwells.
3. Keep the primary orbit model lean: candidate identity plus a constant
   receiver offset. Use a capture-clock-derived narrow tau bound; treat drift
   and wide-tau fits as sensitivity analyses, not primary parameters.
4. Exploit separately calibrated physical Plutos or, ideally, a second known
   site. Shared channels within one Pluto are excellent emitter controls but
   not independent clocks.
5. Separate presence calibration from specificity calibration. Build nulls from
   genuinely inactive captures, not path-level `NO_RESULT` rows with active
   sibling paths.
6. Run full, uncapped candidate/control families and report family-wise error,
   runner separation, wrong-time behavior, and boundary optima.
7. Add an independent observable: payload/beam timing, a second calibrated RF
   edge, a second station, or repeat-pass consistency. More nuisance parameters
   on the same short CFO arc will not resolve identity.

## 4. Recommended program

### Doppler-rate program

1. **Measurement:** retain phase-safe, independently qualified frame-CFO.
2. **Baseline:** source-bound fixed 500 ms causal robust line.
3. **Candidate state:** CFO, rate, and optional acceleration; enable curvature
   only with past-only evidence and hysteresis.
4. **Truth experiment:** inject known polynomial phase into real POST backgrounds
   and score rate bias/RMSE/coverage.
5. **Promotion cohort:** at least ten unopened POST captures with feasible,
   branch-supported episodes and identical masks.
6. **Clock campaign:** later and separately measure simultaneous conducted
   references through the actual LNB/receiver chains.

### Satellite-linking program

1. Freeze episodes, UTC/site/RF metadata, TLE snapshot, visibility policy, and
   nuisance bounds before fitting.
2. Use fixed-time or tightly bounded-time candidate fits with a free constant
   offset; rank only on held-out data.
3. Demand repeat-pass or independent-site recurrence plus family-wide controls
   before naming an object.
4. Keep “same emitter,” “orbital-like,” and “named NORAD” as separate gates.

## 5. Reproducibility and scope notes

- This document is a review of committed artifacts at repository baseline
  `b25443f`; it does not recompute every underlying corpus.
- The [24-hour retrospective](2026_08_25_post_refill_24h_retrospective/README.md)
  preserves a code snapshot because some historical producers came from a
  research worktree. Its
  [snapshot notes](2026_08_25_post_refill_24h_retrospective/SNAPSHOT_NOTES.md)
  identify historical byte drift and missing producer manifests. Treat those
  rows as forensic evidence, not uniformly reproducible fresh-main products.
- The [satellite identity recovery synthesis](2026_08_25_satellite_identity_recovery_v2.md)
  cites an external recovery audit at commit `bbf84a0` that is not in the current
  `origin/main` ancestry. Its hash-cited population results are retained here
  with that provenance limitation.
- The 3 and 5 MS/s deployment work is transport qualification, not Doppler-rate
  science. No same-signal 2.5-versus-3 MS/s rate benchmark exists yet.
- The timing/delay curvature studies are template/channel-relative and share
  candidate selection with the CFO lane. They cannot presently identify
  absolute propagation delay, range, or physical Doppler independently.

## 6. Bottom line

The refill fix changed the scientific answer. PRE-FIX global slopes near
-5 to -7 kHz/s were largely a recording-time artifact; short reset-local
measurements clustered much closer to -3 to -4 kHz/s. POST-FIX data no longer
show that systematic displacement, and clean arcs reveal real curvature rather
than refill steps.

The most plausible route to genuinely better receiver-CFO rate estimates is
not more phase feedback or a larger acquisition search. It is:

> qualified frame-CFO measurements + source-bound 500 ms robust history + a
> conservatively enabled acceleration state, validated against known injections
> in real POST backgrounds and a fresh counter-authoritative cohort.

For satellite linking, orbital shape is now credible at the population level,
but the catalogue remains too crowded and the nuisance/time sensitivity too
large for a named identity. Better rate estimation will help, but secure
identity will also require independent geometry, recurrence, or another
observable.
