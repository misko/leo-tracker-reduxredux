# DS13 residual trends: all 22 recovered tracks

The audit finds a mixture of within-channel drift, channel offsets, and curved residual structure. One common LNB/receiver drift does not explain all of it. Timing-only refits generally do not remove the trends. Timing plus frequency biases predicts some tracks well, but fits are often confounded or unstable when tested on another portion of a track.

All results below are diagnostics of the final group-summed memberships with Viterbi peak selection. The original associations, curves, timing parameters, and calibration are unchanged. No RF collection or new IQ processing was performed.

## What is shared between channels?

For a single receiver chain with a common LNB LO, an additive LO drift is shared in **native Hz**. Geometric Doppler scales with RF frequency. A useful residual decomposition is:

`native residual(satellite, receiver, channel, time)`

`= shared receiver drift(time) + channel-dependent bias + satellite/signal-model discrepancy + noise`.

The existing fit already subtracts a separate offset and linear drift for each receiver, plus an RF-dependent calibration coefficient. The audit therefore concerns what remains after that calibration. It does not imply the hardware has no drift.

Plots multiply native residuals by `11.085 GHz / actual RF`. Consequently, even a common native-Hz drift appears with slightly different slopes after normalization. For channels 1 and 2 on 64361, those factors are approximately 1.0350 and 1.0114. A radio reference error can also have a tuning-frequency-dependent component; the common-additive model is a testable component, not a complete hardware characterization. RX0 and RX1 must not be assumed to have identical drift.

I tested common receiver drift in native Hz and also compared different satellite peaks at the **same time, same channel, same receiver and same GLRT group**. Their residual difference cancels any common additive receiver drift, without needing to know its shape. Those differences are not uniformly flat.

## Evidence and validation

- 22 receiver-specific tracks, 3,238 selected memberships, both scans. One selected peak per group within each track; a GLRT group may contain distinct peaks from multiple satellites.
- Linear and quadratic least-squares fits, Huber slopes, two-second median-bin trends, separate channel fits, channel offsets with common trends, and 600 resamples of five-second time clusters.
- Five contiguous, equal-duration held-out time blocks, with a one-second exclusion around each test block. Every fold refits the correction on the other blocks. This checks interpolation and some endpoint prediction; it is not a new scan or an independently selected cohort.
- Additional early-half/late-half and seed-owned/backfilled transfer tests. Quadratic extrapolation is frequently unstable even when local interpolation is useful.
- Exact physical timing refits, extra timing in ±1 second: timing alone; timing plus one normalized-Hz bias; timing plus one native-Hz bias; timing plus channel constants. Doppler-scale-plus-offset is included as a diagnostic alternative.
- Exact predictions reproduce the sealed curves at selected observation times to better than **5.9e-11 Hz**. The physical ephemeris NPZ files were checked against both the bank receipt and the sealed overlay receipt. Historical deployment files outside this workspace were not revalidated.
- Original proposal rows, independent/MAP peak choices, stronger versus weaker GLRT margins, and a wider comparison cohort with group support ≥0.90 but **no ±150 Hz residual gate or initial-ownership gate**.
- Same-satellite observations on RX0 and RX1 were paired by channel and nearest time, without reusing a row, with at most 0.75 s separation.

These are selected-data diagnostics. The final tracks were selected using baseline posteriors and a ±150 Hz gate, so low RMS is partly built into the selection. The wider comparison still conditions on baseline posterior. Bootstrap intervals are descriptive stability checks, not independent-error significance tests or a correction for testing many models. A correction that wins here is a candidate for validation, not established physical calibration.

## Full inventory

Slope is from the pooled line fit in normalized Hz/s. `q` is the coefficient multiplying `(t − mean(t))²`, in Hz/s², not the second derivative; the latter is `2q`. RMS columns are **in-sample** and include an independently fitted intercept for each polynomial. They should not be interpreted as achievable positioning accuracy.

