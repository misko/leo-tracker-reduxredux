# Original full v5 and compact on identical wide GLRT factors

Original full v5 and compact `phase-release` agreed within 11.7 m in position on every completed pair. Original full v5 itself lost 1.83–1.93 km on DS29-0082 when it received the wide factors in place of its capture-era factors. The two other completed recordings also showed larger factor-source effects than same-factor solver differences. DS26-0122 timed out before the original CLI saved a result. [Chart, c = 0](charts/c0/wide-full-v5.png) · [Chart, fitted c](charts/fitted_c/wide-full-v5.png) · [All four archived v5 options and paired scores](scores.csv)

## Position error

The signed deltas subtract the comparator's error from the original full-wide error. Positive values mean full-wide made a larger error.

| Recording | Calibration | Capture-era full v5 | Compact wide | Full v5 wide | Full wide minus compact | Full wide minus capture era |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0122 | Zero | 0.751 km | 1.320 km | Timeout | | |
| DS26-0122 | Fitted | 0.747 km | 1.318 km | Timeout | | |
| DS26-0237 | Zero | 0.362 km | 0.382 km | 0.392 km | +10.3 m | +30.0 m |
| DS26-0237 | Fitted | 0.271 km | 0.323 km | 0.334 km | +11.2 m | +62.8 m |
| DS29-0082 | Zero | 0.567 km | 2.489 km | 2.496 km | +6.6 m | +1,928.8 m |
| DS29-0082 | Fitted | 0.517 km | 2.346 km | 2.349 km | +3.4 m | +1,831.9 m |
| DS29-0127 | Zero | 0.621 km | 0.756 km | 0.749 km | −6.5 m | +128.3 m |
| DS29-0127 | Fitted | 0.567 km | 0.721 km | 0.714 km | −6.9 m | +146.7 m |

Original full-wide published 3 of 4 in each calibration arm. Compact wide published 4 of 4. Both were within 10% of capture-era no-repair v5 on 1 of 4 with `c = 0` and 0 of 4 with fitted `c`. Both were within 5% on 0 of 4 in each arm. The six completed same-factor positions were 4.1–11.7 m apart. The data indicate sensitivity to the factor source on the completed pairs. The full-wide timeout leaves this attribution unresolved for DS26-0122. [Exact positions and errors](scores.csv)

## Frequency fit

Original residual RMS and compact conditional RMS describe different residual sets. In the complete same-factor pairs, the two reported numerical frequency scores differ by at most 0.0009. Fitting `c` reduced position error on all three completed recordings in both implementations. The frequency score fell on DS26-0237 and rose on both DS29 recordings.

| Recording | Original full-wide residual RMS, zero / fitted | Compact wide conditional RMS, zero / fitted |
| --- | ---: | ---: |
| DS26-0122 | Timeout | 85.498 / 85.506 Hz |
| DS26-0237 | 116.444 / 101.937 Hz | 92.538 / 92.427 Hz |
| DS29-0082 | 137.948 / 94.168 Hz | 84.421 / 84.248 Hz |
| DS29-0127 | 91.126 / 80.017 Hz | 75.833 / 75.902 Hz |

## Diagnostic resource limits

| Recording | Original full-wide terminal result | Wall | Cgroup CPU | Charged peak | Compact wide position stage |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0122 | Deadline after PNG rendering | 600.06 s | 449.20 s | 2.20 GiB | 69.46 s |
| DS26-0237 | Published both arms | 317.85 s | 298.84 s | 2.00 GiB | 64.44 s |
| DS29-0082 | Published both arms | 271.00 s | 177.92 s | 1.55 GiB | 23.27 s |
| DS29-0127 | Published both arms | 294.53 s | 211.70 s | 1.81 GiB | 34.08 s |

The original CLI used one CPU per service, a 4 GiB memory cap, zero swap, and a 600 s deadline. It includes numerical preparation, inference, PNG rendering and archive work. The compact position stages come from earlier replay services at 512 MiB with zero swap and cover their own position boundary. The timings describe those measured processes. DS26-0122 reached its deadline with neither a position receipt nor an evidence ZIP on disk. [Resource receipts](resources.json) · [Timeout log](DS26-0122-service.log)

The study prespecified DS29-0082 and DS26-0122. It selected DS26-0237 and DS29-0127 by the lowest complete wide-factor SHA-256 values among the six remaining recordings. Each original worker ran the pinned `evaluate_accuracy_repair.py worker` CLI on the same complete factor bytes as its compact pair. The truth-free no-repair request preserves the original numerical settings, tile, track policy and causal archive. The only substitutions are the native path and checksum, derived run identity and output directory. The DS29-0082 compact prediction comes from its successful sealed deadline repeat. [Prospective protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Prediction seal](prediction-lock.json)
