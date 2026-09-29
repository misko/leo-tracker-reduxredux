# Partial receiver timing: sigma = 2.0 seconds

This is one completed batch of the predeclared 0.1/0.5/2-second sensitivity study, not completion of all three strengths. One common location is fitted with separate RX0/RX1 timings per recording. A quadratic penalty shrinks recording-specific RX timing differences toward their fitted common mean. The mean is not shrunk toward zero. No strength is selected from reference error.

**18/18 selected solutions pass the audit.** Against the one-timing baseline, 10/18 have lower location error and 16/18 improve matched held Doppler prediction. Against independent receiver timings, the corresponding counts are 13/18 and 5/18. Held scores contain no regularization penalty.

| Dataset | Scans | Audited / planned | One-timing median (m) | Independent RX median (m) | Partial-pooling median (m) | Audited sub-km sets |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 4 | 3/3 | 2,590.063 | 2,724.293 | 2,723.955 | 0 |
| DS7 | 8 | 3/3 | 2,063.706 | 2,048.119 | 2,047.988 | 0 |
| DS8 | 4 | 3/3 | 2,260.918 | 2,009.576 | 2,010.056 | 1 |
| DS8 | 8 | 3/3 | 1,762.028 | 1,200.779 | 1,200.434 | 0 |
| DS9 | 4 | 3/3 | 1,167.327 | 865.315 | 864.958 | 2 |
| DS9 | 8 | 3/3 | 869.695 | 818.401 | 818.060 | 2 |

Medians are joint estimates across early/middle/late scan sets, not single-scan medians. Complete partial-pooling medians require all three selected fits to pass. Baseline columns use the matching validated subset if a batch is incomplete. Four-scan sets are nested within eight-scan sets.

![All panel comparisons](comparison-s200.png)

| Panel | One timing (m) | Independent RX (m) | Partial pooling (m) | Held gain vs one timing (nats) | Held gain vs independent RX (nats) | Audit |
|---|---:|---:|---:|---:|---:|---|
| DS7_early_4 | 2,864.858 | 2,943.416 | 2,943.375 | +3.446 | +0.001 | Pass |
| DS7_early_8 | 2,287.191 | 2,277.528 | 2,277.509 | +14.941 | +0.004 | Pass |
| DS7_middle_4 | 2,590.063 | 2,724.293 | 2,723.955 | +27.777 | -0.008 | Pass |
| DS7_middle_8 | 1,606.608 | 1,185.607 | 1,185.590 | +240.431 | -0.022 | Pass |
| DS7_late_4 | 1,414.224 | 1,310.562 | 1,310.542 | +19.615 | +0.003 | Pass |
| DS7_late_8 | 2,063.706 | 2,048.119 | 2,047.988 | +28.030 | -0.007 | Pass |
| DS8_early_4 | 1,065.224 | 905.451 | 905.372 | +72.873 | -0.012 | Pass |
| DS8_early_8 | 1,390.877 | 1,153.776 | 1,154.370 | +162.801 | -0.048 | Pass |
| DS8_middle_4 | 2,260.918 | 2,009.576 | 2,010.056 | +50.549 | -0.004 | Pass |
| DS8_middle_8 | 2,084.608 | 2,131.008 | 2,131.188 | +59.987 | +0.015 | Pass |
| DS8_late_4 | 3,467.535 | 3,542.454 | 3,541.166 | +39.081 | -0.005 | Pass |
| DS8_late_8 | 1,762.028 | 1,200.779 | 1,200.434 | +62.750 | -0.113 | Pass |
| DS9_early_4 | 2,117.272 | 2,240.652 | 2,240.659 | -5.635 | +0.001 | Pass |
| DS9_early_8 | 682.990 | 818.401 | 818.060 | +112.734 | -0.021 | Pass |
| DS9_middle_4 | 750.643 | 865.315 | 864.958 | +42.762 | -0.028 | Pass |
| DS9_middle_8 | 869.695 | 588.914 | 588.816 | +4.635 | -0.005 | Pass |
| DS9_late_4 | 1,167.327 | 853.339 | 854.209 | +43.641 | -0.040 | Pass |
| DS9_late_8 | 3,435.817 | 3,879.206 | 3,705.549 | -16.230 | -272.042 | Pass |

