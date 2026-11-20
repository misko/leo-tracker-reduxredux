# One stock antenna per RF visit on the complete roof roster

This post-acquisition qualification uses the original stock four-center probe arrays for one antenna on each valid visit. Each RF’s first valid visit selects physical RX0, and each subsequent valid visit to that RF switches the selected antenna. The suppressed antenna’s physical slot remains present with an empty candidate array. The saved IQ still contains both antenna streams. Capture exclusions and original clock, RF, catalogue and tile bindings are retained. [Protocol](PROTOCOL.md) · [Frozen sources and fit schedule](plan.json)

All 22 complete stock native documents authenticated. Across **146,268 valid visits**, the projection preserved **292,536 physical probe slots** and retained **704,103 of 1,409,765** candidate rows. **47,699 of 95,305** original gated probes remained. Two stock archive copies preserve inputs initially available only in local scratch. The source archive records the exact as-run projection code. The shared projection later accepted capture-era factors that lacked a detector-build digest. All 22 prepared native documents and schedule hashes remained byte-identical under the updated shared code. [Per-recording probe and RF receipts](packet-audit.json) · [Source and projection SHA verification](projection-parity-lock.json)

Each case runs the installed compact phase-release receiver with both calibration settings on the same projected observations. The 210-second worker uses one of two fixed host cores, 512 MiB and zero swap. Runtime belongs to this post-acquisition fit. The full-IQ single-antenna study measures acquisition timing on its own fixtures and binds its selected-lane output to the archive projection on matching captures. [Full-IQ acquisition study](../one-lane-whole/README.md)

The two overlap captures, DS26-0014 and DS29-0082, produced byte-identical complete native documents in the direct one-context IQ replay and the archive projection. The comparison covered 6,772 and 4,868 valid visits, respectively. DS29-0082’s 1,904 capture exclusions remained identical. Both fitted coordinates and conditional RF RMS were identical under each calibration setting. This check establishes the representation and exact compact inputs on those two captures. [Direct and projected input and fit parity](direct-iq-parity.json)

## Position

All 22 compact fits published in both calibration arms. The projected one-antenna receiver was within either the +5% or +10% allowance above original no-repair v5 on **8/22** cases in each arm. Full stereo stock reached **12/22** and **13/22** in the zero arm, and **13/22** at either allowance in the fitted arm. The per-case rows also give the signed percent difference and symmetric ±5% and ±10% counts. The original four v5 options use capture-era factors. [Per-case comparisons](scores.csv) · [Group and reference summaries](summary.csv)

| Cohort | One-antenna zero median / P95 | One-antenna fitted median / P95 | Within +10%, zero / fitted |
|---|---:|---:|---:|
| All 22 | 0.855 / 1.786 km | 0.815 / 1.797 km | 8/22 / 8/22 |
| DS26 | 0.924 / 1.936 km | 1.032 / 1.940 km | 3/11 / 3/11 |
| DS29 | 0.765 / 1.743 km | 0.695 / 1.732 km | 5/11 / 5/11 |
| Earlier difficult six | 0.871 / 1.793 km | 0.890 / 1.832 km | 0/6 / 0/6 |
| New lower-edge pair | 1.093 / 1.680 km | 1.084 / 1.663 km | 1/2 / 1/2 |

Full-stereo stock on all 22 had position median/P95 **0.774/1.543 km** at zero calibration and **0.776/1.437 km** with fitted calibration. Original no-repair v5 had **0.739/1.760 km** and **0.724/1.769 km**, respectively. The complete location roster is one surveyed roof. [Zero-calibration figures](charts/c0/modifications.pdf) · [Fitted-calibration figures](charts/fitted_c/modifications.pdf)

## Conditional RF and compact runtime

One-antenna conditional RF RMS median/P95 was **90.680/109.989 Hz** at zero calibration and **90.549/110.112 Hz** with fitted calibration. Full-stereo stock had **85.483/104.123 Hz** and **85.497/104.113 Hz**. All **47,699** retained gated probes appear in the worker observation counts. [RF and fit-score columns](scores.csv)

The actual compact worker's wall median/P95 was **52.96/72.74 s** across the 22 cases. Its CPU median/P95 was **44.50/58.89 s**, and peak charged memory stayed below **393 MiB**. Both calibration arms share this worker timing. The native detector-time fields are blank for the projected roster. The direct IQ pair supplies its separately measured acquisition clocks. [Service timing and observed support](resources.csv) · [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json)
