# Sparse RF-rotating routing before detection

Replacing 22 of 24,808 valid stereo visits with authentic capture-era packets changed position error by at most 19 m with the RF-rotating rule. Both new-to-routing recordings changed by at most 0.51 m in either calibration arm. All three routes stayed at 2/4 within 10% of original v5 in each calibration. On two recordings the detector work model stayed below 20 ms on average across the observed capture CPU range. Every measured original-detector call exceeded the individual 20 ms deadline.

## Before-detection schedule

The router earns one credit per 1,024 admitted stereo visits. It dispatches both receivers of a selected visit to the original detector. The rotating arm spends on the next RF lane in a fixed alternating low/high order, with a fifteen-visit wait limit. Fixed-phase spends immediately when a credit is earned. Both routes can decide from current visit metadata, before either detector reads the IQ. Their achieved counts match exactly. The earlier selective-detector experiment called wide first and used its candidate scores before reprocessing. This schedule keeps the complete recording frontier and has no candidate inputs. [Locked procedure](PROTOCOL.md) · [Exact assignments](selection-lock.json)

| Recording | Valid stereo visits | Routed per arm | Rotating channels | Fixed-phase channels |
| --- | ---: | ---: | --- | --- |
| DS26-0036 | 6,765 | 6 | 1, 5, 2, 6, 3, 7 | 2, 2, 2, 2, 3, 3 |
| DS29-0082 | 4,868 | 4 | 1, 5, 2, 6 | 7, 3, 2, 5 |
| DS26-0014 · holdout | 6,772 | 6 | 1, 5, 2, 6, 3, 7 | 8, 8, 8, 8, 8, 8 |
| DS29-0127 · holdout | 6,403 | 6 | 1, 5, 2, 6, 3, 7 | 4, 1, 2, 5, 8, 1 |

The scorer independently checked the complete ordered visit packets, clocks, sample counters, channel, exact RF, receiver IDs and exclusions, including jointly negative visits. Each policy changed all 22 selected packets. Ten rotating and thirteen fixed-phase substitutions occurred on visits where both original packets had zero positives. No saved substitution created a positive on a previously zero-positive stereo visit. Two rotating and three fixed-phase substitutions removed all positives from the selected stereo visit. These are detector outputs. [Packet audit](treatment-audit.json)

## Position and conditional Doppler

All eight mixed services and the four sealed stocks published both calibration arms. Values are `c = 0` / fitted `c`. The DS29-0082 stock uses the prior exact native-factor replay under the same phase-release receiver, which reproduced the original whole-IQ position and RF pair exactly. [Position scores](scores.csv) · [Stock verification](../../track-recovery/support-cross/archive-parity.csv) · [All four capture-era v5 options](capture-era-v5.csv)

| Recording | Stock wide error (km) | Rotating error (km) | Fixed-phase error (km) |
| --- | ---: | ---: | ---: |
| DS26-0036 | 1.003 / 0.935 | 1.003 / 0.936 | 1.003 / 0.936 |
| DS29-0082 | 2.489 / 2.346 | 2.474 / 2.364 | 2.492 / 2.346 |
| DS26-0014 | 0.472 / 0.755 | 0.473 / 0.756 | 0.552 / 0.716 |
| DS29-0127 | 0.756 / 0.721 | 0.755 / 0.720 | 0.755 / 0.720 |
| Median | 0.879 / 0.845 | 0.879 / 0.846 | 0.879 / 0.828 |

Median conditional Doppler RMS was 84.95 / 84.87 Hz for wide, 84.97 / 84.89 Hz for rotating, and 84.95 / 84.87 Hz for fixed-phase. On the hard recording, rotating improved zero-calibration position by 15.5 m and worsened fitted position by 18.6 m, while conditional RMS rose 0.04 and 0.03 Hz. The cost-feasible means on the two DS26 recordings yielded no material improvement from rotation. All four recordings used one physical roof. [Both-arm position and RF summary](scores.json)

- Rotating route. [`c = 0`](charts/c0/mixed-duty-rotating.png) · [Fitted `c`](charts/fitted_c/mixed-duty-rotating.png)
- Fixed-phase route. [`c = 0`](charts/c0/mixed-duty-fixed-phase.png) · [Fitted `c`](charts/fitted_c/mixed-duty-fixed-phase.png)

## Dual-IQ CPU model and the 20 ms target

The model starts with the actual per-visit CPU from each complete stored-IQ wide service. It subtracts the clocks for exactly the selected wide visits and adds measured original dual-receiver detector costs and router CPU. The archived wide clock ledgers reproduce all complete visit counts, measured timing distributions and deadline counts. For DS26-0036 and DS29-0082, the point model uses the same recording's original timing mean. For the two new cases, it uses the equal-weight mean across the four measured original timing cohorts. Sensitivity uses the observed pooled minimum and maximum of 57 warm calls, 548–2,742 ms CPU. The range represents those observed costs. The selected visits and transfer-case original detector calls were not retimed. [Timing model and on-time counts](time-model.csv) · [Dual-IQ clock authority and samples](time-authority.json) · [Cost chart](detector-cost.png)

| Recording | Stock wide CPU mean (ms) | Rotating CPU mean estimate (ms) | Observed-cost sensitivity (ms) | Wide measured → rotating modeled calls within 20 ms |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 14.286 | 16.117 | 14.760–16.706 | 6,689 → 6,683 / 6,765 |
| DS29-0082 | 22.257 | 23.463 | 22.689–24.493 | 1,050 → 1,049 / 4,868 |
| DS26-0014 | 16.820 | 18.097 | 17.291–19.235 | 6,382 → 6,376 / 6,772 |
| DS29-0127 | 19.185 | 20.534 | 19.682–21.738 | 3,993 → 3,989 / 6,403 |

The fixed-phase cost differs by less than 0.001 ms in mean CPU on every recording. The 20 ms budget is feasible as an amortized host CPU load for DS26-0036 and DS26-0014 across the observed cost range. DS29-0082 already exceeds that mean with wide alone, while DS29-0127 crosses it under the point model and straddles it across observed costs. The fastest observed capture-era call took 548 ms wall time. Each routed call thus misses a synchronous 20 ms deadline under the observed costs even where aggregate CPU fits. The model excludes scheduling, acquisition, buffering, archive I/O, and position fitting. [Exact model](time-model.csv)

The independently measured factor-to-position services took 25.34–46.57 CPU s and 25.44–48.70 wall s each. They ran with a 512 MiB cgroup, no swap, a 210 s limit, and one pinned numerical core on the host. The highest charge was 367.1 MiB with no OOMs or swap. The mixed-factor replay and timing model used saved RF evidence, with no new IQ acquisition or physical target timing. [Numerical resource receipt](resources.csv) · [Prediction seal](prediction-lock.json)
