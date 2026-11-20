# Four waiting slots at the recorded arrival cadence

The four-slot replay retained all valid stock visits on DS29-0316. It still dropped 80 stock visits on DS26-0197 and 906 and 757 fifth-center visits across the two recordings. Fifth-center packets that did emit reached p95 ages of 373 and 357 ms. Host service and decoder readiness changed between the historical and current runs, so these counts describe the realized workloads. The fixed-service model below isolates the queue-capacity change.

This replay increases capacity from one waiting visit to four, plus one in service. The queue is FIFO and drops the newest valid arrival if full. Each additional dual-receiver CI16 slot holds 1.6 MB of raw samples, so the three added slots hold 4.8 MB before metadata. The decoder prefetch remains eight windows. Each recording uses its original physical cadence, causal input authority and the same core as before. DS26-0197 uses CPU18 and DS29-0316 CPU19. The host delivery gap medians are 43.54 and 43.45 ms over complete spans of 299.978 and 299.986 s. [Frozen protocol](PROTOCOL.md) · [Source lock](source-lock.json)

The prior one-slot runs are historical same-core controls, with no same-time repeat. The new runs keep the installed detector binaries and all input bytes fixed. They use one detector, one numerical thread, a 512 MiB cgroup cap and zero swap. Separate columns measure detector CPU, elapsed detector service, queue wait after dispatch, and packet age from scheduled host delivery to verified emission. The position fit follows capture as a separately timed step. This is recorded-IQ replay on the host. [One-slot report](../../support-preserving/arrival-queue/README.md)

For each recording and mode, the raw source authenticates the complete capture against its physical counter, clock and IQ authority. Each emitted native visit is checked against the previous complete detector's canonical envelope hash. Both physical receiver rows of every actual queue drop are absent from the retained support. Hardware exclusions remain separate. When all visits emit, the reuse certificate verifies the complete native input SHA against the previous measured position and records the ordered receiver-pair identity. Otherwise a fresh phase-release fit uses both `c = 0` and fitted `c`, the original 25 km offer and the same causal TLE history. The archived four original-v5 options still use capture-era factors. [Stage plot](buffered-arrival.png) · [Position chart index](position-charts/README.md)

## Actual paced stage

| Recording | Detector | Valid visits | Drops, one → four | p95 packet age, one → four | Maximum age, one → four | Source-ready after schedule, four |
|---|---|---:|---:|---:|---:|---:|
| DS26-0197 | Stock | 6,761 | 8 → 80 | 50.8 → 55.2 ms | 214 → 808 ms | 0 |
| DS26-0197 | Fifth center | 6,761 | 40 → 906 | 72.3 → 373.2 ms | 167 → 2,973 ms | 298 |
| DS29-0316 | Stock | 6,774 | 16 → 0 | 51.2 → 48.0 ms | 186 → 130 ms | 0 |
| DS29-0316 | Fifth center | 6,774 | 55 → 757 | 74.5 → 357.4 ms | 156 → 2,267 ms | 152 |

All four trials completed, authenticating 27,092 physical entries and 25,327 emitted visits. The new stock runs had median native CPU of 22.31/22.30 ms and median packet ages of 28.36/27.90 ms. The new fifth-center runs had native CPU medians of 34.51/34.59 ms, native elapsed wall medians of 39.86/39.72 ms and packet-age medians of 108.57/102.52 ms. For admitted fifth-center packets, 17.5%/19.5% completed before the next scheduled original delivery, compared with 55.4%/53.1% under the earlier one-slot runs. Maximum actual-dispatch-to-detector waits were 2,572/1,929 ms. [Measured stage, both capacities](buffered-stage.csv)

All historical one-slot inputs were decoder-ready by the original schedule. In the new fifth-center runs, 263/134 of the late-ready visits also dropped on queue admission. Other queue drops had a decoded input before its scheduled time. There were no shared stock drop identities between the two queue measurements and 3/11 shared fifth-center drops. DS26 stock lost 80 visits despite all source packets being ready on time. For example, accepted visit 5412 used 35.29 ms of CPU across 199.26 ms of native elapsed time, with four later arrivals dropped while the visit was in service. The measurement does not identify which host resource caused those elapsed-time stalls. [Drop identities and sample counters](drop-identities.csv) · [Complete four-slot trace](four-slot-events.json.gz)

Four-slot wall time stayed between 300.73 and 301.07 s. Charged memory reached the 512 MiB limit in all four trials without swap or OOM. Peak process RSS was approximately 210–226 MiB. The 11 original DS26 acquisition exclusions remain separate from valid queue drops. [Stage and input seal](stage-lock.json)

## Position on the emitted packets

Each recording and mode has a usable position in both calibration arms. Three changed inputs were freshly fitted. The lossless DS29 stock case reuses the exact complete-input endpoint, with no new fit time attributed. Fresh factor-to-position wall time ranged from 76.24 to 93.88 s. The table lists horizontal errors in the order `c = 0` / fitted `c`.

| Recording | Detector | All-valid error (km) | One-slot error (km) | Four-slot error (km) | Four-slot RF RMS (Hz) |
|---|---|---:|---:|---:|---:|
| DS26-0197 | Stock | 0.792 / 0.992 | 0.784 / 0.989 | 0.822 / 1.023 | 80.670 / 80.710 |
| DS26-0197 | Fifth center | 0.759 / 0.937 | 0.807 / 0.988 | 0.631 / 0.799 | 83.387 / 83.410 |
| DS29-0316 | Stock | 0.834 / 0.852 | 0.715 / 0.718 | 0.834 / 0.852 | 119.815 / 119.818 |
| DS29-0316 | Fifth center | 0.218 / 0.218 | 0.725 / 0.682 | 0.540 / 0.537 | 125.955 / 125.953 |

The observed four-slot fifth-center packets give smaller position errors than the one-slot packet set in all four paired arms. On DS26 the error also falls below the all-valid fit. On DS29 it remains roughly 0.32 km above the all-valid fit. There, RF RMS increased by 3.67/3.65 Hz relative to one-slot even with lower geographic errors. Modeled packet preservation, realized packet ages, and conditional RF fit characterize different parts of the receiver. Two captures from one roof establish the effects on these particular retained supports. [Paired geography and RF](buffered-positions.csv) · [Four original-v5 references](original-v5.csv) · [Exact stock reuse certificate](position-control-byte-bindings.json) · [Position score seal](position-score-lock.json)

## Queue capacity with fixed measured service times

An independent FIFO calculation holds every complete unpaced archived service duration and recorded arrival fixed, varying only the number of waiting slots. The one- and four-slot CPU-time models drop zero valid visits on every recording and mode. When using the earlier wall service times, stock drops change from 7 to 5 on DS26 and remain zero on DS29. Fifth-center drops change from 76 to 44 and from 113 to 73. In that fifth-center wall model the maximum admitted packet ages grow from 334 to 914 ms and from 1,494 to 1,746 ms. This controlled queue calculation keeps historical timing fixed, including any prior descheduling. The real paced comparisons test two separate host timing realizations. [Fixed-service model](fixed-service-model.csv)
