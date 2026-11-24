# Two-of-three short stereo visits on saved physical detections

Both containing fixes met the frozen 250 m per-arm allowance against named ALGO08v3. Dense DS30-0008 improved by 158/51 m relative to named v3 and regressed by 562/604 m relative to acquisition on every mixed-aperture visit. Weak DS30-0016 improved by 119 m and regressed by 77 m relative to named v3, with 214/45 m regressions relative to complete mixed coverage. The dense 12 ms call reduction prices at 4.207 CPU seconds using the original per-call mean. Real detector and raw-to-exit savings remain unmeasured.

This experiment uses a [frozen chronological schedule](whole-stereo-blocks-protocol.md) and the real unfiltered rank-zero 12 ms and maximum-margin 20 ms lane proposals from both physical recordings. A metadata-only decision keeps the first two short visits of each three within each edge/channel/actual RF stream. Both radios and all eighth-visit two-scan anchors remain synchronized. Original invalid captures, sample counters, delivery clocks, visits, archive cutoffs, operator offers, and raw authority are preserved. Each masked visit has two empty original slots. The derived packet binds an explicitly new research detector recipe. Neither saved numerical worker had a path to original waveform data. [Receipt with full inputs and decisions](measurements/whole-stereo-blocks.json.gz).

## Position and RF fit

Every pair is ordered `c = 0` then fitted `c`. Named v3 is the published original two-scan receiver and solver. Complete mixed is the previously verified unfiltered 20/12 ms packet on the exact-graph/grid-projection preset. The mask uses the same preset and full catalogue. The named comparison is by raw authority, recording, and supplied region. Measurements are historical comparisons plus a fresh saved candidate for each case. Both masked cases returned complete in the original containing region and retained the original solver orbit policy. The region-excluded and live history-routed outcomes are unknown.

| Recording and receiver | Survey error, km | RF RMS, Hz |
| --- | ---: | ---: |
| Dense named v3 | 1.639 / 1.512 | 129.703 / 129.663 |
| Dense complete mixed | 0.919 / 0.857 | 140.961 / 140.950 |
| Dense masked mixed | 1.481 / 1.461 | 135.001 / 134.908 |
| Weak named v3 | 1.644 / 1.661 | 109.375 / 109.479 |
| Weak complete mixed | 1.311 / 1.694 | 121.526 / 120.291 |
| Weak masked mixed | 1.525 / 1.739 | 125.685 / 124.610 |

Dense endpoint displacement was 442/446 m from named v3 and 632/676 m from complete mixed. Of 4,367 complete mixed owners per arm, 2,849 were shared and 1,518 dropped, with 75 newly owned masked rows. Across the shared identifiers, 68 association roles changed and all NORAD identifiers agreed. Weak endpoint displacement was 197/528 m from named and 267/288 m from complete mixed. Each weak arm retained 81 of 116 owners and added zero, with unchanged NORADs and roles on the shared identifiers. Both saved candidates preserved the complete 179-cell grid schema and path and all eight PNGs were decoded and digest-verified. RF fit changes are reported separately from survey error.

## Detector budget and duration

| Recording | Full 20 ms calls | Short 12 ms before → paid | Exported factors before → paid | Gross modeled acquisition credit | Saved numerical solve CPU before → paid |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense DS30-0008 | 1,696 | 11,834 → 7,894 | 7,336 → 5,202 | 4.207 s | 22.868 → 20.560 s |
| Weak DS30-0016 | 186 | 1,240 → 832 | 475 → 336 | 0.402 s | 2.555 → 2.448 s |

The gross estimate charges every 20 ms invocation and all original verified reads, decode and digesting. It multiplies the number of omitted 12 ms invocations by the mean over all such original calls. Per-visit native durations on the omitted subset were unavailable, so the credit is an estimate. The dense acquisition model moves from 32.403 to 28.197 CPU seconds, with 15.053 CPU seconds outside native processing. Dense and weak historical solve-plus-acquisition models save 6.382 and 0.500 seconds after charging the saved mask planner, which took 0.133 and 0.009 CPU seconds respectively. These comparisons use historical control clocks and saved candidate clocks. The study stages zero waveform bytes and leaves the full acquisition byte budget intact.

The dense child wrote the final scientific receipt at 22.994 publication CPU seconds. An ensuing read of `grid_feature_projection.c` failed because that file was absent from the sparse checkout. The measured 24.664 CPU and 24.673 elapsed seconds belong to exit 1. The original terminal, 20.560 CPU-second numerical clock, selected rows, both position sidecars and eight figures were recovered and independently verified without another solve. The process recorded 320 input blocks while waveform entry points were closed. The weak admission verified the projection source before launch and the child exited 0 at 5.111 CPU and 5.113 elapsed seconds, against the complete mixed historical 5.449 CPU and 5.452 elapsed seconds. It recorded zero input blocks.

## Later continuation audit

The published position paths both used all paid in-lane factors from the original unfiltered receiver. As a separate saved test, the released stateful continuation saw each omitted opportunity as an empty slot. Its full versus masked selections changed from 5,940 to 3,725 on dense and from 356 to 228 on weak. Dense lost 1,716 selections on directly omitted slots and a further 499 on paid later slots. Weak lost 107 directly and 21 later. Neither audit gained a selection. The archived mixed detector can reproduce these inputs to continuation. It cannot establish how named-v3 hidden anchor candidates or other unexported ranks would behave. The direct dense accuracy cost and the indirect support loss make the schedule a bounded research candidate.

Earlier physical [alternate visits](../single-core-2x/alternate-visits.md), simulated [burst cadence](../single-core-2x/cadence.md), [full-aperture thinning](aperture.md), [crossed apertures](mixed-aperture-crossed.md), [native aperture panels](mixed-aperture-receiver.md) and [single-lane masks](stereo-mask.md) assessed other schedules or receiver paths.
