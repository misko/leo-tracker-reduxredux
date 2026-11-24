# The frozen lag contrast rule fails at 8 ms on DS30-0169

The unchanged **1.10** pre-carrier cutoff lost **three of 45 short factors** on the independently staged DS30-0169 member. It kept all 16 full-anchor lanes byte-for-byte, including both normal 20 ms scans and the original selected output. Complete verified acquisition saved **7.249 CPU ms** in one order and cost **5.336 CPU ms** in reverse. Both advancement conditions failed. The prespecified 8 ms transfer stopped before DS30-0008. [Frozen protocol](cross-lag-eight-ms-protocol.md) · [Exact signed paired receipt](measurements/cross-lag-eight-ms-0169.json.gz)

| Fresh order | Short native CPU, ordinary / routed | Complete authenticated acquisition CPU, ordinary / routed | Process wall through exit, ordinary / routed |
|---|---:|---:|---:|
| Ordinary then routed | 70.563 / 63.846 ms | 682.912 / 675.663 ms | 1.6674 / 1.7128 s |
| Routed then ordinary | 71.963 / 67.952 ms | 708.031 / 713.367 ms | 1.8090 / 1.8377 s |

Each process kept all 64 original stereo opportunities with **51 admitted and 13 invalid**, or **16 full and 86 short antenna calls**. All original compressed and decoded digests were checked. There were zero major faults and no input blocks in the four fresh processes. All 19,297 input pages remained resident. Ordinary reproduced all 102 emitted probes from the independently archived 8 ms control. The candidate expanded 50 of 86 short lanes in both orders. The removed factors were the antenna 1 positives at original visits 9, 11 and 39. Their exact-minus-control margins were **0.189, 0.092 and 0.121**. The other 42 short and 11 full factors were byte-identical, with no additions. No position or additional CFO refinement ran.

The result concerns the same lag cutoff on a different aperture. The distinct 12 ms test matched all 212 short outputs through native verification in its two signed members. The 8 ms test rebuilt only the 80,000-sample timing source and kept its original signed short verifier and two-scan anchors. The ratio threshold, lag pair and complete stereo schedule remained fixed. The resulting 8 ms DSO has SHA-256 `aa235377aeaa004e5fcb1aa3632808afa50f8261e4171e319e8d8475ead9293a`. [12 ms evidence](cross-lag-timing.md)

Use `python -Bm reports.ALGO08.v3.cross_lag_eight_ms build NEW_TMPFS_BUILD RELEASE_ASSETS`, then `launch NEW_TMPFS_RESULT 0169 NEW_TMPFS_BUILD` under the shared Gauss CPU2 lock with the original capture account, nice 15, best-effort I/O priority 7, and one numerical thread. The receipt expands to SHA-256 `bb2efb4aaba6f7211f65fbea1c193978e2d06f0e2441df6c20c43250de198c6e`. Six component and nearby tests passed. [Driver](cross_lag_eight_ms.py) · [Tests](../../../tests/pipeline_eval/test_cross_lag_eight_ms.py)
