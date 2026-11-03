# Recent scan localization comparison

Draft with incomplete evaluation. Snapshot: 2026-10-06 06:13 PDT.

This study compares orbit-blind GLRT refinement, receiver cone priors, and T1-AT versus V16 position scoring on 16 recent scans, with a matched fitted-c versus c = 0 control. The central endpoint is position error, not merely signal coverage.

**232 of 256 position fits are saved; 165 pass convergence checks and 42 hit the search boundary.** All 16 cases are saved for 13 of 16 scans. A saved but unconverged fit remains provisional. Missing fits are not zero-error results.

## Current findings

The cohort evaluation is incomplete. Paired results below describe only the available scans; they cannot yet establish a cohort-wide winner.

The table reports one contrast at a time with all other switches held fixed. Only pairs with two converged interior solutions enter the median change. Negative change means lower position error. Each row has at most one pair per scan.

| Change | Held fixed | Available pairs | Converged interior pairs | Median error change (m) | Improved pairs |
| --- | --- | --- | --- | --- | --- |
| arm: fitted-c minus zero-c | refinement=original; model=T1AT; cone=off | 16 | 11 | +19.6 | 5/11 |
| arm: fitted-c minus zero-c | refinement=original; model=T1AT; cone=on | 16 | 11 | +16.5 | 5/11 |
| arm: fitted-c minus zero-c | refinement=original; model=V16; cone=off | 16 | 9 | +36.0 | 4/9 |
| arm: fitted-c minus zero-c | refinement=original; model=V16; cone=on | 16 | 7 | +35.7 | 3/7 |
| arm: fitted-c minus zero-c | refinement=refined; model=T1AT; cone=off | 13 | 10 | -16.1 | 5/10 |
| arm: fitted-c minus zero-c | refinement=refined; model=T1AT; cone=on | 13 | 10 | -18.3 | 5/10 |
| arm: fitted-c minus zero-c | refinement=refined; model=V16; cone=off | 13 | 9 | +24.0 | 3/9 |
| arm: fitted-c minus zero-c | refinement=refined; model=V16; cone=on | 13 | 6 | -9.2 | 3/6 |
| cone: on minus off | refinement=original; model=T1AT; arm=fitted-c | 16 | 11 | -11.1 | 9/11 |
| cone: on minus off | refinement=original; model=T1AT; arm=zero-c | 16 | 11 | -5.5 | 7/11 |
| cone: on minus off | refinement=original; model=V16; arm=fitted-c | 16 | 8 | -1.6 | 6/8 |
| cone: on minus off | refinement=original; model=V16; arm=zero-c | 16 | 7 | -4.1 | 4/7 |
| cone: on minus off | refinement=refined; model=T1AT; arm=fitted-c | 13 | 10 | -6.6 | 6/10 |
| cone: on minus off | refinement=refined; model=T1AT; arm=zero-c | 13 | 10 | -1.4 | 5/10 |
| cone: on minus off | refinement=refined; model=V16; arm=fitted-c | 13 | 6 | -0.1 | 3/6 |
| cone: on minus off | refinement=refined; model=V16; arm=zero-c | 13 | 7 | +6.9 | 3/7 |
| model: V16 minus T1AT | refinement=original; cone=off; arm=fitted-c | 16 | 9 | +154.0 | 3/9 |
| model: V16 minus T1AT | refinement=original; cone=off; arm=zero-c | 16 | 8 | -41.2 | 4/8 |
| model: V16 minus T1AT | refinement=original; cone=on; arm=fitted-c | 16 | 8 | +109.3 | 3/8 |
| model: V16 minus T1AT | refinement=original; cone=on; arm=zero-c | 16 | 7 | +42.6 | 3/7 |
| model: V16 minus T1AT | refinement=refined; cone=off; arm=fitted-c | 13 | 9 | -91.8 | 6/9 |
| model: V16 minus T1AT | refinement=refined; cone=off; arm=zero-c | 13 | 8 | -81.1 | 5/8 |
| model: V16 minus T1AT | refinement=refined; cone=on; arm=fitted-c | 13 | 7 | +161.8 | 3/7 |
| model: V16 minus T1AT | refinement=refined; cone=on; arm=zero-c | 13 | 7 | -66.1 | 4/7 |
| refinement: refined minus original | model=T1AT; cone=off; arm=fitted-c | 13 | 8 | -42.8 | 5/8 |
| refinement: refined minus original | model=T1AT; cone=off; arm=zero-c | 13 | 7 | -86.0 | 4/7 |
| refinement: refined minus original | model=T1AT; cone=on; arm=fitted-c | 13 | 7 | -47.2 | 4/7 |
| refinement: refined minus original | model=T1AT; cone=on; arm=zero-c | 13 | 7 | -71.8 | 4/7 |
| refinement: refined minus original | model=V16; cone=off; arm=fitted-c | 13 | 8 | -128.0 | 5/8 |
| refinement: refined minus original | model=V16; cone=off; arm=zero-c | 13 | 8 | -160.8 | 5/8 |
| refinement: refined minus original | model=V16; cone=on; arm=fitted-c | 13 | 4 | -43.0 | 2/4 |
| refinement: refined minus original | model=V16; cone=on; arm=zero-c | 13 | 4 | -18.0 | 2/4 |