| Track | Groups | Slope Hz/s | q Hz/s² | Current RMS Hz | After line Hz | After quadratic Hz |
|---|---:|---:|---:|---:|---:|---:|
| A · 64010/RX1 | 147 | -3.31 | -0.2084 | 46.7 | 38.4 | 36.1 |
| A · 58484/RX1 | 107 | +2.95 | -0.0172 | 69.2 | 57.0 | 56.9 |
| A · 64361/RX0 | 146 | +2.80 | +0.0078 | 78.8 | 36.3 | 36.1 |
| A · 68299/RX1 | 127 | -0.51 | -0.0879 | 49.2 | 32.7 | 30.4 |
| A · 68299/RX0 | 208 | -1.34 | -0.2799 | 65.9 | 59.2 | 43.2 |
| A · 64013/RX0 | 258 | -2.31 | -0.0356 | 80.4 | 47.5 | 45.0 |
| A · 100431/RX0 | 99 | -3.22 | +0.0243 | 55.0 | 28.2 | 28.1 |
| A · 67889/RX0 | 278 | -0.30 | -0.0164 | 44.4 | 44.1 | 43.7 |
| A · 58622/RX1 | 154 | -0.56 | -0.0623 | 45.7 | 37.8 | 36.3 |
| A · 66186/RX1 | 185 | +5.13 | -0.0830 | 68.8 | 29.1 | 26.8 |
| A · 64767/RX1 | 83 | +4.75 | -0.0030 | 50.0 | 30.5 | 30.5 |
| B · 66231/RX1 | 44 | +2.46 | +0.0638 | 48.6 | 43.8 | 43.6 |
| B · 59199/RX0 | 238 | -0.43 | -0.0146 | 67.3 | 66.0 | 65.8 |
| B · 65739/RX0 | 90 | -0.16 | -0.0096 | 52.8 | 52.6 | 52.6 |
| B · 65686/RX0 | 201 | +0.91 | +0.0708 | 67.2 | 63.4 | 57.3 |
| B · 63926/RX0 | 234 | -0.71 | -0.0255 | 61.1 | 59.4 | 59.2 |
| B · 62953/RX1 | 153 | +1.26 | -0.0533 | 60.5 | 57.2 | 56.4 |
| B · 65804/RX0 | 94 | -4.99 | -0.0014 | 71.6 | 56.9 | 56.9 |
| B · 65804/RX1 | 60 | +0.53 | -0.3132 | 76.1 | 74.7 | 72.5 |
| B · 69307/RX0 | 78 | -2.48 | -0.1359 | 69.5 | 61.2 | 57.4 |
| B · 62847/RX0 | 110 | +0.60 | +0.0039 | 63.1 | 57.5 | 57.5 |
| B · 65745/RX0 | 144 | +4.50 | +0.0104 | 64.8 | 49.7 | 49.7 |

## What survives prediction tests?

These scores use the same final cohort within each row unless a channel subset is explicitly stated. The constant-only score estimates a mean from training blocks; it may be worse than leaving the sealed residual untouched. Compare corrected CV both to constant-only CV and to the current RMS above.

