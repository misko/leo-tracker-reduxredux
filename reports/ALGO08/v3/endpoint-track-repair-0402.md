# Endpoint repair restores 61 named rows on saved DS30-0402

The endpoint-only repair restored all **61 named-v3 observations** on the failing curved fragment and kept every cumulative control row in the same order with its original owner and role. Horizontal error fell **14.4 m** for `c = 0` and **14.0 m** for fitted `c`. Published RF RMS fell **0.368 Hz** and **0.359 Hz**. The complete saved candidate took **24.384 s**, versus **24.048 s** for its fresh cumulative control. [Frozen protocol](endpoint-track-repair-0402-protocol.md) · [Sealed pair, exact rows and figures](measurements/endpoint-track-repair-0402.json.gz)

| Calibration | Cumulative error (km) | Endpoint repair error (km) | Cumulative RF RMS (Hz) | Endpoint repair RF RMS (Hz) |
|---|---:|---:|---:|---:|
| `c = 0` | 0.953925 | 0.939478 | 100.926589 | 100.558313 |
| Fitted `c` | 0.949482 | 0.935530 | 100.855121 | 100.495808 |

The original two-arm fit produced one common maximum-step failure on RX2 CH6 T003, NORAD 58377. The candidate checked the same two chronological endpoint deletions at each fitted state. First-point deletion left the step statistic at **4.0632 / 4.0723**, above the original cutoff of 4. Last-point deletion lowered it to **2.8343 / 2.8465**. It also passed the original raw curvature, profile, conditional, alias and elevation checks in both arms. The selected last point occupied capture-relative time 49.4855251 s in the prior crossed diagnosis. The runtime used the fitted track order and gates to choose it. [Original lost rows](owner-loss-0402.md) · [Bounded repair](endpoint_track_repair.py)

One paired refit retained 4,102 conditional and 639 predictive rows per arm. Each arm converged in one phase refresh, with final phase changes of 0.00664 and 0.00658 s, and all original fitted track gates passed. The normal signed update qualified and was accepted. Final ownership rose from 4,680 to **4,741** per arm. The new 61 are all conditional rows of NORAD 58377. Compared with named v3, the 80 rows still absent are the earlier NORAD 62735 conditional and predictive fragments. The estimated horizontal errors still exceed named v3’s 0.863651 and 0.860302 km by about 76 and 75 m. [Named comparison and exact prior roster](prospective-0402-solver.md)

Both fresh processes completed the full **179-point** grid and published the optimizer path. Each sidecar binds its own verified position PNG. All eight candidate file and decoded pixel digests changed and their pixel dimensions matched the control. The independent legend check reproduced all four candidate orbit legends from the fitted owners. The fresh control reproduced the archived cumulative terminal, ordered owners, path and grid science, and all eight PNG file and decoded pixel digests.

| Saved timing boundary | Control | Endpoint repair |
|---|---:|---:|
| Full launch through exit elapsed | 24.048 s | 24.384 s |
| Full launch through exit CPU | 24.036 s | 24.375 s |
| Complete numerical solve CPU | 20.694 s | 21.120 s |
| Paid repair CPU | 0.698 s | 0.292 s |

Both processes recorded zero filesystem input blocks and major faults. They ran sequentially under the shared Gauss CPU2 lock, with nice 15, best-effort I/O priority 7, one numerical thread and the same tmpfs stage and font cache. The repair scope includes frozen checks and its paired refit. The original control scope includes common-support preparation and the paired deletion refit. The changed retained support also enters subsequent signed, grid and publication work. The complete candidate used **0.339 more CPU s** in this pair.

The 0402 result satisfies the prespecified condition for the DS30-0160 cross-recording transfer. That case remains reserved with its endpoint-repair outcome unmeasured. Generic tests exercise an interior outlier, unique first and last endpoints, ambiguous and disagreeing endpoint choices, unfinished phase fallback, and an already valid track. Thirteen focused and adjacent tests passed. The full saved comparison used as-run driver commit `7a266102f` and the frozen rule and protocol at `a0d684801`. [Runner and scorer](endpoint_track_repair_0402.py) · [Component tests](../../../tests/pipeline_eval/test_endpoint_track_repair.py)