## Position errors for every planned case

Gray cells are pending. A cross marks an unconverged saved fit; a triangle marks the 4 km boundary. Both RF arms use identical branch inputs and maximum search budgets.

![Position errors for all scans and configurations](position-error-matrix.png)

## Paired effects on position error

Each point compares the same scan under one changed switch. Points below the diagonal have lower position error after the switch. The figure uses the displayed fixed settings; the paired table and CSV cover all settings. Sample-rate colors describe different captures, not randomized sample-rate treatments. Crosses and triangles remain provisional or constrained.

![Matched changes from refinement, score model, and cone prior](paired-position-effects.png)

## Per scan comparisons

![Available individual scan comparisons](available-scan-comparison.png)

## Coverage and frequency fit

The following rows use cone-off fitted-c fits to avoid repeating branch coverage eight times. Coverage is fixed before final position fitting; changing the score model can change RMS and position without changing this coverage. RMS is posterior weighted over the frozen associated observations. Strong final support counts windows whose largest satellite responsibility exceeds 0.5, divided by the assigned windows used for fitting. It is model-dependent support, not independently validated identity.

| Scan | Measurements | Model | Satellites | Assigned / passing windows | Coverage | Strong final support / assigned | RMS (Hz) | Position error (m) | Converged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R025-01 | original | T1AT | 32 | 2655 / 3029 | 87.7% | 2488 / 2655 | 131.4 | 2967.7 | True |
| R025-01 | original | V16 | 32 | 2655 / 3029 | 87.7% | 2555 / 2655 | 125.6 | 3343.8 | True |
| R025-01 | refined | T1AT | 30 | 2643 / 3029 | 87.3% | 2500 / 2643 | 123.7 | 2328.7 | True |
| R025-01 | refined | V16 | 30 | 2643 / 3029 | 87.3% | 2111 / 2643 | 120.5 | 1915.4 | True |
| R025-02 | original | T1AT | 32 | 3534 / 3768 | 93.8% | 3307 / 3534 | 106.2 | 1409.9 | True |
| R025-02 | original | V16 | 32 | 3534 / 3768 | 93.8% | 3441 / 3534 | 97.5 | 1460.5 | True |
| R025-02 | refined | T1AT | 32 | 3509 / 3768 | 93.1% | 3299 / 3509 | 102.7 | 764.0 | True |
| R025-02 | refined | V16 | 32 | 3509 / 3768 | 93.1% | 3430 / 3509 | 94.5 | 672.2 | True |
| R025-03 | original | T1AT | 28 | 2538 / 2763 | 91.9% | 2476 / 2538 | 108.5 | 1500.5 | True |
| R025-03 | original | V16 | 28 | 2538 / 2763 | 91.9% | 1878 / 2538 | 114.0 | 2512.7 | True |
| R025-03 | refined | T1AT | 28 | 2536 / 2763 | 91.8% | 2477 / 2536 | 105.7 | 1023.9 | True |
| R025-03 | refined | V16 | 28 | 2536 / 2763 | 91.8% | 1884 / 2536 | 112.7 | 2327.0 | True |
| R025-04 | original | T1AT | 22 | 2888 / 3055 | 94.5% | 2820 / 2888 | 87.1 | 1532.8 | True |
| R025-04 | original | V16 | 22 | 2888 / 3055 | 94.5% | 2867 / 2888 | 82.1 | 1441.3 | True |
| R025-04 | refined | T1AT | 22 | 2897 / 3055 | 94.8% | 2833 / 2897 | 89.8 | 1637.2 | True |
| R025-04 | refined | V16 | 22 | 2897 / 3055 | 94.8% | 2881 / 2897 | 84.9 | 1514.3 | True |
| R025-05 | original | T1AT | 42 | 2847 / 3599 | 79.1% | 2491 / 2847 | 135.3 | 2497.7 | False |
| R025-05 | original | V16 | 42 | 2847 / 3599 | 79.1% | 1077 / 2847 | 116.8 | 4000.0 | False |
| R025-05 | refined | T1AT | 32 | 3398 / 3599 | 94.4% | 3253 / 3398 | 91.8 | 2370.4 | True |
| R025-05 | refined | V16 | 32 | 3398 / 3599 | 94.4% | 3353 / 3398 | 88.2 | 4000.0 | False |
| R025-06 | original | T1AT | 36 | 2253 / 2640 | 85.3% | 2051 / 2253 | 145.0 | 4000.0 | False |
| R025-06 | original | V16 | 36 | 2253 / 2640 | 85.3% | 633 / 2253 | 138.6 | 1712.1 | True |
| R025-06 | refined | T1AT | 26 | 2376 / 2640 | 90.0% | 2323 / 2376 | 100.1 | 1947.9 | True |
| R025-06 | refined | V16 | 26 | 2376 / 2640 | 90.0% | 2366 / 2376 | 97.3 | 1871.7 | True |
| R025-07 | original | T1AT | 22 | 2641 / 2847 | 92.8% | 2601 / 2641 | 79.9 | 3980.6 | True |
| R025-07 | original | V16 | 22 | 2641 / 2847 | 92.8% | 2622 / 2641 | 79.5 | 2407.3 | True |
| R025-07 | refined | T1AT | 30 | 2518 / 2847 | 88.4% | 2360 / 2518 | 96.7 | 3955.6 | True |
| R025-07 | refined | V16 | 30 | 2518 / 2847 | 88.4% | 2504 / 2518 | 90.9 | 2121.2 | True |
| R025-08 | original | T1AT | 30 | 3643 / 3825 | 95.2% | 3505 / 3643 | 96.8 | 1089.3 | True |
| R025-08 | original | V16 | 30 | 3643 / 3825 | 95.2% | 2841 / 3643 | 94.2 | 1820.6 | False |
| R025-08 | refined | T1AT | 30 | 3643 / 3825 | 95.2% | 3527 / 3643 | 92.8 | 1363.2 | True |
| R025-08 | refined | V16 | 30 | 3643 / 3825 | 95.2% | 2914 / 3643 | 92.4 | 2366.4 | False |
| R100-01 | original | T1AT | 30 | 3513 / 3711 | 94.7% | 3406 / 3513 | 77.7 | 1110.0 | True |
| R100-01 | original | V16 | 30 | 3513 / 3711 | 94.7% | 3488 / 3513 | 69.7 | 1264.0 | True |
| R100-01 | refined | T1AT | 30 | 3517 / 3711 | 94.8% | 3416 / 3517 | 92.5 | 1175.3 | True |
| R100-01 | refined | V16 | 30 | 3517 / 3711 | 94.8% | 3501 / 3517 | 86.8 | 1328.6 | True |
| R100-02 | original | T1AT | 54 | 2714 / 3681 | 73.7% | 2068 / 2714 | 168.6 | 4000.0 | False |
| R100-02 | original | V16 | 54 | 2714 / 3681 | 73.7% | 1076 / 2714 | 161.1 | 1968.5 | False |
| R100-02 | refined | T1AT | 40 | 3376 / 3681 | 91.7% | 3039 / 3376 | 127.8 | 1247.1 | True |
| R100-02 | refined | V16 | 40 | 3376 / 3681 | 91.7% | 2662 / 3376 | 116.4 | 2386.0 | True |
| R100-03 | original | T1AT | 33 | 3199 / 3361 | 95.2% | 3053 / 3199 | 86.2 | 1959.0 | True |
| R100-03 | original | V16 | 33 | 3199 / 3361 | 95.2% | 3160 / 3199 | 76.6 | 2269.4 | True |
| R100-03 | refined | T1AT | 42 | 2835 / 3361 | 84.3% | 2615 / 2835 | 109.6 | 1566.2 | False |
| R100-03 | refined | V16 | 42 | 2835 / 3361 | 84.3% | 934 / 2835 | 130.0 | 2018.4 | False |
| R100-04 | original | T1AT | 25 | 2894 / 3086 | 93.8% | 2816 / 2894 | 90.7 | 838.4 | True |
| R100-04 | original | V16 | 25 | 2894 / 3086 | 93.8% | 2855 / 2894 | 83.5 | 582.2 | True |
| R100-04 | refined | T1AT | 25 | 2895 / 3086 | 93.8% | 2815 / 2895 | 102.7 | 777.8 | True |
| R100-04 | refined | V16 | 25 | 2895 / 3086 | 93.8% | 2856 / 2895 | 98.1 | 511.9 | True |
| R100-05 | original | T1AT | 32 | 3645 / 3942 | 92.5% | 3511 / 3645 | 95.8 | 4000.0 | True |
| R100-05 | original | V16 | 32 | 3645 / 3942 | 92.5% | 3623 / 3645 | 90.8 | 4000.0 | True |
| R100-05 | refined | T1AT | 32 | 3650 / 3942 | 92.6% | 3513 / 3650 | 105.9 | 4000.0 | True |
| R100-05 | refined | V16 | 32 | 3650 / 3942 | 92.6% | 3623 / 3650 | 101.7 | 4000.0 | True |
| R100-06 | original | T1AT | 26 | 2879 / 3165 | 91.0% | 2784 / 2879 | 103.4 | 2889.8 | True |
| R100-06 | original | V16 | 26 | 2879 / 3165 | 91.0% | 2849 / 2879 | 100.3 | 4000.0 | True |
| R100-07 | original | T1AT | 45 | 2882 / 3433 | 83.9% | 2276 / 2882 | 171.8 | 3007.8 | False |
| R100-07 | original | V16 | 45 | 2882 / 3433 | 83.9% | 872 / 2882 | 164.8 | 4000.0 | False |
| R100-08 | original | T1AT | 33 | 3736 / 3915 | 95.4% | 3601 / 3736 | 71.8 | 1060.3 | True |
| R100-08 | original | V16 | 33 | 3736 / 3915 | 95.4% | 3593 / 3736 | 69.4 | 1809.7 | True |