| Track | Constant-only CV Hz | Diagnostic with useful evidence | Diagnostic CV Hz | Assessment |
|---|---:|---|---:|---|
| A · 64010/RX1 | 52.8 | Timing + channel constants | 21.7 | Clear channel offsets and within-channel time structure; physical timing/bias form transfers locally. |
| A · 58484/RX1 | 71.2 | Channel offsets + line | 34.7 | Strong slope and channel separation. Quadratic adds only a small gain (32.3). Timing + channel constants is poor (70.0). |
| A · 64361/RX0 | 90.5 | Line | 38.0 | Strong within-channel drift. Quadratic is worse (45.8); timing alone is worse (91.0). |
| A · 68299/RX1 | 34.0 | Timing + one normalized bias | 32.1 | Modest curvature/offset, much weaker than RX0. On 126 well-covered CH2/CH4 groups, channel offsets alone score 27.3, versus 27.9 with quadratic. |
| A · 68299/RX0 | 71.5 | Channel offsets + quadratic | 49.6 | Strong curved structure; pooled quadratic scores 49.9. Timing + channel constants scores 73.5. |
| A · 64013/RX0 | 79.3 | Quadratic | 47.6 | Slope plus some curvature. On 236 CH1/CH4 groups, channel-line CV is 41.4 and channel-quadratic CV is 34.4. |
| A · 100431/RX0 | 46.6 | Line | 29.8 | Clear drift; quadratic is unnecessary (31.9). |
| A · 67889/RX0 | 45.2 | No compelling time correction | — | Line 46.2, quadratic 44.5: negligible useful trend. |
| A · 58622/RX1 | 41.5 | Channel constants only | 22.2 | Apparent pooled curvature largely disappears after channel adjustment. A common line adds essentially nothing (22.1); quadratic worsens to 25.1. |
| A · 66186/RX1 | 79.7 | Timing + channel constants | 28.1 | Strong drift plus curvature, shared by all three channels. Strongest timing/bias candidate alongside 64010. |
| A · 64767/RX1 | 57.7 | Channel offsets + line | 17.2 | Clear drift and a channel step. Quadratic barely changes score (17.0). Timing + channel constants fails (82.1). |
| B · 66231/RX1 | 51.2 | Weak line candidate | 45.3 | Only 44 groups; slope weakens from +2.46 to +0.86 Hz/s in the wider ungated window. Not robust enough for a new drift parameter. |
| B · 59199/RX0 | 68.8 | No useful time correction | — | Line 72.4, quadratic 84.7; avoid fitting the noise. |
| B · 65739/RX0 | 53.1 | No useful time correction | — | Line 53.1, quadratic 62.8. |
| B · 65686/RX0 | 71.5 | Visible bowl; correction unvalidated | — | Quadratic 73.1 versus line 81.2. Curvature repeats in CH1 and CH2 but does not beat constant-only CV or the uncorrected 67.2 Hz. |
| B · 63926/RX0 | 60.9 | No useful time correction | — | Line 63.6, quadratic 75.6. |
| B · 62953/RX1 | 63.4 | No useful time correction | — | Line 63.5, quadratic 74.7; recovered membership is not evidence for adding another drift parameter. |
| B · 65804/RX0 | 85.0 | Visible negative line; predictive gain limited | 71.1 | Strong slope within channels, but correction barely beats current 71.6 Hz RMS. Large block-to-block variation remains. |
| B · 65804/RX1 | 76.9 | No validated quadratic correction | — | Line 79.7, quadratic 93.7 despite a fitted negative quadratic coefficient. |
| B · 69307/RX0 | 75.6 | Negative slope, weak predictive evidence | 72.5 | Worse than uncorrected 69.5 Hz. Strong-margin half has only -0.31 Hz/s; do not promote this to a calibrated drift. |
| B · 62847/RX0 | 60.2 | Mostly a constant offset | — | Line 64.2, quadratic 113.6. |
| B · 65745/RX0 | 70.1 | Channel offsets + line | 44.7 | Clear drift. Channel-adjusted rate is +7.06 Hz/s, versus pooled +4.50. Quadratic adds little (43.0). |

Sparse channels cause some full-cohort channel-controlled CV folds to be unidentifiable: the held-out block contains a channel absent from training. Those scores are marked unavailable in the data, not silently imputed. The supplemental analysis explicitly reports restricted, well-covered channel cohorts (at least 15 groups and 40% of the track time span), with scores compared only within each restricted cohort.

## Detailed findings

### 64361: the slope is real within the dominant channel; its cause is not identified

CH2 contains 136 of 146 groups and spans the whole 84.6-second track. Its slope is +2.82 Hz/s, versus +2.80 pooled. All 83 retained seed-owned groups are CH2. Viterbi changes the slope only from +2.76 to +2.80. Original proposals give +3.18 Hz/s; the broader no-residual-gate cohort gives +2.73. The strong-margin half also retains a positive slope (+3.52). This is not created by joining CH1 and CH2 or by Viterbi.

