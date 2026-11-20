# Fused four and staggered fifth at equal recorded pace

Fused four retained **94.39%** of valid arrivals on DS29-0174 and returned **0.294 / 0.204 km** error at `c = 0` / fitted `c`. Staggered fifth retained **70.08%** and returned **0.726 / 0.698 km**. Each result comes from the packets emitted by its own full saved-IQ replay. The two host runs showed different release-delay and prefetch behavior. [Zero-calibration figure](charts/c0/modifications.pdf) · [Fitted-calibration figure](charts/fitted_c/modifications.pdf) · [Host timing figure](timing.png)

DS29-0174 is the recording with the lowest authenticated clock-manifest SHA-256 among the eligible members of the sealed 20-recording pool. DS26-0026 and DS29-0316 were excluded because they had related combined-detector experiments. The selected hash ends in an odd digit, fixing staggered first and fused four second. The two real saved-IQ clocks use the same caller CPU22, persistent helper CPU23, 512 MiB cgroup cap, zero swap and one waiting visit beside the active visit. [Protocol](PROTOCOL.md) · [Executable and input lock](source-lock.json)

## Evidence and boundary

Both paths run on the original recorded two-receiver IQ and preserve its sample counters, hardware-invalid visits and delivery timestamps. The per-RF alternating lane applies across valid arrivals, including a visit later dropped by the queue. Every emitted envelope must reproduce its predeclared exact fingerprint from the already-authenticated full four/fifth raw branches. Queue drops remain in the trace and supply no position observations. The compact solver uses the actual emitted subset and the original truth-free search offer, tracking config and causal TLE history. Both calibration arms share those inputs within a method. [Prediction seal](prediction-lock.json) · [Compact input lock](position-input-lock.json)

An initial launch failed its command binding before systemd started. Two short service setup attempts then failed before any arrivals because the capture interpreter lacks a supervisor-only scientific dependency. The corrected launcher keeps the scoring imports on the supervisor. The recording, order, libraries, schedule and every expected packet hash were unchanged. [First setup plan](preflight-source-lock.json) · [Failed service receipts](setup-failed)

## Packet coverage and timing

Arrival-to-emission age is measured from the archived due time and includes host release delay. Its percentiles describe emitted visits. Queue drops and hardware-invalid visits retain their own counts in the full denominator. Detector CPU includes the caller and helper. The startup split uses the first 32 chronological emissions in each run. These two host runs have a fixed order and ordinary OS caching between them. [Timing](timing.csv) · [Startup vs later](startup.csv) · [Coverage and age figure](timing.png)

| Observed on 6,774 delivered visits | Fused four | Staggered fifth |
| --- | ---: | ---: |
| Emitted / 6,704 valid | **6,328 (94.39%)** | **4,698 (70.08%)** |
| Queue drops | 376 | 2,006 |
| Hardware invalid | 70 | 70 |
| Detector wall median / P95 (ms) | 16.76 / 35.11 | 20.12 / 85.36 |
| Caller plus helper CPU median / P95 (ms) | 23.43 / 30.14 | 28.34 / 35.41 |
| Emission age median / P95 (ms) | 18.56 / 44.34 | 22.57 / 200.95 |
| Detector calls within 20 ms | 4,585 | 2,300 |
| Emissions within 20 ms of due time | 3,896 | 1,381 |
| Late source prefetch visits | 40 | 133 |
| Release delay P95 (ms) | 0.87 | 32.70 |

There were 4,419 common emissions, 1,909 fused-only emissions and 279 staggered-only emissions. Both services followed the same 300.006 s archived clock and reached a charged peak of 512 MiB with zero swap. Actual late prefetch and host release delay differed between the two runs. The per-call CPU measurements quantify extra detector work on the emitted subset. The queue-drop difference includes both detector work and host scheduling and IO conditions. [Raw service and visit evidence](raw)

Fused-four detector-wall P95 was 130.82 ms for the first 32 emissions and 34.50 ms afterward. Staggered P95 was 1,256.01 ms then 82.21 ms. Initialization through the first scheduled arrival took 1.10 s and 0.96 s from the worker start markers. The first 32 emissions capture startup effects on this host and its existing caches. [Startup split](startup.csv)

## Positions

The original four v5 options use their original capture-era factor archives. Per-arm frequency scores and RMS describe each method's conditional associated observations. The released stock-four archive is also available for the same recording, with its own unpaced timing conditions. It is presented separately from the paced comparison. [Geographic and RF scores](scores.csv) · [Earlier unpaced stock](archived-unpaced.csv) · [Position figures](charts)

| Position input | Error `c = 0` / fitted `c` (km) | Conditional RF RMS (Hz) | Conditional objective |
| --- | ---: | ---: | ---: |
| Fused four, actual paced emissions | 0.294 / 0.204 | 100.91 / 101.08 | 30,808.21 / 30,802.81 |
| Staggered fifth, actual paced emissions | 0.726 / 0.698 | 110.30 / 110.45 | 23,365.48 / 23,356.46 |
| Earlier released four, complete unpaced factors | 0.793 / 0.806 | 99.87 / 100.04 | 32,078.36 / 32,069.13 |
| Original v5 no repair or selective gap | 0.885 / 0.917 | | |
| Original v5 one or all omitted-track nomination | 0.881 / 0.912 | | |

The actual fused fit used 3,908 observations on 122 tracks. Staggered used 3,071 observations on 106 tracks. Fitting `c` reduced roof error by 0.090 km for fused four and 0.029 km for staggered on this recording. Conditional RMS increased by 0.176 Hz and 0.145 Hz, respectively. The two actual solver processes used separate cores after the raw clocks had finished. Worker fit wall was 86.8 s for fused and 53.8 s for staggered. [Measured results and fit receipts](positions.jsonl.gz)

The two paced clocks and measured fits used the scheduled time budget. The released four comparator comes from the earlier complete unpaced run on CPU18/19. Its 200.5 s pipeline time and 54 of 6,704 detector calls within 20 ms describe that run's conditions. [Archived comparison receipt](archived-stock-authority.json)

Rebuild the charts and scoring tables from the sealed results.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.equal_pace_results score
```