## Frozen cohort

Capture times below are Pacific time. Sample rates are native recorded rates. The fixed selection window was October 5, 2026, 10:26:39–18:26:39 PDT. No scan is substituted because its result is poor.

| Short name | Scan ID | Rate (MS/s) | Capture start (PDT) | Saved / planned fits |
| --- | --- | --- | --- | --- |
| R025-01 | scan-fw-fdd9d24f76498df2 | 2.5 | 10-05 11:08:19 | 16 / 16 |
| R025-02 | scan-fw-2afa6e0bc073b82f | 2.5 | 10-05 11:44:45 | 16 / 16 |
| R025-03 | scan-fw-b606ae195f6ab8fa | 2.5 | 10-05 12:57:23 | 16 / 16 |
| R025-04 | scan-fw-8c79ac18d06bc47b | 2.5 | 10-05 14:00:03 | 16 / 16 |
| R025-05 | scan-fw-a0a05179be5b50bb | 2.5 | 10-05 14:56:34 | 16 / 16 |
| R025-06 | scan-fw-e99dee950dd9443a | 2.5 | 10-05 15:53:06 | 16 / 16 |
| R025-07 | scan-fw-16a07a2ba728b117 | 2.5 | 10-05 16:57:45 | 16 / 16 |
| R025-08 | scan-fw-ae832513158980a7 | 2.5 | 10-05 18:02:20 | 16 / 16 |
| R100-01 | scan-fw-aadec7177d989684 | 10.0 | 10-05 11:00:14 | 16 / 16 |
| R100-02 | scan-fw-ddfb0d08aa716511 | 10.0 | 10-05 11:52:49 | 16 / 16 |
| R100-03 | scan-fw-3443fd7c1603a902 | 10.0 | 10-05 12:41:14 | 16 / 16 |
| R100-04 | scan-fw-bf565e1d55644542 | 10.0 | 10-05 13:51:59 | 16 / 16 |
| R100-05 | scan-fw-6670c65afa65c2f1 | 10.0 | 10-05 15:04:39 | 16 / 16 |
| R100-06 | scan-fw-f755ad5587a0d248 | 10.0 | 10-05 16:01:10 | 8 / 16 |
| R100-07 | scan-fw-0c79ba4249fd1989 | 10.0 | 10-05 17:13:54 | 8 / 16 |
| R100-08 | scan-fw-26c9b53f7ca07e39 | 10.0 | 10-05 17:54:14 | 8 / 16 |

