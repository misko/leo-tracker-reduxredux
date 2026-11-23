# DS30-0402 saved transfer on the first named rank-one winner

The cumulative publication took **23.749 s** through exit on the exact named-v3 20 ms detector packet, compared with **73.351 s** for the named replay, a **3.09×** saved-process speedup. Both routes chose the second cold finalist. Horizontal error increased by **90.3 m** for `c = 0` and **89.2 m** for fitted `c`, while RF RMS rose by **0.254 Hz** and **0.279 Hz**, respectively. This was the first named rank-one winner in the frozen roster, with its named result already known when assigned. [Frozen protocol](prospective-0402-solver-protocol.md) · [Full scored receipt](measurements/prospective-0402-solver.json.gz)

| Calibration | Named horizontal error (km) | Cumulative horizontal error (km) | Named RF RMS (Hz) | Cumulative RF RMS (Hz) |
|---|---:|---:|---:|---:|
| `c = 0` | 0.863651 | 0.953925 | 100.672203 | 100.926589 |
| Fitted `c` | 0.860302 | 0.949482 | 100.576460 | 100.855121 |

The fresh named replay reproduced its original zero-based screened rank **1**, terminal, owners, both calibration arms, 179-point grid and optimizer path. The cumulative race finished all three cold finalists because their prefix gaps were 80.10 and 166.54, below the required 1,030.24. The three completed scores matched the named screen scores exactly in the same order, and cumulative selected one-based branch **2**. Its later common-support repair and signed update used a different published observation set. `route_details.signed.selection.qualified` was **true** and the signed update was **accepted**. The selected standardized correction coefficient was −0.11720358. The held future gain was 83.611 on 2,679 observations, and the satellite-disjoint future gain was 19.180 on 499. The complete training and validation selection receipt is retained. [Prior cumulative route](prospective-0155-solver.md) · [Runner and verification](prospective_0402_solver.py)

## Owner and media evidence

In each calibration arm the cumulative result retained 4,680 of 4,821 named observations. Every retained row kept its NORAD and role. The same 141 observations disappeared in both arms, with zero added rows. Joining the exact dropped owner IDs to the signed native packet identifies these receiver and channel groups.

| NORAD | Named role | Receiver / channel | Dropped per arm | First–last visit |
|---|---|---|---:|---:|
| 58377 | Conditional | RX2 / CH6 | 61 | 69–1,085 |
| 62735 | Conditional | RX1 / CH5 | 48 | 84–1,028 |
| 62735 | Predictive | RX1 / CH4 | 17 | 835–1,107 |
| 62735 | Predictive | RX2 / CH4 | 15 | 867–1,107 |

The cumulative repair separately recorded removal of its own 62-point curved fragment `SCAN-RX2-CH6-T003-RF11959687500.000000`. It shares a lane with the 61 missing named conditional observations for NORAD 58377. The saved named owner rows carry observation ID, NORAD and role. Exact component membership for those rows is unavailable from the sealed owner rows.

Both publications had complete 179-point grids and path sidecars whose bindings matched their own position PNGs. All eight files and decoded RGBA hashes were verified in both processes, and the named files reproduced the archived checks. All candidate file and RGBA digests changed. The four orbit sheets kept their 2,400-pixel width and were 3,135 pixels high versus 3,172 for the named sheets, consistent with the legend shrinking from 24 satellites to 23. Both residuals, the position figure and track RMS kept their pixel dimensions. A separate post-exit check reproduced all four candidate orbit legends from fitted owners, with 26 pixels of minimum clearance. Four direct orbit and two direct residual products completed without renderer fallback.

## Timing

| Saved-input boundary | Named v3 | Cumulative |
|---|---:|---:|
| Launch through exit elapsed | 73.351 s | 23.749 s |
| Launch through exit CPU | 73.254 s | 23.708 s |
| Matched numerical solve elapsed | 68.825 s | 20.412 s |
| Matched numerical solve CPU | 68.774 s | 20.405 s |

The numerical solve accounts for **48.369 of 49.546 CPU seconds** saved, or **97.6%**. Everything outside the timed numerical solve accounts for a net 1.177 CPU s. Available named subclocks cover the initial screen and selected native kernels, leaving the savings among finalist finishing, history initialization and subsequent candidate work unresolved. The cumulative cold clock was 6.858 CPU s. Its regional check used 1.997 s, complete evidence 4.934 s, and rendering 1.407 s. The stage clocks are provided with their original nested scopes.

The processes ran in succession on the same pinned Gauss CPU 2 with one numerical thread, nice 15, best-effort I/O priority 7 and a common warmed font cache. Linux reported 15,488 and 5,304 input blocks from ordinary saved-process dependencies. Elapsed exceeded CPU by 98 ms and 41 ms, respectively. Host-global full I/O pressure was 52.08% over the 10 seconds before staging. The named-first, cumulative-second order leaves cache and process-order variation in the comparison. The 49.60 s elapsed difference is also visible in the independent CPU clocks.

The separately timed archive stage took **2.098 s elapsed / 0.059 CPU s**. It copied exactly 19 unique original TLE payloads totaling **34,002,575 bytes**, reused existing tmpfs content for 25 snapshot names and verified all 48 staged names, digests, lengths and collection times. The same original 25 km offer, signed inventory and cutoff bound both processes, including all 6,761 admitted stereo visits out of 6,773 issued. The input was saved detector data throughout. The timing driver and protocol were frozen at `ca3a64553`, and the post-exit augmentation added the receiver/channel join and matched clock attribution. Twelve focused and adjacent tests passed. [Component tests](../../../tests/pipeline_eval/test_prospective_0402_solver.py)