Training selects the greatest penalized score among successful interior starts with gradient infinity norm at most 0.01. The raw likelihood, penalty, and penalized objective remain separately recorded and checked. Scores across different strengths are not a hyperparameter-selection criterion.

72/72 starts qualify; 18/18 tied-baseline checks pass. Scoring verified 2,407 execution/input bindings. The maximum selected-fit derivative discrepancy is 1.82754e-05.

90 process receipts; 90 exit zero. Total job wall time 903.93 s, maximum 23.60 s, peak RSS 674,856 KiB. Optimizer qualification and numerical audit success are separate from process exit.


No failed start or audit was retried, removed or reclassified.

| Panel | Fitted mean RX1−RX0 (s) | RMS deviation from mean (s) | Penalty |
|---|---:|---:|---:|
| DS7_early_4 | -0.002218 | 0.064850 | 0.002103 |
| DS7_early_8 | +0.017833 | 0.147769 | 0.021836 |
| DS7_middle_4 | -0.034785 | 0.203234 | 0.020652 |
| DS7_middle_8 | -0.124132 | 0.599874 | 0.359849 |
| DS7_late_4 | +0.178507 | 0.179960 | 0.016193 |
| DS7_late_8 | +0.199657 | 0.211454 | 0.044713 |
| DS8_early_4 | -0.027112 | 0.292853 | 0.042881 |
| DS8_early_8 | +0.147321 | 0.252511 | 0.063762 |
| DS8_middle_4 | -0.177334 | 0.276555 | 0.038241 |
| DS8_middle_8 | -0.048961 | 0.314300 | 0.098785 |
| DS8_late_4 | -0.341789 | 0.686795 | 0.235844 |
| DS8_late_8 | +0.004740 | 0.872185 | 0.760707 |
| DS9_early_4 | -0.079537 | 0.066983 | 0.002243 |
| DS9_early_8 | -0.324584 | 0.468546 | 0.219535 |
| DS9_middle_4 | -0.293833 | 0.681553 | 0.232257 |
| DS9_middle_8 | +0.038812 | 1.369860 | 1.876517 |
| DS9_late_4 | +0.139340 | 0.563614 | 0.158830 |
| DS9_late_8 | -0.190510 | 0.303176 | 0.091916 |

The additional baseline-derived start can find a different optimum. Below are panels where its selected penalized score exceeds the best generic start by more than 0.001 nats. Initialization is training-selected; a higher training score need not give lower reference error.

| Panel | Selected minus generic training (nats) | Selected error (m) | Generic-only error (m) |
|---|---:|---:|---:|
| DS7_middle_4 | 4.391460 | 2,723.955 | 2,150.562 |
| DS7_middle_8 | 23.324887 | 1,185.590 | 1,101.414 |
| DS8_middle_8 | 41.934835 | 2,131.188 | 2,214.734 |
| DS9_late_8 | 9.145172 | 3,705.549 | 1,974.538 |

These timings are fitted nuisance parameters, not independent measurements of receiver clock offsets. Their dispersion is regularized, so it cannot be interpreted as a measured timing uncertainty.

On the same held observations in the first four scans, 0/9 audited eight-scan fits improve prediction over the four-scan fit. The median change is -26.940 nats.

The exposed unsurveyed reference, dependent scan sets and previously explored single site do not establish blind sub-km accuracy. The late DS9 eight-scan result is retained in every relevant aggregate. This timing model is separate from the fixed receiver-cone experiment; no combined improvement is claimed.

[Complete batch data](summary-s200.json), [receipts](resources-s200.json), [protocol](PROTOCOL.md), [frozen plan](plan.json), and [tests](tests.log). Existing output directories are immutable evidence. One bounded worker used cached inputs only; no RF collection, waveform reads, propagation or provider fetches.