## Purpose and experimental design

This comparison asks whether orbit-blind GLRT refinement, a learned receiver cone prior, and the V16 position score improve localization over the original T1-AT position score on recent recordings. It uses 16 fixed scans, eight at 2.5 MS/s and eight at 10 MS/s. Each scan is localized independently. No RF recording is started by this analysis.

The eight combinations of refinement off/on, cone off/on, and T1-AT/V16 each receive two final RF-calibration arms: fitted `c` and `c = 0`. There are therefore 16 position fits per scan and 256 planned fits. The cone toggle affects final position scoring, not the discrete satellite-selection procedure. Both position models share full-data calibration and the T1-AT greedy-plus-replacement association engine. T1-AT here denotes the original Gaussian position score C0, not a replay of historical calibration-fold experiments.

The cohort was fixed by recording metadata rather than localization outcomes. Eight equally spaced time targets per sample rate were matched to the nearest unused eligible completed capture in the eight-hour request window. Each recording lasts 300 seconds. The different-rate scans are not simultaneous controlled observations of identical signals; rate-stratified results are descriptive, not a causal estimate of a sample-rate effect.

## Receiver geometry and its uncertainty

The capture metadata binds the LT3D-004B fixture, with a nominal 40-degree included feed-axis angle and 20-degree outward tilt per holder. RX0 is nominally west-facing and RX1 east-facing. A level base implies nominal 70-degree elevation. These are configuration and fixture facts, not a surveyed measurement of the installed RF boresights. Actual elevation, polarization roll, and phase-center baseline were not measured; the physical connector mapping remains provisional. The known roof coordinates are operator supplied, with unknown survey uncertainty and altitude datum.