Changing timing alone gives 78.1 Hz in-sample RMS and leaves +2.89 Hz/s. Timing plus a normalized bias gives an extra -95.6 ms, bias -301.8 Hz, and 46.0 Hz fitted RMS, but held-out RMS is 59.0 Hz. Fitting only one half and predicting the other is unstable: approximately 92.3 and 177.9 Hz test RMS, with even the fitted timing sign changing between halves. The linear description predicts much better overall (38.0 Hz CV). The -95.6 ms correction is not a measured clock error.

A Doppler-scale-plus-offset fit scores 36.9 Hz in time-block CV, similar to the line. Its fractional scale is -0.0009276, equivalent to about -10.3 MHz at 11.085 GHz if interpreted literally as RF error. That is a diagnostic equivalence, not evidence that the RF metadata are wrong: scale, transmitter drift, orbital velocity discrepancy, and calibration errors are confounded on this limited arc.

At 105–130 s, same-group 64361 and 68299 peaks have similar native-Hz slopes (+2.99 and +3.32). A shared receiver contribution is plausible for that interval. Other intervals and satellite pairs disagree, so the data do not establish a single satellite-only or receiver-only cause. The earlier suggestion that this must be a satellite-specific timing/TLE issue was too strong.

### 68299/RX0: strongest curvature; RX1 is a valuable control

RX0's quadratic coefficient is -0.2799 Hz/s², essentially unchanged by channel controls (-0.2820). The five-second cluster-resampling interval for the channel-adjusted coefficient is approximately [-0.461, -0.122]. It is visible separately in CH1, CH3, and CH4; their coefficients are approximately -0.289, -0.282, and -0.251. Independent peak selection and the wider cohort retain the same sign and scale (-0.265 and -0.249).

This shape predicts withheld local blocks: channel-quadratic CV 49.6 Hz versus channel-line 93.9 and channel-offset-only 72.1. It does not extrapolate reliably: fitting the early half and predicting the late half with a quadratic gives 363 Hz RMS. Treat the curve as a local description, not an orbit correction to extend arbitrarily.

There are 83 same-channel, near-simultaneous RX0/RX1 pairs (maximum separation 0.562 s). Their native-Hz quadratic coefficients are -0.270 on RX0 and -0.101 on RX1; the receiver difference retains -0.169 Hz/s². A shared satellite orbit error alone cannot explain that entire difference. Receiver-chain differences, channel/signal effects, selection, and estimator effects remain possible; receiver timing/calibration is not held equal between chains.

Late in the track, 68299 and 64013 also differ at identical time/channel/receiver: the robust channel-controlled native difference slope is about -6.44 Hz/s over 40 matched groups. A common additive LNB drift cannot generate that differential trend by itself.

### Channel offsets are material, but do not imply different LNB drift per channel

For A/58622, fitting a constant per channel reduces time-block CV from 41.5 to 22.2 Hz. The pooled quadratic coefficient -0.0623 becomes +0.0033 after channel adjustment; the bootstrap interval spans zero. This is the clearest case where changing channel composition makes a pooled residual look curved.

For A/58484, channel adjustment reduces line-fit RMS from 57.0 to 30.7 Hz. It reveals a common positive rate of +3.88 Hz/s, versus +2.95 pooled. The channel means and slope both matter.

For A/64767, channel adjustment reveals +6.02 Hz/s, versus +4.75 pooled. CH1 and CH3 individually give +6.44 and +5.97. The model needs a time-varying component even after allowing different constant channel biases.

For B/65745, channel adjustment raises the inferred rate from +4.50 to +7.06 Hz/s. On the 94 well-covered CH3/CH4 groups, line-plus-channel CV is 37.9 Hz, versus 76.1 for channel constants alone. Mixing channels partly hides the slope here; it does not create it.

Channel offsets in this audit are phenomenological. They may reflect signal/estimator or calibration differences, and are not proof of an independent LNB oscillator drift in each channel.

### Timing/bias corrections that do predict locally

A/64010: extra timing -161.6 ms with fitted channel biases approximately -557, -553, -618 normalized Hz; 20.6 Hz fitted RMS, 21.7 Hz time-block CV. All three channel slopes are negative. This is a useful physical-form candidate, but a joint recalibration must determine which part is timing versus bias.

