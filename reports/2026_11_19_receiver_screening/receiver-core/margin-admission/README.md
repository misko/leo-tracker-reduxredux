# Fractional-margin admission

One global cutoff of **0.23467635869958722** removed **19.1%** of admitted wide candidates and reduced summed position CPU by **6.5%** across four held recordings. Both receiver versions published both calibration arms on all four recordings. The higher cutoff increased the largest position error from **0.793 to 2.391 km** at `c = 0` and from **0.806 to 1.948 km** with fitted `c`. DS26-0014 accounted for the deterioration. The trial supports keeping the 0.025 gate for this receiver.

## Held positions

Values in each cell are original gate → calibrated gate. All cases offered the same roof search region to both receivers.

| Recording | Position error, `c = 0` (km) | Position error, fitted `c` (km) | Conditional RF RMS, `c = 0` (Hz) | Conditional RF RMS, fitted `c` (Hz) |
|---|---:|---:|---:|---:|
| DS26-0237 | 0.382 → 0.277 | 0.323 → 0.216 | 92.54 → 90.51 | 92.43 → 90.40 |
| DS29-0174 | 0.793 → 0.788 | 0.806 → 0.801 | 99.87 → 100.62 | 100.04 → 100.77 |
| DS26-0014 | 0.472 → 2.391 | 0.755 → 1.948 | 97.39 → 95.82 | 97.57 → 95.69 |
| DS29-0127 | 0.756 → 0.722 | 0.721 → 0.682 | 75.83 → 73.22 | 75.90 → 73.28 |
| Median (n = 4) | 0.614 → 0.755 | 0.738 → 0.741 | 94.96 → 93.16 | 95.00 → 93.05 |
| P95 (n = 4) | 0.787 → 2.150 | 0.798 → 1.776 | | |

The proportion within 1 km went from 4/4 to 3/4 in each calibration arm. DS26-0014's conditional frequency fits improved by 1.57 and 1.88 Hz while its geographic errors increased. Conditional RMS uses each receiver's selected support. The capture-era baseline v5 medians were 0.753 and 0.742 km on these records. See the two position charts for all four original v5 roles. [Position scores](scores.csv) · [Capture-era v5 scores](capture-era-v5.csv) · [`c = 0` chart](charts/c0/wide-margin-admission.png) · [Fitted `c` chart](charts/fitted_c/wide-margin-admission.png)

## Teacher agreement

The threshold was calibrated once using equal weights for two development recordings. DS26-0036 retained 3,462 positive probes out of 13,530 (teacher 3,395). DS29-0082 retained 1,820 out of 9,736 (teacher 1,868). A lower threshold wins an equal-prevalence tie. The original 0.025 floor made this a removal-only experiment. [Prespecified protocol](PROTOCOL.md) · [Threshold lock](threshold-lock.json)

The 53,290 held valid probes included 14,134 capture-era positives. The original wide gate admitted 14,930 probes and the calibrated gate admitted 14,118. Raising the cutoff to 0.10 removed just 57 positive probes on the same inputs. At the calibrated cutoff, admission among capture-era negatives dropped from 4.94% to 3.45%, while recall of capture-era positives dropped from 91.93% to 90.32%. All four elapsed-capture quarters showed the same tradeoff. Pooled teacher recall fell by 1.40 to 1.83 percentage points across the four quarters. The teacher is the prior capture-era detector's output. These rates measure agreement with that detector. [Agreement by recording, cutoff and elapsed quarter](teacher-agreement.csv) · [Operating-point chart](teacher-agreement.png)

## Same-count allocation control

On DS29-0127 the prespecified hash control admitted 8,598 candidates, matching the scalar arm. Hash selection left 2,781 positive probes compared with 2,677 for the scalar, and published both calibrations. Its errors were 0.761 and 0.713 km, versus 0.722 and 0.682 km for the scalar. Conditional RF RMS was 87.54 and 87.58 Hz with hash selection versus 73.22 and 73.28 Hz with scalar selection. Position CPU was 45.81 s with hash selection versus 51.08 s with scalar selection. This single control measures an allocation difference at fixed candidate count on DS29-0127. [Allocation prediction lock](thinning-lock.json) · [`c = 0` chart](charts/c0/wide-margin-allocation-control.png) · [Fitted `c` chart](charts/fitted_c/wide-margin-allocation-control.png)

## Matched execution

The replay reused the complete sealed wide GLRT factors. The scalar reads only the native fractional margin and ordinary admission flag. All ranks, scores, probes, hardware clocks, configurations, causal TLE history, tile offers and solver settings were byte- or value-checked. The original gate reproduced all eight earlier wide coordinate and RF pairs exactly. [Input audit](input-audit.json) · [Control parity](scores.json)

The held post-GLRT runs used one core each at nice 10, a 512 MiB cgroup with no swap and a 170 s worker limit. There were no timeouts, OOMs or swap. Summed CPU was 228.62 → 213.85 s and median worker wall time was 52.43 → 50.89 s. Individual CPU improved on three recordings and increased from 50.46 to 51.08 s on DS29-0127. Highest cgroup charge across each group was 397.8 → 391.6 MiB. No IQ decoding, new detector execution, or physical acquisition timing enters those measurements. The four held recordings were from the same physical roof. [Resource receipts](resources.csv) · [Sealed predictions](prediction-lock.json)

The first launch failed at module import on every worker. Its exact launcher and receipts are archived. The corrected launcher sets the worker's initial directory and retains the exact predeclared plan and threshold. [Initial receipts](initial-infrastructure/prediction-lock.json) · [Launcher amendment](execution-lock.json)
