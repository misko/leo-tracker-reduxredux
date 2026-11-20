# Two GLRT lanes with exact fractional reuse

The combined receiver runs the exact fifth-center detector in two persistent receiver contexts and reuses the previously computed center of each fractional GLRT grid. In the matched held study, fifth-center wall time was **31.25 ms serial, 19.94 ms in parallel, and 19.08 ms with both changes**. Corresponding p95 values were **41.90, 29.45 and 28.73 ms**. All methods returned the same 1,536 ordered fifth-center candidates and 243 gated candidates. [Stage chart](stage.png) · [Timing data](native-timing.csv) · [Parity receipt](native-parity.csv)

## Matched detector calls

The 96 genuine windows were sequences 0–23 from segments 3 and 8 in each of DS26-0197 and DS29-0316. Neither component study used these blocks. Three retained warm repetitions per window and mode ran in counterbalanced order. The typed serial detector used caller CPU20. Both parallel roles used CPU20 and a persistent helper on CPU21. Their clocks start with loaded dual CI16 and end after decoding both native output rows. Three additional signed, seeded-noise and zero controls per edge exercised the stock, fifth and absent modes. Complete public science, hint, support and gate records matched, including 1,535 stock ordered candidates and 216 stock gates. [Input lock](native-source-lock.json) · [Detailed measurements](native-measurements.json.gz)

| Mode and boundary | Released serial | Parallel | Parallel + fractional reuse |
| --- | ---: | ---: | ---: |
| Stock wall p50 / p95, ms | 25.31 / 33.71 | 16.29 / 23.13 | 15.28 / 21.66 |
| Stock CPU p50 / p95, ms | 24.69 / 29.17 | 26.35 / 31.85 | 24.28 / 29.18 |
| Stock at or below 20 ms | 5 / 288 | 245 / 288 | 267 / 288 |
| Fifth wall p50 / p95, ms | 31.25 / 41.90 | 19.94 / 29.45 | 19.08 / 28.73 |
| Fifth CPU p50 / p95, ms | 30.36 / 36.50 | 32.79 / 39.30 | 31.18 / 37.60 |
| Fifth at or below 20 ms | 0 / 288 | 146 / 288 | 170 / 288 |

CPU counts the caller and active helper. Each role and capture ran in its own 512 MiB, zero-swap cgroup. Across the two captures, charged peaks were 147.42–147.61 MiB serial, 174.37–174.82 MiB parallel and 174.35–174.80 MiB combined. Cgroup CPU over the held measurement phase was 8.66–8.79 s, 9.45–9.47 s and 8.86–8.87 s, respectively. Worker RSS is reported separately. No cgroup recorded an OOM kill. [Cgroup and process resources](native-resources.csv) · [Full distributions](native-summary.json)

The native wrapper is the sealed persistent two-lane executable. Its sibling detector incorporates exactly the three sealed fractional source changes. The join continues to return existing public rows in physical receiver order, and the helper's affinity is checked per call. [ABI and library hashes](native-build.json) · [Detector source closure](detector-build.json) · [Native result lock](native-lock.json)

## One complete arrival-paced replay

The fused fifth-center receiver replayed all **6,770** DS26-0026 arrivals in **300.75 s** on CPU20 with the helper on CPU21. It emitted **6,604** visits, dropped **155** when the one-active-plus-one-waiting queue was full, and excluded **11** recorded hardware-invalid arrivals. Every emitted two-receiver envelope matched the independently sealed complete fifth-center branch. The worker used **234.64 CPU s**, reached the **512 MiB** charged cgroup limit, and recorded zero swap and OOM kills. [Raw summary](paced/raw-summary.json) · [Memory witness](paced/raw-witness.json) · [Visit trace](paced/trace.json.gz)

Native wall p50/p95 was **19.51/32.24 ms**, and end-to-end emission age was **21.33/35.54 ms**. Of 6,604 emissions, **3,572** detector calls and **2,307** complete arrival-to-emission intervals met 20 ms. The prior CPU18 services ran adaptive first and always-fifth second. They dropped 504 and 78 visits, respectively. Those are historical results from separate core assignments and a different run order. [Pace comparison and clock boundaries](paced/paced-comparison.json)

## Both calibration arms

The fresh compact v5 worker fit precisely the authenticated emitted visits, the original causal TLEs, and the original offered tile. It published in both arms from 4,424 observations on 128 tracks. The separately capped fit used 76.8 s wall and reached 374.1 MiB with zero swap. The numerical launcher used a digest-field adapter after staging, preserving the original paced source, native file and request hashes. It ran one fresh compact solve. [Position source and seal](paced/position-lock.json) · [Position rows](paced/positions.jsonl.gz)

| Receiver | Position error, `c = 0` / fitted `c`, km | Conditional RF RMS, `c = 0` / fitted `c`, Hz |
| --- | ---: | ---: |
| Fused paced fifth, CPU20/21 | 0.698 / 0.672 | 85.34 / 85.29 |
| Earlier adaptive pace, CPU18 first | 0.560 / 0.553 | 88.49 / 88.47 |
| Earlier always-fifth pace, CPU18 second | 0.731 / 0.717 | 86.75 / 86.69 |

Each of the four original v5 options had 1.630 km error at `c = 0` and 1.560 km at fitted `c` on its capture-era inputs for this case. The new position comparison covers one roof recording. [Scores](paced/scores.csv) · [`c = 0` chart](paced/charts/c0/c0/combined-native-paced.png) · [Fitted `c` chart](paced/charts/fitted_c/fitted_c/combined-native-paced.png)