The cone model uses shared shape with receiver-specific roll, learned on 20 earlier scans disjoint from this cohort. It applies a soft preference for the receiver that made a detection. It does not treat absence on the other receiver as a veto, and unsupported sky regions remain neutral. This avoids equating west-facing hardware with a perfect western-hemisphere exclusion.

## From recorded IQ to one observation per window

The original analyzer evaluates 20 ms GLRT probes at a configured 120 ms probe stride within retained adaptive visits. It permits up to eight acquisition candidates and uses a saved GLRT margin cutoff of 0.025. A window is identified by probe, receiver, and RF channel. Multiple candidate records within one window are alternative frequency/epoch hypotheses, not independent 20 ms recordings.

The original branch keeps the highest original GLRT-margin candidate per passing window. The refined branch re-evaluates candidates against recorded IQ using candidate-guided frequency and epoch refinement without orbit input, then selects the highest refined-score candidate. Failed refinements retain their original estimate and are counted in the refinement receipts. Frequencies are compared with the known 4.4 microsecond pilot alias period, approximately 227.273 kHz.

The refinement performs three bounded iterations. The first checks the saved frequency and its two neighboring alias centers at the saved epoch. Later iterations refine fractional epoch around the current best estimate and recenter frequency. A trial must return finite scores and remain within 1 kHz of its center modulo the alias period; the largest GLRT margin wins, with the previous best retained as a candidate. This uses IQ evidence rather than nudging measurements toward an orbit prediction. It is not an exhaustive search for new signals that were absent from the original candidate list.

Refinement can change both a candidate's frequency and which candidate wins a window. Consequently the original/refined comparison measures the total downstream effect of refinement and winner selection, not merely a frequency correction applied to an otherwise fixed dataset. Calibration and satellite selection are rerun separately for the two branches.

