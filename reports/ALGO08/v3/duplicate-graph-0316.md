# Five duplicate proposals on a physical DS30 fix

The frozen duplicate-track rule removed **five proposals across 16 lane finalizations** on the complete DS30-0316 saved detector packet. Both calibration arms kept all **2,002** ordered observations, satellite assignments and roles. The two compared research builds had identical positions, RF residuals, terminal, path, matched grid, and all eight encoded and decoded PNGs. The regional proof, orbit handoff and projection counts matched. The duplicate check itself cost **0.319 ms CPU**. [Original comparison and native-option evidence](measurements/duplicate-graph-0316.json.gz)

| Saved detections to published output | Fixed-zero / fitted horizontal error | Fixed-zero / fitted RF RMS | Elapsed |
|---|---:|---:|---:|
| Frozen v3, historical | 1,944.73 / 1,863.06 m | 99.232 / 99.054 Hz | 18.140 s |
| Research combined solver, historical control | 1,916.77 / 1,833.65 m | 99.594 / 99.435 Hz | 11.209 s |
| Same solver with duplicate proposal check | 1,916.77 / 1,833.65 m | 99.594 / 99.435 Hz | 10.808 s |

The fresh launch and the control occurred at different times. The 0.402 s difference between research clocks does not isolate a performance gain from removing duplicates. This experiment tests transfer of a rule that recovered four observations in South and preserved the final North publication. The physical reference is the existing DS30 operator site authority. [Earlier named and combined physical results](catalogue-block-portable-0316.md) · [North and South comparisons](duplicate-graph-accuracy.md)

The worker used the exact archive, region, detector and code used by its physical control. One setup attempt rejected the newer bootstrap source before solving. The accepted worker exited successfully, and the scorer was then run with the matching read-only storage interface. One successful physical saved solve and zero waveform acquisitions were charged. The uncompressed comparison receipt has SHA-256 `302d8a8d55eca3da9eada3668b9ab440eaa67764734135afdf8636f234171aae`. [Frozen protocol](duplicate-graph-0316-protocol.md) · [Replay and scorer](duplicate_graph_0316.py)
