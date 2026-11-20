# Secondary full-IQ deadline repeat

This is the separately registered repeat of the two primary scout-budget timeout cases. It repeats both detector branches on each recording under the original 512 MiB memory cap, zero swap and 360 s service deadline. Attempt and `TMPDIR` paths are on the local ext4 volume. Detector executables, replay and position programs, native runtime, recordings, catalogue, causal request, tile, CPU pairs and branch order match the primary source lock. [Registered protocol](PROTOCOL.md) · [Study specification](study.json)

## Primary observations remain in the audit

| Recording and primary branch | Service outcome | Raw stage wall | Full wall or active timeout | Cgroup CPU |
| --- | --- | ---: | ---: | ---: |
| DS29-0082, four starts | Timed out | 334.05 s | 360.08 s | 166.66 s |
| DS29-0082, sixteen starts | Completed | 83.12 s | 112.66 s | 184.18 s |
| DS26-0237, four starts | Completed | 112.62 s | 180.56 s | 249.86 s |
| DS26-0237, sixteen starts | Timed out | 131.51 s | 360.03 s | 291.46 s |

Both timed-out primary branches completed the raw-factor stage and did not publish a position. DS26-0237's primary sixteen-start cgroup took 522.35 s from service entry to fully inactive, including time after its manager-recorded 360.03 s active interval. Its timeout remains in the official primary comparison. Both repeats are new capped attempts selected by the frozen timeout roster. [Primary and repeat audit](primary-repeat-audit/charts/README.md) · [Primary terminal receipts and stage data](primary-repeat-audit/primary-resources.json)

## Four complete secondary saved-IQ replays

All four services completed within 360 s and published both `c = 0` and fitted `c` positions. Every run reached 536,870,912 bytes of cgroup peak charged memory and used zero swap. The corresponding primary and repeated branches reproduced byte-identical native factor archives with the same raw, clock, capture-exclusion and receiver-probe support digests. The generated job files differ only in the local native-file and position-output paths. The two completed primary branches reproduced both prior position-arm payloads exactly. [Run resources and checksums](resources.json) · [Primary/repeat identity proof](primary-repeat-audit/primary-repeat-provenance.json)

| Recording and repeat branch | Full wall | Raw stage wall | Fit wall | Cgroup CPU | Native positives | Dual-RX visits ≤20 ms wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS29-0082, four starts | 77.53 s | 53.78 s | 23.27 s | 125.08 s | 8,472 | 4,841/4,868 |
| DS29-0082, sixteen starts | 99.19 s | 70.73 s | 27.87 s | 161.71 s | 7,726 | 1,025/4,868 |
| DS26-0237, four starts | 126.42 s | 72.34 s | 53.31 s | 189.38 s | 17,344 | 6,472/6,766 |
| DS26-0237, sixteen starts | 150.31 s | 90.39 s | 59.08 s | 226.73 s | 15,590 | 3,030/6,766 |

Full wall uses the measured worker entry to successful position end. Raw and fit exclude a separately measured assembly interval. The two-case selection and scratch change make the secondary timings a deadline repeat under the observed conditions. Primary deadline outcomes and broader geographic qualification remain separate.

## Geographic error and conditional RF fit

| Recording | Four starts, `c = 0` / fitted `c` | Sixteen starts, `c = 0` / fitted `c` | Capture-era v5 baseline, `c = 0` / fitted `c` |
| --- | ---: | ---: | ---: |
| DS29-0082 | 2.489 / 2.346 km | 2.273 / 2.025 km | 0.567 / 0.517 km |
| DS26-0237 | 0.382 / 0.323 km | 0.223 / 0.149 km | 0.362 / 0.271 km |

DS26-0237's sixteen-start results were within 10% of the v5 baseline in both arms. Its four-start result met the tolerance with `c = 0`. Both DS29-0082 branches exceeded the v5 tolerance in both arms. The four v5 choices are shown in the [secondary plots](charts/README.md). [Geographic and RF scores](scores.csv) · [Capture-era v5 observations](primary-repeat-audit/capture-era-v5.csv)

Conditional RF RMS for DS29-0082 changed from 84.42 / 84.25 Hz with four starts to 85.95 / 85.65 Hz with sixteen starts. For DS26-0237 it changed from 92.54 / 92.43 to 92.01 / 91.91 Hz. The score file also records conditional frequency objectives and capture-era baseline RF RMS independently of geographic error.
