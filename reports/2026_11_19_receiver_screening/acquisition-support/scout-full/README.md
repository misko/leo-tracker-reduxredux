# Four versus sixteen proposed pilot start times

Both detectors published seven of eight full-waveform fixes. With fitted calibration each met the original v5 error target on **4/8** recordings, at either a 5% or a 10% allowance. At zero calibration the 10% counts were **5/8** for four starts and **4/8** for sixteen. Among the six recordings on which both finished, sixteen starts improved the position on five in each arm. It added a median **28.51 s elapsed** and **29.42 s CPU** per completed pair. [Fitted chart](charts/fitted_c/scout-centers-all.png) · [Zero-calibration chart](charts/c0/scout-centers-all.png) · [Both arms on the two new recordings](charts/index.html#screening-scout-centers-new-iq)

| Recording | Original v5, zero / fitted (km) | Four starts, zero / fitted (km) | Sixteen starts, zero / fitted (km) |
| --- | ---: | ---: | ---: |
| DS26-0014, first full comparison | 3.415 / 3.405 | 0.472 / 0.755 | 0.074 / 0.450 |
| DS29-0127, first full comparison | 0.621 / 0.567 | 0.756 / 0.721 | 0.701 / 0.656 |
| DS26-0036 | 1.278 / 1.208 | 1.003 / 0.935 | 0.785 / 0.746 |
| DS29-0082 | 0.567 / 0.517 | Timeout | 2.273 / 2.025 |
| DS26-0237 | 0.362 / 0.271 | 0.382 / 0.323 | Timeout |
| DS29-0174 | 0.885 / 0.917 | 0.793 / 0.806 | 0.702 / 0.751 |
| DS26-0122 | 0.751 / 0.747 | 1.320 / 1.318 | 1.542 / 1.542 |
| DS29-0247 | 1.320 / 1.458 | 1.326 / 1.338 | 1.252 / 1.257 |

The median / 95th percentile among returned fixes was 0.806 / 1.332 km for four starts and 0.751 / 1.880 km for sixteen with fitted calibration. At zero calibration these were 0.793 / 1.324 km and 0.785 / 2.054 km. The two return sets differ by one recording in each direction. All recordings use the same physical roof, including the two additional waveform IDs selected by input hash before their comparison. [Every position, v5 reference and conditional RF score](scores.csv) · [Distribution summaries](summary.json)

Across the 51,816 valid dual-receiver calls per detector, mean detector CPU rose from 18.61 to 23.49 ms. Four starts met the 20 ms elapsed target on 32,405 calls (62.5%), and sixteen met it on 14,150 (27.3%). The total positive candidate count fell from 138,887 to 126,061 after the final eight-slot selection. Conditional Doppler RMS fell on five of the six jointly completed recordings in each arm. The cost figures are from the archive host. [Stage timings and resource accounting](resources.json) · [Detector-only qualification](../scout-budget/README.md)

Each complete service had a 360 s deadline, 512 MiB and zero swap. Both timed-out services finished the full detector stage. The file service was under contention during the experiment. For DS26-0237, systemd started terminating at 360.03 s and confirmed the group terminal at 522.35 s. The worker used 291.46 CPU seconds. Its original supervising process exited before writing the receipt, and the receipt was recovered from the manager and verified against the original log, invocation, recording and empty cgroup. DS29-0082's supervisor recorded 360.08 s to failure. The four-start raw output was byte-equal to the earlier control on all eight recordings, including DS29-0082. All seven returned four-start fixes matched the earlier position exactly in both arms. The primary chart retains each timeout. [Control audit](../control-parity/README.md) · [Separate deadline repeat](../deadline-repeat/README.md) · [Protocol](PROTOCOL.md) · [Prediction seal](prediction-lock.json)
