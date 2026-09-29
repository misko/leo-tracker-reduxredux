# Partial receiver timing: sigma = 0.5 seconds

This is one completed batch of the predeclared 0.1/0.5/2-second sensitivity study, not completion of all three strengths. One common location is fitted with separate RX0/RX1 timings per recording. A quadratic penalty shrinks recording-specific RX timing differences toward their fitted common mean. The mean is not shrunk toward zero. No strength is selected from reference error.

**17/18 selected solutions pass the audit.** Against the one-timing baseline, 9/17 have lower location error and 15/17 improve matched held Doppler prediction. Against independent receiver timings, the corresponding counts are 10/17 and 6/17. Held scores contain no regularization penalty.

| Dataset | Scans | Audited / planned | One-timing median (m) | Independent RX median (m) | Partial-pooling median (m) | Audited sub-km sets |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 4 | 3/3 | 2,590.063 | 2,724.293 | 2,718.762 | 0 |
| DS7 | 8 | 3/3 | 2,063.706 | 2,048.119 | 2,046.052 | 0 |
| DS8 | 4 | 3/3 | 2,260.918 | 2,009.576 | 2,017.196 | 1 |
| DS8 | 8 | 3/3 | 1,762.028 | 1,200.779 | 1,405.676 | 0 |
| DS9 | 4 | 3/3 | 1,167.327 | 865.315 | 869.555 | 2 |
| DS9 | 8 | 2/3 | 776.343 | 703.658 | Incomplete | 1 |

Medians are joint estimates across early/middle/late scan sets, not single-scan medians. Complete partial-pooling medians require all three selected fits to pass. Baseline columns use the matching validated subset if a batch is incomplete. Four-scan sets are nested within eight-scan sets.

![All panel comparisons](comparison-s050.png)

| Panel | One timing (m) | Independent RX (m) | Partial pooling (m) | Held gain vs one timing (nats) | Held gain vs independent RX (nats) | Audit |
|---|---:|---:|---:|---:|---:|---|
| DS7_early_4 | 2,864.858 | 2,943.416 | 2,942.778 | +3.447 | +0.001 | Pass |
| DS7_early_8 | 2,287.191 | 2,277.528 | 2,277.178 | +15.005 | +0.068 | Pass |
| DS7_middle_4 | 2,590.063 | 2,724.293 | 2,718.762 | +27.648 | -0.137 | Pass |
| DS7_middle_8 | 1,606.608 | 1,185.607 | 1,090.625 | +186.818 | -53.635 | Pass |
| DS7_late_4 | 1,414.224 | 1,310.562 | 1,310.248 | +19.658 | +0.047 | Pass |
| DS7_late_8 | 2,063.706 | 2,048.119 | 2,046.052 | +27.920 | -0.118 | Pass |
| DS8_early_4 | 1,065.224 | 905.451 | 904.163 | +72.688 | -0.198 | Pass |
| DS8_early_8 | 1,390.877 | 1,153.776 | 1,163.267 | +162.052 | -0.797 | Pass |
| DS8_middle_4 | 2,260.918 | 2,009.576 | 2,017.196 | +50.485 | -0.068 | Pass |
| DS8_middle_8 | 2,084.608 | 2,131.008 | 2,133.851 | +60.206 | +0.235 | Pass |
| DS8_late_4 | 3,467.535 | 3,542.454 | 3,521.610 | +38.997 | -0.089 | Pass |
| DS8_late_8 | 1,762.028 | 1,200.779 | 1,405.676 | +100.405 | +37.543 | Pass |
| DS9_early_4 | 2,117.272 | 2,240.652 | 2,240.766 | -5.625 | +0.011 | Pass |
| DS9_early_8 | 682.990 | 818.401 | 812.985 | +112.408 | -0.347 | Pass |
| DS9_middle_4 | 750.643 | 865.315 | 859.570 | +42.332 | -0.458 | Pass |
| DS9_middle_8 | 869.695 | 588.914 | 1,390.371 | -1.203 | -5.843 | Pass |
| DS9_late_4 | 1,167.327 | 853.339 | 869.555 | +42.699 | -0.983 | Pass |
| DS9_late_8 | 3,435.817 | 3,879.206 | 3,707.271 | -15.726 | -271.538 | Failed; values unvalidated |