The final position fit uses all associated top-one windows in that branch. It does not use every raw candidate, and it does not include unassociated windows as additional negative evidence. GLRT margin selects a winner but is not itself the final likelihood weight. Every retained observation has unit weight before soft satellite/clutter responsibilities are computed.

## Calibration and satellite selection

Calibration uses the full scan at the known roof, with receiver offsets, drifts, a smooth receiver baseline, RF dependence, and satellite timing. Initialization uses track shapes and multiple timing starts; it does not transfer a previous scan's estimated position. Calibration must pass its convergence checks before downstream association is accepted.

The association stage searches the visible candidate bank with satellite timing bounded to plus or minus 20 seconds, a 600 Hz matching tolerance, and at least ten supporting peaks for a candidate. Greedy additions are followed by removal and replacement passes. Its discrete selection objective is:

`association score = number of assigned windows − 10 × number of selected satellites`.

This is distinct from the final probabilistic localization loss. A larger association score or a higher coverage fraction does not by itself establish more accurate satellite identities or position.

Within each original/refined branch, fitted-c associations determine a frozen set of observations, satellite trajectories, and receiver baseline. All position-score, cone, and final RF arms use those same inputs. Thus the final `c = 0` arm tests removing the additional RF coefficient at positioning; it is not an end-to-end pipeline in which RF dependence was forbidden during upstream calibration and selection.

## Final position model and loss

After subtracting the fixed receiver baseline, the predicted frequency for observation i and satellite s is:

`prediction(i,s) = orbit_Doppler(s, x, t_i + tau + delta_s, F_i)`

`                 + a_RX + b_RX × (t_i − 150 s) + c × (F_i − F_ref) / 1 GHz`.

Here x is horizontal position, tau is a common orbit time shift, delta_s is a satellite-relative time shift, and a_RX and b_RX are additional receiver offsets and linear drifts. The coefficient c is learned in the fitted-c arm and fixed to zero in the other arm. Doppler is evaluated at each observation's RF frequency.

The final loss is a conditional finite-set likelihood rather than fixed-owner least squares. Each retained window can share soft responsibility among the selected satellites and clutter. Only the selected satellite set participates, so a discarded catalog alternative cannot receive responsibility in this final fit.

For window g, let q_gs be the detection probability, A the alias period in Hz, phi_A the alias-aware Gaussian frequency density, and lambda the clutter rate. The singleton likelihood can be written:

`P0_g = exp(−lambda) × product_s(1 − q_gs)`

`H_g = lambda / A + sum_s[q_gs / (1 − q_gs) × phi_A(residual_gs; sigma)]`

`L_g = P0_g / (1 − P0_g) × H_g`.

The minimized objective is:

`J = −sum_g log(L_g) + 0.5 × (tau / sigma_common)^2`

`    + 0.5 × sum_s(delta_s / sigma_relative)^2`.

Without cones, q_gs equals the model's detection budget divided by the selected satellite count, multiplied by the existing hard visibility gate. With cones, a support-aware receiver preference tilts those probabilities while preserving the window's total detection mass. Cone strength is 0.5 and the probability floor is 0.1. The hard horizon rule is identical in both arms: the comparison does not simultaneously replace it with a smooth horizon model.

| Setting | T1-AT original score C0 | V16 |
| --- | ---: | ---: |
| Frequency Gaussian sigma | 200 Hz | 125 Hz |
| Detection budget | 0.8 | 1.6 |
| Clutter rate | 2 | 0.5 |
| Common timing prior sigma | 10 s | 3 s |
| Satellite-relative timing prior sigma | 1 s | 0.15 s |
| Common timing hard bound | ±10 s | ±10 s |
| Total satellite timing hard bound | ±20 s | ±20 s |
| Horizontal search radius | 4 km | 4 km |

Analytic gradients include frequency residual derivatives with respect to position, timing, receiver terms, and c. The cone arm also differentiates its geometric preference. Its zero-strength score/gradient parity and nonzero finite-difference derivatives are tested. A Fisher approximation preconditions optimization; it is not a certificate that a nonconvex search has found the global minimum.

## Search budget and convergence

