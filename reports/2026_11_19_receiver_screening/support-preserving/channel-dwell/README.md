# Channel dwell at matched original-detector budgets

The previous spread and four-visit burst policies produced zero Graph tracks on DS26-0164 and DS29-0357. This run preserves the same budgets of 96 and 416 original dual-receiver detector calls per recording. It concentrates them into continuous intervals on one or two RF lanes. The same two recordings form the replication pair. A salted acquisition-metadata selection added DS26-0249 and DS29-0247. Each solve uses genuine capture-era detector packets and the original causal TLE history, with clocks, exclusions and native rows cut at its final scheduled sample. [Protocol](PROTOCOL.md) · [Exact schedules](schedule.json) · [Prior burst comparison](../capture-bursts/README.md)

| Recording | 96-call channel | 416-call channels |
| --- | ---: | --- |
| DS26-0164 | 8 | 8 and 4 |
| DS29-0357 | 4 | 4 and 8 |
| DS26-0249 | 3 | 3 and 7 |
| DS29-0247 | 8 | 8 and 4 |

The 96-call dwell samples every other valid opportunity on its hash-selected lane. The 416-call dwell uses 208 consecutive opportunities on each of two lanes in opposite RF banks. The delayed run at each budget waits until valid lane ordinal 384 and then uses the same rule. Both receivers share each decision. No survey calls or signal outcomes enter the schedule. The first setup attempt failed at the executable path handoff before entering the installed solver. The corrected runner uses the same exact schedule, verified byte for byte. [Initial 18 setup failures](initial-launch/prediction-lock.json) · [Corrected prediction seal](prediction-lock.json)

## Tracks, satellite support and position

All 16 dwell attempts formed actual Graph tracks with active curvature. The 96-call schedules span 67.31–67.36 s and retained 2–4 time-connected winning chains per fit. The 416-call schedules span 73.51–73.92 s and retained 4–6 chains. These chains meet the minimum eight points over six seconds and at most ten seconds between points, before any CFO compatibility test. The original spread and burst schedules on the two repeated recordings had no such chain. [Packet and sample-frontier audit](packet-audit.csv)

The early 96-call rule published on 1/4 recordings and its delayed control on 2/4, in both calibration arms. Each of the five failed 96-call fits reached the signed incumbent with one compatible curved satellite. The installed cavity nomination then hit its nonempty-observation mask requirement. Those attempts return no coordinates. The 416-call policies published all eight fits in both arms with two to five compatible curved satellites. Both new full controls published and each had 24 compatible curved satellites. [Compatible NORADs, track counts and solver stage](graph-geometry.csv)

The geometry check takes each compatible curved track's matched orbit and the actual fitted receiver endpoint. It computes the east/north range-rate sensitivity and removes each track's mean before taking the two singular values. The smaller singular value on the 416-call arms was 76–411 Hz/km, compared with 1,339 and 1,695 Hz/km on the two fresh full controls at `c = 0`. These values include the number of retained observations. They describe local Doppler sensitivity under the selected orbits and per-track means. The two archived full controls supply Graph evidence and positions from the earlier run. [Doppler geometry measurements](graph-geometry.csv)

Each slash below gives `c = 0` / fitted `c`. The published 416-call errors span **1.690–9.848 km**. None of the sparse variants came within 5% or 10% of the original no-repair v5 error on any recording in either arm. All four complete-factor compact controls met both targets in both arms. Conditional RF does not track error consistently. On DS26-0164 the delayed 416-call fit had 48.46 Hz RMS at zero calibration while returning a 9.848 km error. The full fit on that recording had 58.11 Hz RMS and a 1.228 km error. [Position, RF, and target count inputs](scores.csv) · [All four capture-era v5 options](capture-era-v5.csv)

| Recording | Early 96 (km) | Delayed 96 (km) | Early 416 (km) | Delayed 416 (km) | Complete factors (km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0164 | Failed | 9.569 / 9.569 | 1.693 / 1.690 | 9.848 / 9.848 | 1.228 / 1.246 |
| DS29-0357 | 6.261 / 6.261 | 7.707 / 7.707 | 8.278 / 8.283 | 3.347 / 3.349 | 0.436 / 0.434 |
| DS26-0249 | Failed | Failed | 5.141 / 5.142 | 9.566 / 9.566 | 0.075 / 0.045 |
| DS29-0247 | Failed | Failed | 6.924 / 6.924 | 6.418 / 6.418 | 1.320 / 1.458 |

## Detector queue and measured solver cost

The selected original-detector visits use the archived scan cadence, around 0.355 s per return to a lane. Under the observed launch clocks the early intervals finished supplying data at 67.4–73.6 s. The delayed runs first supplied a selected visit at approximately 136.2 s. A one-detector-core FIFO with the equal-cohort mean original-detector CPU cost of 1.457 s per visit estimates work from these original arrivals. The query scenario adds measured factor-to-position wall time after the final detector result, or observed terminal service wall on a failed solve. Sensitivity applies the observed original-call cost range of 0.548–2.742 s across each same-clock schedule. The earlier timing panel measured zero of 57 actual original calls within 20 ms wall. This is a saved-factor replay and transferred detector model. [Cost authority](cost-authority.json) · [Per-case timing and fit resources](time-work.csv) · [Measured Graph and modeled queue chart](dwell-frontier.png)

| Schedule | Nominal original detector CPU (s) | Modeled terminal from first archived delivery (s) | Observed-cost sensitivity across four recordings (s) |
| --- | ---: | ---: | ---: |
| Early 96 | 139.92 | 156–162 | 84–285 |
| Delayed 96 | 139.92 | 292–297 | 220–420 |
| Early 416 | 606.30 | 623–628 | 244–1,162 |
| Delayed 416 | 606.30 | 759–767 | 381–1,302 |

The 18 corrected fresh services, including the two full controls, took 243.54 s as a batch across two pinned cores. All services used the 512 MiB cap and zero swap. The corrected sparse publication workers finished in 16.24–24.72 s and the sparse failures in 15.61–21.31 s of service wall time. The largest corrected fresh cgroup charge was 407.9 MiB. No OOM or swap occurred. The sparse schedules improve tractable temporal support at equal work, while the measured errors and transferred costs remain outside the original location and real-time targets. [Prediction seal](prediction-lock.json) · [All four chart variants, both arms](charts/README.md)
