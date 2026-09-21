# Recent eight-hour trajectories and saved-IQ phase

The frozen request window is 2026-09-21 06:34:16–14:34:16 UTC. It contains 79 adaptive captures from radio .21 at dual-RX 2.5 MS/s. Seventy-five have complete shared-tracking-v14 products, containing 2,914 RF tracklets; four recent captures lack that product. All shortlisted recordings have their declared IQ chunks on disk. No new RF was collected.

The selection uses the existing reconstruction gates, duration, and exact shared RX0/RX1 visit support. It does not use phase quality or catalogue identity to select tracks. These are reconstructed RF trajectories; satellite identity remains unproven. The longest single-receiver trajectory spans 64.790 seconds. Phase analysis prioritizes the following five longest shared trajectories.

| Scan suffix (`scan-hop-…`) | Channel / edge | Shared span (s) | Shared visits | Replayed visits | Median conditional phase SE (degrees) |
|---|---|---:|---:|---:|---:|
| 6adcb067e2dbce43 | 3 / lower | 45.713 | 101 | 20 | 4.41 |
| e46d3aba244cf641 | 2 / upper | 44.326 | 106 | 12 | 5.28 |
| 6ca90c84541ebe31 | 4 / lower | 44.183 | 49 | 12 | 5.93 |
| b158f63a64278e61 | 4 / lower | 43.746 | 69 | 12 | 4.72 |
| 34c0b0e1ae062f97 | 4 / lower | 43.292 | 68 | 12 | 4.33 |

The first pass replays 68 distinct saved visits. Every selected phase measurement is associated back to its selected persisted RF trajectory using timing/frequency evidence rather than phase. Reported errors are conditional estimator errors, not total physical uncertainty.

## What phase is established

The saved IQ supports local, wrapped, instrument-inclusive RX1-minus-RX0 phase estimates within dwells. It does not yet establish continuous satellite geometric phase over these trajectories. In the longest track, contiguous pilot-symbol halves disagree by a median 14.25 degrees and a maximum 123.08 degrees, exceeding the nominal median 4.41-degree fit error. Across its 20 selected visits, phases cover the circle; gaps of 1.77–5.11 seconds leave cycle counts unresolved. No geometric slope is fitted by forcing an unwrap.

Under an independently justified stable differential receiver/LNB phase model, a single source's phase changes can contain geometric changes. This analysis does not establish that model, and the within-dwell discrepancies require explanation even under that assumption. Simultaneous two-source double differences can cancel a common receiver phase term when they use the same physical time support, but still require signal, timing, alias, and noise-bias controls.

The first pass finds a second shared source candidate at scan 34c0b0e1ae062f97, visit 678. A further screen of twenty nearby visits (19 new visits and a reproduction of 678) finds two pairs only at 678. Thus no multi-visit reference trajectory is established. The generic raw tool's asynchronous-centroid double difference is not interpreted as a geometric measurement.

## Could the changes be orbital?

The [geometry/orbit scenario report](2026_09_21_phase_change_geometry_scenarios.md) supplies distributions for LEO, MEO, and ideal GEO cases, with the recorded observing location and Earth rotation. It uses the LT3D-001A mechanical geometry, an explicitly illustrative holder pose, and sensitivity cases for unknown RF phase-center offsets, source separation, heading, and beam selection assumptions.

Changes of tens of degrees over several seconds can be physically plausible for this baseline and Ku-band frequency. Large changes within tens of milliseconds are a different question: even the fastest illustrated 350-km orbit and largest illustrated 114.7-mm baseline permit only about 1.48 degrees of two-source double-difference change over 20 ms. This is a scenario bound, not a measured phase-center bound. Geometry cannot be used to choose an otherwise unverified phase alias. The scenario distributions do not validate the observed phase trajectory or resolve its instrumental terms.

## Evidence

- [Full ranked inventory and selection](figures/2026_09_21_recent8h_track_inventory/README.md), including machine-readable rankings and exact shared-visit references.
- [Longest-track phase report](2026_09_21_scan_hop_6ad_long_track_phase.md), with per-visit measurements, controls, binding errors, JSON, PNGs, and digests.
- [Other four tracks](figures/2026_09_21_recent8h_phase_replay/README.md), with 48 saved-visit results and controls.
- [Second-source neighbor screen](figures/2026_09_21_scan34c0_visit678_neighbors/README.md).

The longest-track binding and geometry-scenario tests pass (9 tests). Raw evidence canonical digests were independently checked for the five first-pass replays and neighbor screen. These research artifacts do not replace production analysis contracts or deploy scanner changes.