Training selects the greatest penalized score among successful interior starts with gradient infinity norm at most 0.01. The raw likelihood, penalty, and penalized objective remain separately recorded and checked. Scores across different strengths are not a hyperparameter-selection criterion.

71/72 starts qualify; 18/18 tied-baseline checks pass. Scoring verified 2,409 execution/input bindings. The maximum selected-fit derivative discrepancy is 3.28767e-05.

90 process receipts; 90 exit zero. Total job wall time 892.06 s, maximum 22.92 s, peak RSS 675,372 KiB. Optimizer qualification and numerical audit success are separate from process exit.

- Retained unqualified start: DS7_middle_8_s050 / nested: ABNORMAL: .

No failed start or audit was retried, removed or reclassified.

| Panel | Fitted mean RX1−RX0 (s) | RMS deviation from mean (s) | Penalty |
|---|---:|---:|---:|
| DS7_early_4 | -0.002361 | 0.064287 | 0.033063 |
| DS7_early_8 | +0.017463 | 0.146715 | 0.344405 |
| DS7_middle_4 | -0.036195 | 0.198865 | 0.316378 |
| DS7_middle_8 | -0.018580 | 0.517949 | 4.292332 |
| DS7_late_4 | +0.177908 | 0.178646 | 0.255314 |
| DS7_late_8 | +0.199269 | 0.209406 | 0.701614 |
| DS8_early_4 | -0.027010 | 0.290454 | 0.674908 |
| DS8_early_8 | +0.147992 | 0.249161 | 0.993299 |
| DS8_middle_4 | -0.176056 | 0.272378 | 0.593517 |
| DS8_middle_8 | -0.048873 | 0.309307 | 1.530736 |
| DS8_late_4 | -0.343185 | 0.675743 | 3.653025 |
| DS8_late_8 | -0.248443 | 0.526052 | 4.427692 |
| DS9_early_4 | -0.079549 | 0.066365 | 0.035234 |
| DS9_early_8 | -0.323677 | 0.462343 | 3.420173 |
| DS9_middle_4 | -0.296541 | 0.677447 | 3.671473 |
| DS9_middle_8 | -0.258749 | 0.593262 | 5.631351 |
| DS9_late_4 | +0.135383 | 0.547922 | 2.401745 |

The additional baseline-derived start can find a different optimum. Below are panels where its selected penalized score exceeds the best generic start by more than 0.001 nats. Initialization is training-selected; a higher training score need not give lower reference error.

| Panel | Selected minus generic training (nats) | Selected error (m) | Generic-only error (m) |
|---|---:|---:|---:|
| DS7_middle_4 | 4.782922 | 2,718.762 | 2,154.140 |
| DS8_middle_8 | 47.663424 | 2,133.851 | 2,218.044 |

These timings are fitted nuisance parameters, not independent measurements of receiver clock offsets. Their dispersion is regularized, so it cannot be interpreted as a measured timing uncertainty.

On the same held observations in the first four scans, 0/8 audited eight-scan fits improve prediction over the four-scan fit. The median change is -31.017 nats.

The exposed unsurveyed reference, dependent scan sets and previously explored single site do not establish blind sub-km accuracy. The late DS9 eight-scan result is retained in every relevant aggregate. This timing model is separate from the fixed receiver-cone experiment; no combined improvement is claimed.

[Complete batch data](summary-s050.json), [receipts](resources-s050.json), [protocol](PROTOCOL.md), [frozen plan](plan.json), and [tests](tests.log). Existing output directories are immutable evidence. One bounded worker used cached inputs only; no RF collection, waveform reads, propagation or provider fetches.
