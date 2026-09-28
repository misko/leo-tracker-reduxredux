# Host full-inventory quality cohort

This saved-IQ host qualification uses 64 metadata-selected DS7 dwells: eight
lower and eight upper windows at each native rate. It spans eight recordings,
two per rate, and 1,408 receiver/probe windows. It is a portability and kernel
quality audit, not an ARM timing result or a recovery claim beyond this sealed
development cohort.

Baseline, unpruned-screen, and pruned-plus-screen variants completed every dwell
and window. Their per-window ordered audit has zero errors against the sealed
original repeat-0 baseline: all 11,264 candidates retained ordered identity and
the checked acquired/tracking CFO plus final exact/control/margin values.

| Rate | Dwells | Windows | Baseline positives | Variant positives | One-to-one matches | Positive windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.5 MS/s | 16 | 352 | 485 | 485 | 485 | 188 |
| 5 MS/s | 16 | 352 | 259 | 259 | 259 | 120 |
| 7.5 MS/s | 16 | 352 | 448 | 448 | 448 | 184 |
| 10 MS/s | 16 | 352 | 477 | 477 | 477 | 199 |
| Total | 64 | 1,408 | 1,669 | 1,669 | 1,669 | 691 |

There are zero misses and zero added positives. Denominators come from all
sealed baseline probes in the selected inventory, including every receiver and
every scheduled window, rather than only native-matched records.

Mean host kernel CPU time per receiver/probe was 290.586 ms for baseline,
171.541 ms for unpruned-screen, and 167.656 ms for pruned-plus-screen. Both
screen variants screened 461,064 conditioned bins and FP64-rechecked 12,988;
baseline rechecked all 461,064 bins. Detailed row outputs, manifests, and build
receipts are copied in `results/baseline64/`, `results/screen64/`, and
`results/pruned_screen64/`.

This selection deliberately uses the first eight saved windows per edge and
rate in the input receipt. It covers eight recordings and must not be read as a
broad 88-recording selection or a population runtime estimate. The separate ARM
timings supplied for the primary unpruned method are 2.7406 s versus 2.7454 s
for pruned-screen, which is effectively neutral in that measurement.
