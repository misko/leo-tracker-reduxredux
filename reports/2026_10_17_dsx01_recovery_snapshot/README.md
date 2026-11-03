# DSX01: latest 15-window recovery and timing snapshot

Read-only summary of saved fitted-c endpoints. Recovery means association coverage, not verified satellite identity or validated position accuracy. No parameters were refitted. No validation-position information is used for model selection or initialization.

Expanded profile: 434/693 associated, up from 96/693. Seven windows restore ≥80% of originally missing associations, one restores 50–80%, six restore less than 50%, and window 003 remains unchanged at zero. Three windows reach complete association. The fixed-bank profile has six major restorations and 422/693 associations. Expansion regresses window 001 from 79/86 to 45/86; do not combine per-window maxima.

Net missing restored = (new associations − lost original associations) / originally missing. The 80% grouping is descriptive, not a preregistered success criterion.

| Window | Region | Original | Fixed | Expanded | Expanded new / lost | Net missing restored |
|---|---|---:|---:|---:|---:|---:|
| 001 | S01 RX1/CH4 40–100s | 13/86 | 79/86 | 45/86 | 37 / 5 | 43.8% |
| 002 | S01 RX1/CH2 50–75s | 1/35 | 11/35 | 13/35 | 13 / 1 | 35.3% |
| 003 | S01 RX1/CH2 170–190s | 0/27 | 0/27 | 0/27 | 0 / 0 | 0.0% |
| 004 | S02 RX1/CH1 65–100s | 6/44 | 10/44 | 11/44 | 8 / 3 | 13.2% |
| 005 | S02 RX1/CH3 95–127s | 1/33 | 31/33 | 33/33 | 32 / 0 | 100.0% |
| 006 | S02 RX2/CH2 150–200s | 12/72 | 33/72 | 36/72 | 26 / 2 | 40.0% |
| 007 | S03 RX1/CH4 0–40s | 16/54 | 54/54 | 54/54 | 38 / 0 | 100.0% |
| 008 | S03 RX1/CH4 175–210s | 8/50 | 48/50 | 48/50 | 40 / 0 | 95.2% |
| 009 | S03 RX1/CH5 175–200s | 4/34 | 34/34 | 34/34 | 30 / 0 | 100.0% |
| 010 | S04 RX2/CH5 75–110s | 2/46 | 25/46 | 33/46 | 32 / 1 | 70.5% |
| 011 | S04 RX2/CH3 110–140s | 9/43 | 15/43 | 11/43 | 6 / 4 | 5.9% |
| 012 | S04 RX1/CH3 125–175s | 14/66 | 16/66 | 27/66 | 15 / 2 | 25.0% |
| 013 | S05 RX1/CH3 40–60s | 1/28 | 22/28 | 23/28 | 22 / 0 | 81.5% |
| 014 | S05 RX1/CH4 250–280s | 3/39 | 11/39 | 32/39 | 29 / 0 | 80.6% |
| 015 | S05 RX1/CH2 110–140s | 6/36 | 33/36 | 34/36 | 28 / 0 | 93.3% |

![All windows](window-recovery.png)

![Timing histograms](satellite-timing-histogram.png)

Each histogram entry is one recording–satellite fit, not one observation. The same satellite may occur in multiple recordings. Both comparisons retain the same original cohort even if support is subsequently lost. Added expanded-bank candidates are excluded from these matched histograms and retained separately in the timing CSV. Total offsets are bounded at ±20 s; subtracting the common shift can put relative offsets beyond those bounds. Timing offsets can absorb geometry, calibration and identity errors; they do not independently measure satellite clock error or TLE age.

| Method | Total RMS (s), 215 pairs | Relative RMS (s), 215 pairs | Total abs(τ) ≥19 s |
|---|---:|---:|---:|
| Original | 9.39 | 9.15 | 2/215 |
| Exact profile: fixed candidates | 8.02 | 7.47 | 1/215 |
| Exact profile: expanded candidates | 7.94 | 7.50 | 1/215 |

Across complete scans, the expanded model gains 3,817 assignments but loses 791 original assignments. Several position-reference distances remain above 100 km. These development results do not establish generalization to new positions. The next validation must keep position-independent initialization and data-derived candidate selection, and measure held observations with correct training-only band calibration.

Source recording IDs and denominators are frozen in the dataset regions CSV. Controlled c=0 comparisons and numerical audit details remain in the [iteration 2 report](../2026_10_16_dsx01_iteration2/README.md).