A/66186: extra timing -160.3 ms and channel biases approximately -552, -553, -570 normalized Hz; 25.9 Hz fitted RMS, 28.1 Hz CV. The curvature also repeats in all three channels. Timing plus one constant already scores 28.6 Hz CV. This is another promising candidate, not a demonstrated timing-source fault.

Across the audit, the timing derivative and a constant-bias column are nearly collinear: absolute column cosine is often above 0.99. A subsecond timing change and hundreds of Hz of frequency offset can compensate each other. Precise-looking fitted timings should not be treated as physically identified parameters.

### 65804: receiver dependence argues against an orbit-only explanation

The final RX0 track has -4.99 Hz/s pooled and -5.58 with channel constants. Its CH2 and CH4 slopes are -5.92 and -4.96. The strong-margin subset is also negative (-6.26), and widening the cohort leaves -5.27 Hz/s. The structure is not just weak points or channel mixing.

The 38 matched same-channel RX0/RX1 pairs have native-Hz slopes -6.20 and -0.41, respectively, and a difference of -5.79 Hz/s. Their maximum time separation is 0.641 s. Together with the same-receiver comparison against 69307 (52 same-group pairs; robust channel-adjusted difference about +4.03 Hz/s for 69307 minus 65804), this rejects both a purely shared satellite correction and a purely common additive RX0 drift as complete explanations. Mixed signal/estimator/receiver effects are plausible, but their cause is unresolved.

### 65745: archived IQ-refinement and TLE checks reinforce the trend

The earlier saved estimator audit used a different, wider stable cohort of 178 points. Independent fine-CFO refinement changed its native-Hz slope from +7.00 to +7.04 Hz/s. Thus that older experiment did not remove the drift by refining the stored peak. This is supporting archived evidence, not a new IQ run and not the same cohort as the present 144-point final track.

The archived older-TLE comparison, after allowing ±10 s timing alignment, retained a normalized slope of about +6.90 Hz/s and RMS 105.8 Hz, versus approximately +6.48 Hz/s and 101.5 Hz for the pinned-TLE baseline cohort. The available older element set did not resolve the trend. This check exists for 65745 only; it is not an exhaustive alternative-TLE audit of all satellites.

## Shared receiver drift versus satellite-specific residuals

I fitted a native-Hz shared linear or quadratic receiver correction with per-track constant offsets and shared channel constants. For transfer testing, the target satellite is excluded from estimating the shared correction. Testing uses only target times with another satellite observed on that receiver within two seconds; each test mean is removed, so this is a shape-transfer diagnostic rather than an absolute frequency prediction.

This simple common drift generally does not transfer well. Examples of centered native RMS before/after the transferred quadratic are A/64361 44.9/54.5 Hz, A/64767 49.3/58.4 Hz, B/65804 71.9/76.6 Hz, and B/65745 57.3/59.5 Hz. Some cases improve modestly, such as A/66186 65.5/60.9 Hz. This rejects a universal shared low-order polynomial as the entire explanation, not every possible oscillator process.

The exact same-group satellite differences are stronger controls because they cancel the additive receiver process point by point. Selected examples (robust channel-controlled native difference slope):

| Scan / receiver | Satellites differenced | Matched groups | Time span s | Difference slope Hz/s |
|---|---|---:|---|---:|
| A / RX0 | 64361 − 68299 | 33 | 105.1–129.7 | -0.73 |
| A / RX0 | 68299 − 64013 | 40 | 130.9–149.5 | -6.44 |
| A / RX0 | 100431 − 64013 | 39 | 152.1–182.4 | -0.36 |
| A / RX1 | 66186 − 64767 | 23 | 285.5–299.3 | -4.56 |
| B / RX0 | 69307 − 65804 | 52 | 194.6–223.2 | +4.03 |

Some pairs agree; others do not. These selected overlapping arcs are limited in duration and still contain estimator noise. They justify keeping both common receiver terms and satellite/signal-specific error terms in the investigation.