Every final arm receives fresh association-timing and zero-timing roof starts, four cardinal probes at 3.2 km, and three local starts comprising the roof fit and the two best probes by objective. The roof-start budgets are 5 seconds each; probe budgets are 1 second each; local starts receive 8 seconds each; polishing receives 15 seconds. Unconverged solutions can additionally receive 20 seconds of SLSQP and 10 seconds of Fisher continuation. These are matched maximum budgets, not guarantees of identical iteration counts on a shared host.

Solutions are selected by their own objective, never by proximity to the known roof. A saved fit is converged only when its checked constrained stationarity measure is at most 0.001 and position was not fixed. A result at 4 km is a boundary solution, not an unconstrained minimum. Converged interior solutions can still occupy different local basins.

Execution batches have wall-clock limits separate from these numerical budgets. An interrupted batch is pending work, not a scientific result. Completed arm files are retained; refinement resumes from visit checkpoints. The report counts saved, converged, boundary, and missing cases separately.

## Interpretation and limitations

Position error is horizontal distance from the best-found location to the reference roof. Coverage is assigned top-one windows divided by passing windows from that measurement branch. Posterior-weighted frequency RMS describes fit quality, not absolute localization accuracy. These quantities answer different questions and are reported separately.

The paired effect of a switch is computed within the same scan with every other factor fixed. Negative position-error change means improvement. Comparisons exclude incomplete pairs, explicitly count unconverged pairs, and do not subtract medians from different available scan subsets. Repeated variants of one scan are not independent observations.

All calibration and position fits use their full designated data, with no holdout folds in this experiment. Upstream calibration and association are conditioned on the known roof. Therefore the position results are exploratory conditional localization diagnostics, not blind geolocation or held-out validation. V16 was developed on earlier scans, but this does not remove the known-location conditioning in the new pipeline.

A better in-sample frequency score cannot establish better position. Raw negative log likelihoods are also not comparable across T1-AT and V16 because the likelihood widths, detection/clutter parameters, and priors differ. The study should not declare a winning configuration until the fixed cohort has been evaluated and convergence limitations are included.

## Reproduction and evidence

The frozen `protocol.json` records the cohort digest, scientific source digests, settings, and search budgets. `results.csv` contains every planned position case, including missing ones. `paired-changes.csv` contains within-scan comparisons. Each saved fit links its exact input arrays, calibration and association receipts, optimization starts, objective, convergence diagnostics, and source hashes. The original and refined branch observations remain distinct.

Run `summarize_factorial.py` from the study directory's repository to refresh the figures, tables, and this report from saved results. `run_factorial_bounded.py` resumes missing position arms; `run_bounded.py` handles checkpointed export, orbit-bank, refinement, calibration, and association stages. Neither command requests new RF collection. The source files and scientific protocol must remain unchanged when resuming this experiment; a scientific change requires a separate version.

The factorial runner also accepts `--refinements original` or `--refinements refined` to schedule one measurement branch independently. This allows original-data comparisons to proceed while IQ refinement runs. It changes execution order only: the full report retains all 256 planned cases, and the other branch remains pending rather than being removed from the denominator.


## Downloads

[All cases CSV](results.csv) · [Paired changes CSV](paired-changes.csv) · [Frozen protocol](protocol.json) · [Report evidence summary](report-evidence.json) · [Markdown report](report.md)

## Optimizer continuation experiment

[Separate continuation report](continuation-v1/report.md) tests whether additional optimization resolves provisional fits without changing data or the model. Its results do not overwrite the fixed-budget figures above. Lower loss and lower position error are evaluated separately.

![Position and objective changes after optimizer continuation](continuation-v1/continuation-effects.png)

[Continuation scorecard](continuation-v1/scorecard.md) compares identical complete scan cohorts while retaining boundary and unconverged results.

[Responsibility audit](continuation-v1/responsibility-audit.md) separates satellite-to-satellite changes from transitions to or from clutter at the original and continued solutions.

[Equal-budget optimizer scaling pilot](optimizer-scaling-v1/report.md) compares ordinary and per-window-scaled SLSQP, with unscaled convergence checks. [Local gradient checks](../gradient-check.md) document the sampled derivative audit at the difficult R100-02 continuation point.

[Optimizer assessment](../optimizer-assessment.md) summarizes the continuation, scaling, and matched-polish findings without replacing baseline results.
