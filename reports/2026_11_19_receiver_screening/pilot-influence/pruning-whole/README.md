# Exact four-region GLRT at the recorded arrival pace

This follow-up uses DS26-0197 and the previously sealed complete stock-wide packet and delivery-clock stream. Both replay arms run four regions on the two physical receivers, with the same persistent dual-lane wrapper pinned to CPU0/1. The primary active-set library ran first and the dense library second. The old archived stock pace used a single caller on CPU18 in a separate service. These are saved-IQ host services. [Protocol](PROTOCOL.md) · [Frozen capture, order and library authority](source-lock.json)

Every admitted packet is computed by the live detector and checked against the archived complete stock envelope before emission. The compact phase fit uses only the actual admitted packets and directly verifies their original factor bytes, offered tile and causal TLE authority. Recorded hardware exclusions and any queue drops stay in the physical ledger. The compact worker executes both calibration arms on one fresh matched input. [Held detector release](../native-pruning/README.md)

## Measured recorded-arrival services

Both new services accounted for all 6,772 arrivals, including 11 recorded hardware exclusions. All emitted packet digests matched complete archived stock. The 6,509 visits emitted by both new arms matched exactly. The active-set run alone emitted 118 visits and the dense run alone emitted 134. Each was a single bounded realization on the same cores with one waiting slot. [Packet parity and exact drop lists](parity.json) · [Per-visit status and digests](packet-status.json.gz)

| Measured boundary | Active set, first | Dense, second | Earlier CPU18 stock |
| --- | ---: | ---: | ---: |
| Emitted / queue drops | 6,627 / 134 | 6,643 / 118 | 6,753 / 8 |
| Summed coarse CPU p50 / p95, ms | 1.156 / 1.354 | 1.935 / 2.293 | — |
| Complete detector wall p50 / p95, ms | 10.37 / 25.23 | 10.62 / 21.60 | 29.66 / 44.76 |
| Complete detector wall at or below 20 ms | 6,070 / 6,627 | 6,241 / 6,643 | 54 / 6,753 |
| Emission age p50 / p95, ms | 11.78 / 30.01 | 12.01 / 24.01 | 31.71 / 50.80 |
| Emission age at or below 20 ms | 5,868 / 6,627 | 6,106 / 6,643 | 4 / 6,753 |
| Worker cgroup CPU, s | 112.96 | 119.70 | 202.82 |
| Worker wall, s | 300.63 | 300.47 | 300.81 |

On the shared emitted visits, median per-packet reductions were 0.781 ms coarse CPU, 0.914 ms total detector CPU and 0.341 ms detector wall. The active-set run used 6.73 fewer cgroup CPU seconds. Its 95th-percentile wall clocks, queue drops and 20 ms deadline coverage were worse in this one ordering. The earlier CPU18 service used a different one-caller layout and supplies historical context. Both current cgroups reached 512 MiB with zero swap or OOM kills. [Same-core paired and historical timing](comparison.json) · [Per-stage CPU](native-stages.csv) · [Stage chart](stage.png)

The dense service completed and emitted a success record just before the outer supervisor ended. The repository reconciler recovered its terminal result from the matching systemd invocation and journal. The missing outer exit code remains null. The detector outputs, worker time evidence and bounded stage sidecar are the actual completed service's files. [Dense service receipt](dense-service.json) · [Worker bounds](dense-witness.json) · [Raw seal](raw-lock.json)

## Fresh compact fit on actual emitted support

The capped worker fit both arms from the 6,627 exactly verified emissions. It used 4,133 observations and 112 tracks. Service wall was **46.36 s**, and peak charge was **375.9 MiB** with zero swap. The position control comes from the complete archived stock fit, including the 134 valid visits dropped by the active-set service. The fresh dense replay supplies timing and its own emitted roster. [Fresh input and request](position-input-lock.json) · [Position rows and resources](positions.jsonl.gz)

| Position input | Error `c = 0` / fitted `c`, km | Conditional RF RMS `c = 0` / fitted `c`, Hz |
| --- | ---: | ---: |
| Active-set emitted support | 0.827 / 1.034 | 80.33 / 80.36 |
| Archived complete stock | 0.792 / 0.992 | 80.52 / 80.56 |

Both fresh arms published. Their conditional RF RMS was lower and their geographic error was higher than complete archived stock. The scientific comparison covers one matched roof recording with different emitted support. [Scores](scores.csv) · [`c = 0` chart](charts/c0/c0/native-pruning-whole-position.png) · [Fitted `c` chart](charts/fitted_c/fitted_c/native-pruning-whole-position.png)
