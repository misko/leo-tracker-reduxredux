# Native receiver clocks improve held prediction without improving position

The DS22-019 native-clock extension improves held likelihood in both bands while worsening distance to the configured reference. Its better training frequency fit therefore is not merely an in-sample improvement. This comparison does not establish that the inferred position or satellite associations are correct. DS22's reference remains configured and unconfirmed.

| Case | Frozen state | Training NLL | Held CH1–8 NLL/window | Held CH1–4 NLL/window | Held CH5–8 NLL/window |
|---|---|---:|---:|---:|---:|
| 001 | Original C | 41529.962579 | 13.771388 | 12.963739 | 14.989152 |
| 001 | Native clock C | 41991.555740 | 13.715883 | 12.835191 | 15.043780 |
| 019 | Original C | 41281.479093 | 14.881720 | 14.562911 | 15.306462 |
| 019 | Native clock C | 40715.794380 | 13.511036 | 13.206521 | 13.916735 |

Lower NLL is better. Case 001 improves slightly overall, with improvement confined to the lower band; its upper-band held prediction worsens. Case 019 improves substantially in both bands. These views restrict the full-band fitted states; they are not independently fitted half-band models.

The previously sealed position comparison in `NATIVE_RECEIVER_CLOCK_RESULTS.md` worsened from 21.266493 to 29.257438 km for 001 and 142.113760 to 151.943354 km for 019. The new diagnostic reads no reference and changes no training selection. Better held frequency likelihood does not establish better localization. Position ambiguity, candidate associations, calibration/geography confounding, and reference validity remain possible explanations requiring distinct tests.

The 001 augmented cold-start search also retains a demonstrated optimization limitation: the original full-band winner with zero added clocks is feasible and has lower training objective than the selected augmented fit. This held comparison does not resolve that search limitation or compare global optima.

Both original six-start fit matrices and selected states were sealed before any held prediction. Each state replays its saved training objective within 1e-7 and passes frozen-calibration closure before held extraction. The original disjoint held partitions were retained: 805 windows for 001 (484 lower, 321 upper) and 737 for 019 (421 lower, 316 upper). Position, timing, candidate bank, fitted c and the learned clock/calibration functions remain frozen. Predictions evaluate those functions at each native branch timestamp. Band NLL sums reproduce full NLL within 1e-7. No held-based selection or optimizer call occurs.

Source `d0dddca0c`; two tests pass, including nonzero frozen-clock agreement at native branch times and rejection outside clock support; Ruff passes. The actual diagnostic completed in 97.177 seconds with 12 held predictions and zero optimizer calls. Receipts: `local/ds22-native-clock-held-v1`; report SHA256 `7a6bb24f7df346f45f0251fac43a2b3a322fffa285878de23d5ad672de38a922`.
