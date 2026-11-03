# DSX01 iteration 3: controlled recovery experiments

All results retain the same 15 windows, 693 window observations and 20,084 complete-scan observations. These are full-data warm development comparisons; identities are hypotheses, and configured-reference distances are not surveyed truth. Station coordinates do not seed or select any fit. Incomplete methods are excluded from aggregate plots and listed in summary.json.

| Arm | Method | Full associations | Window associations | ≥80% net-restored windows | New / lost original support | Assigned RMS Hz | Strict endpoints |
|---|---|---:|---:|---:|---:|---:|---:|
| fitted-c | Original | 11222/20084 | 96/693 | 0/15 | 0 / 0 | 160.29 | 4/5 |
| fitted-c | Exact profile, fixed candidates | 13784/20084 | 422/693 | 6/15 | 3304 / 742 | 155.82 | 4/5 |
| fitted-c | Exact profile, expanded candidates | 14248/20084 | 434/693 | 7/15 | 3817 / 791 | 151.88 | 4/5 |
| fitted-c | Fixed profile, timing prior 1 s | 13366/20084 | 347/693 | 4/15 | 2995 / 851 | 154.94 | 3/5 |
| fitted-c | Fixed profile, timing prior 0.5 s | 12302/20084 | 339/693 | 5/15 | 2257 / 1177 | 159.70 | 3/5 |
| fitted-c | Fixed profile, causal Space-Track | 13793/20084 | 371/693 | 5/15 | 3496 / 925 | 155.50 | 5/5 |
| fitted-c | Fixed profile + frequency-width continuation | 14173/20084 | 455/693 | 7/15 | 3988 / 1037 | 153.16 | 2/5 |
| fitted-c | Fixed profile + extra 125 Hz continuation | 13784/20084 | 422/693 | 6/15 | 3304 / 742 | 155.82 | 4/5 |
| zero-c | Exact profile, fixed candidates | 12311/20084 | 292/693 | 3/15 | 3529 / 2440 | 169.40 | 3/5 |
| zero-c | Exact profile, expanded candidates | 12617/20084 | 337/693 | 3/15 | 3773 / 2378 | 165.72 | 4/5 |
| zero-c | Fixed profile, timing prior 1 s | 11697/20084 | 304/693 | 3/15 | 3029 / 2554 | 169.92 | 4/5 |
| zero-c | Fixed profile, timing prior 0.5 s | 10298/20084 | 299/693 | 3/15 | 2345 / 3269 | 173.56 | 5/5 |
| zero-c | Fixed profile, causal Space-Track | 12109/20084 | 288/693 | 2/15 | 3483 / 2596 | 170.49 | 4/5 |
| zero-c | Fixed profile + frequency-width continuation | 12535/20084 | 357/693 | 3/15 | 3928 / 2615 | 167.81 | 4/5 |
| zero-c | Fixed profile + extra 125 Hz continuation | 12372/20084 | 313/693 | 3/15 | 3575 / 2425 | 169.25 | 3/5 |

Width continuation reaches 455/693 window associations versus its matched extra-125-Hz control’s 422/693, but replaces more original full-scan support and has only two strict raw endpoints. Expanded profile reaches 434/693 and retains more complete-scan assignments. No method wins all criteria. See [the measured findings](FINDINGS.md) for the tradeoffs and why the recovery/generalization goal remains active.

Assigned RMS uses each variant’s own associated set and can improve through selection. New/lost support and the all-observation CDF expose this change. Original fitted-c is a context baseline for both arms; c=0 comparisons require their matched c=0 method controls. Total objectives across different priors are not comparable.

![All 15 window counts](window-coverage.png)

![Coverage and position CDFs](performance-cdfs.png)

![Timing histograms](timing-histograms.png)

Causal Space-Track changes only S01/S05. S02–S04 already used the identical latest-causal Space-Track digest, so their original fixed-profile receipts are exact identity controls. Both providers retain the same selected candidate IDs, original warm seed, fixed band contrasts, priors and 1000-call/120-second profile allowance. This is not a rerun of candidate discovery or an end-to-end provider comparison.

Frequency-width continuation starts at the saved fixed profile, uses intermediate widths 1000→500→250→125 Hz, and evaluates final counts, RMS and selection at the original 125 Hz. It has an additional 1000-objective/120-second allowance after the profile. Its matched control uses that same extra allowance entirely at 125 Hz. Thus comparisons to a profile alone combine algorithm and added budget. These curves use the raw algorithm endpoints uniformly across all five sources; supplementary numerical finishing is separate.

Training-only calibration and support-portfolio pilots are documented in their component directories and are not pooled with these full five-source protocols unless complete.

[Window-level CSV](windows.csv) · [Source-level CSV](sources.csv) · [Protocol](PROTOCOL.md)
