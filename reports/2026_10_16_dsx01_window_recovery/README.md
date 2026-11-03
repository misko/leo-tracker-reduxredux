# DSX01: 15-window recovery and satellite timing histograms

This is a read-only analysis of the saved full-data, fitted-c endpoints. No model was refitted. “Recovered” below means increased satellite-association coverage, not independently verified satellite identity or a validated localization improvement. All five A endpoints remain nonstationary.

Model A improves counts in 8/15 windows; 6 have unchanged counts and 1 worsens. Four windows restore at least 80% of their originally missing associations on a net basis; one reaches 100% window coverage. This 80% threshold is a descriptive grouping, not a pre-registered success gate. Across all 693 observations, coverage is 96 → 253: 160 newly assigned, 3 lost, net +157. That closes 26.3% of the original 597 missing associations. B, C and equal-budget continuation leave all 15 window counts unchanged.

![All 15 window counts](window-recovery.png)

| Window | Source / region | Before | A after | Newly assigned / originally missing | Lost | Net missing restored |
|---|---|---:|---:|---:|---:|---:|
| 001 | S01 RX1/CH4 40–100s | 13/86 | 74/86 (86.0%) | 62/73 | 1 | 83.6% |
| 002 | S01 RX1/CH2 50–75s | 1/35 | 2/35 (5.7%) | 1/34 | 0 | 2.9% |
| 003 | S01 RX1/CH2 170–190s | 0/27 | 0/27 (0.0%) | 0/27 | 0 | 0.0% |
| 004 | S02 RX1/CH1 65–100s | 6/44 | 6/44 (13.6%) | 0/38 | 0 | 0.0% |
| 005 | S02 RX1/CH3 95–127s | 1/33 | 1/33 (3.0%) | 0/32 | 0 | 0.0% |
| 006 | S02 RX2/CH2 150–200s | 12/72 | 11/72 (15.3%) | 0/60 | 1 | -1.7% |
| 007 | S03 RX1/CH4 0–40s | 16/54 | 54/54 (100.0%) | 38/38 | 0 | 100.0% |
| 008 | S03 RX1/CH4 175–210s | 8/50 | 9/50 (18.0%) | 2/42 | 1 | 2.4% |
| 009 | S03 RX1/CH5 175–200s | 4/34 | 31/34 (91.2%) | 27/30 | 0 | 90.0% |
| 010 | S04 RX2/CH5 75–110s | 2/46 | 3/46 (6.5%) | 1/44 | 0 | 2.3% |
| 011 | S04 RX2/CH3 110–140s | 9/43 | 10/43 (23.3%) | 1/34 | 0 | 2.9% |
| 012 | S04 RX1/CH3 125–175s | 14/66 | 14/66 (21.2%) | 0/52 | 0 | 0.0% |
| 013 | S05 RX1/CH3 40–60s | 1/28 | 1/28 (3.6%) | 0/27 | 0 | 0.0% |
| 014 | S05 RX1/CH4 250–280s | 3/39 | 3/39 (7.7%) | 0/36 | 0 | 0.0% |
| 015 | S05 RX1/CH2 110–140s | 6/36 | 34/36 (94.4%) | 28/30 | 0 | 93.3% |

Source IDs map to the five recording IDs in the [parent report](../2026_10_16_dsx01_models/README.md). All requested observations remain in the denominator, including other trajectories, positive controls and outliers. An unchanged count can hide changes of identity or membership; the CSV reports new and lost memberships separately.

![Satellite timing histograms](satellite-timing-histogram.png)

The top row shows total orbit-time offsets τ; the bottom removes each recording’s common clock shift, showing δτ = τ − common. Each entry is one recording–satellite pair, not one GLRT point. The same satellite can contribute once per recording. All methods use the same 215 pairs and 2 s bins. These are fitted model parameters, not independently measured satellite clock errors or TLE ages. The ±20 s bounds apply to total τ; relative offsets can extend beyond them when a nonzero common term is removed.

| Method | Relative timing RMS (s) | Pairs with abs(δτ) > 5 s | Total abs(τ) ≥ 19 s | Changes > 1 s |
|---|---:|---:|---:|---:|
| original | 9.147 | 133/215 | 2/215 | 0 |
| A | 8.898 | 127/215 | 2/215 | 13 |
| B | 9.146 | 133/215 | 2/215 | 0 |
| C | 9.147 | 133/215 | 2/215 | 0 |

The timing distribution remains broad. A moves a small number of timing branches substantially, while B/C largely overlap the original. Lower timing RMS is not a proof of more accurate timing or position.

![Paired timing changes](satellite-timing-change-histogram.png)

Some fitted candidates have little evidence. The following plot fixes the original-supported cohort (at least five original assignments), retaining all 182 pairs for every variant even if support is lost:

![Fixed supported cohort](supported-satellite-timing-histogram.png)

| Source | Original common (s) | A common (s) | B common (s) | C common (s) |
|---|---:|---:|---:|---:|
| S01 | -1.594 | -1.312 | -1.594 | -1.594 |
| S02 | -0.647 | -1.261 | -0.647 | -0.647 |
| S03 | 1.901 | 1.966 | 1.887 | 1.901 |
| S04 | 3.870 | 3.673 | 3.870 | 3.870 |
| S05 | 0.463 | 0.288 | 0.463 | 0.463 |

[Window CSV](window-recovery.csv) · [Timing CSV](timing-offsets.csv) · [Summary](summary.json). Prior target-informed track fits, the automatic full-data variants, and temporal cold starts are distinct experiments. These tables use only the automatic full-data endpoints, without choosing a different best model or temporal fold for each window. Original dataset and parent evaluation artifacts are unchanged.