## Selection and estimator findings

The ±150 Hz gate hides some track ends. In the ±10 s wider cohort without that gate, A/64361 has 15/233 groups outside ±150 Hz; A/64013 has 42/315; B/62953 has 20/179; B/65804/RX0 has 10/170. Those are comparison counts, not automatically trustworthy new assignments. A/64013's slope steepens from -2.31 to -2.87 Hz/s in that broader cohort. A narrow post-fit gate should not be used to validate a correction learned from the retained points.

Original seed proposals sometimes contain large outliers or incorrect peak choices, producing enormous ordinary least-squares slopes. They were retained in the audit for provenance, but those slopes are not evidence of extreme physical drift. Huber summaries, the final cohort, and the relaxed target-MAP cohort give the more useful comparisons.

Viterbi is not the principal origin of the strongest trends: A/64361 changes +2.76 to +2.80 Hz/s, A/66186 +5.06 to +5.13, A/68299/RX0 quadratic -0.265 to -0.280, and B/65745 +4.26 to +4.50. It is not exactly neutral: B/65804/RX0 changes -4.41 to -4.99, and B/62953 +1.05 to +1.26.

Many final peaks retain zero native residual-bin correction relative to acquired CFO, e.g. 139/146 for 64361, 203/208 for A/68299/RX0, 181/185 for 66186, 94/94 for B/65804/RX0, and 143/144 for B/65745. This is not an absolute-frequency quantizer: acquired CFO varies between observations. Metadata correlations do not establish the cause, and the original GLRT estimation can carry smooth bias. Only 65745 has the cited archived fine-CFO comparison; the other strong tracks still need independent estimator validation if causal attribution is required.

## Recommended next experiment

Use a physically shared native-Hz calibration model: one time-varying additive drift per receiver chain; static RF/channel calibration terms; orbit Doppler evaluated at each observation's actual RF; and regularized satellite timing and frequency bias. Preserve channel identity even when tracks are joined. This agrees with the expectation that the common LNB drift is shared across channels.

Start with the cases whose proposed correction transfers: A/64010 and A/66186 for timing/bias, A/58622 for channel offsets, and the receiver comparisons for A/68299 and B/65804. Use matched same-group satellite differences to prevent a common receiver correction from absorbing incompatible trends. Treat A/64361 and A/64767 as unresolved drift cases rather than declaring a timing fix.

Fit on training groups, then reevaluate the full candidate likelihood and associations on withheld groups before reopening the residual gate. Use the broader original cohort to detect censoring, with robust or mixture treatment of incorrect peaks. Per-satellite linear/quadratic corrections can describe these residuals, but freely adding them to a position solver can consume the very Doppler information used to locate the receiver. They should remain diagnostics until their calibration and held-out benefit are established.

## Files

- `key-findings.png` / `.svg`: focused eight-panel figure.
- `scan-a-residual-audit.png` / `.svg`, `scan-b-residual-audit.png` / `.svg`: all 22 tracks, with channel colors, fitted components, and the wider ungated comparison.
- `all-tracks.csv`: numerical summary and CV scores for every track.
- `points-and-diagnostic-corrections.csv`: exact final rows and fitted diagnostic components.
- `receipt.json`: all fits, time folds, bootstrap results, original/relaxed cohorts, peer comparisons, source hashes and figure hashes.
- `followup.json`: timing plus channel constants, well-covered channel subsets, GLRT metadata controls, and matched cross-receiver results.
- `shared-receiver-drift.json`: native-Hz shared-drift transfer tests.
- Scripts and tests are in the parent report directory: `residual_trend_audit.py`, `residual_trend_followup.py`, `residual_shared_receiver_audit.py`, `plot_residual_audit_summary.py`.

Archived supporting evidence: `../satellite65745-glrt-audit/summary.json`, `../satellite65745-orbit-audit/extra-constant-and-tle-comparison.json`, and `../satellite65745-orbit-audit/older-tle-timing-alignment-10s.json`. These use different saved cohorts and must not be mixed numerically with the final-track RMS table.
