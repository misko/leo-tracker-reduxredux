# Four and five acquisition centers on two new lower-edge recordings

The selection froze DS26-0144 and DS29-0491, the first lower-edge recording in each eligible dataset in first-segment SHA-256 order. They extend the pooled 20 recordings, which include the preceding upper-edge pair. The DS26 search ranked 51 lower-edge candidates from the archived common 127. The DS29 search ranked 298 lower-edge candidates from the original 615-record snapshot with its documented roof authority. The selected manifests passed SHA-256 verification, and all 212 declared payload and index members of each recording passed availability and size checks. No detector output or position outcome determines eligibility or order. [Protocol](PROTOCOL.md) · [Frozen input plan and releases](source-lock.json) · [Eligibility and exclusions](selection.json)

The stock four-center and fifth-center services read every archived valid dual-IQ visit with the same installed compact phase release and original 25 km request, causal catalogue, and TrackConfig. The original invalid records remain in both streams. Independent offline services use fixed CPU pairs, a 450-second limit, 512 MiB charged cap and zero swap. The four original v5 controls on DS26 are the published capture-era predictions. The four DS29 roles run using the authenticated original worker and matching archive-native input, causal catalogue, search request and priors under a separate 600-second, 4 GiB zero-swap factor-to-position limit. [Original v5 reference plan](reference-source-lock.json)

## Whole-recording detector coverage

Both policies processed all 6,756 valid visits on DS26 and all 6,772 on DS29, with 16 and 2 original invalid visits accounted for. Each detector call used both lanes. The fifth center added a distinct start on 11,323 of 13,512 receiver probes on DS26 and 11,178 of 13,544 on DS29. Both policies kept the recorded clock and eligible visit inventory unchanged. [Raw prediction seal and native archives](raw-prediction-lock.json) · [Per-visit lineage and timings](visits.jsonl.gz)

| Recording | Four/five positive probes | Fifth-center gains/losses | Identical passing stock payloads retained by five |
| --- | ---: | ---: | ---: |
| DS26-0144 | 4,592 / 4,984 | 396 / 4 | 19,589 of 20,645 |
| DS29-0491 | 4,901 / 5,264 | 366 / 3 | 21,095 of 22,160 |

All four stock starts remain eligible before the shared shortlist. Newly admitted starts also compete for its eight positions. Payload retention matches the actual passing stock candidates independently of shortlist rank. [Probe, gate and nomination audit](probe-audit.json)

## Measured wall time and CPU

All four complete replays finished with both calibration arms. Each reached a charged memory peak of 512 MiB with zero swap. DS26 ran four then five on cores 12/13, and DS29 ran five then four on 14/15. The figures below use the measured shared host. Detector measurements are per valid dual-receiver call, and the full pipeline includes raw read, detector calls, factor assembly and both position fits. [Service and stage receipts](resources.json) · [Prediction seal](prediction-lock.json)

| Recording and receiver | Call wall ≤20 ms | P95 call wall | Detector CPU | Full pipeline wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0144 four centers | 196 of 6,756 | 31.75 ms | 167.64 s | 202.58 / 286.12 s |
| DS26-0144 five centers | 0 of 6,756 | 41.62 ms | 223.35 s | 278.99 / 348.07 s |
| DS29-0491 four centers | 133 of 6,772 | 34.08 ms | 171.14 s | 262.98 / 304.67 s |
| DS29-0491 five centers | 0 of 6,772 | 41.04 ms | 217.43 s | 286.16 / 362.21 s |

The offline services drop no work to meet a visit deadline. Their fractions at 20 ms describe measured call duration. The independently instrumented staggered implementation uses these same case and output bindings. [Full timing distributions](deadlines.csv) · [Staggered whole-recording study](../staggered-whole/README.md)

## Position and frequency fit

Four centers met both the +5% and +10% thresholds against original no-repair v5 on two of two recordings in each calibration arm. Five centers met both thresholds on one of two at `c = 0` and two of two with fitted `c`. The fifth center cut DS29 position error by about half in both arms. On DS26 it increased `c = 0` error by 102 m and reduced fitted-`c` error by 4 m. [All four original options and positions](scores.csv) · [Both calibration arms and per-dataset charts](charts/README.md)

| Recording | Original no-repair v5, `c = 0` / fitted `c` | Four centers, `c = 0` / fitted `c` | Five centers, `c = 0` / fitted `c` |
| --- | ---: | ---: | ---: |
| DS26-0144 | 0.192 / 0.229 km | 0.162 / 0.180 km | 0.264 / 0.176 km |
| DS29-0491 | 1.767 / 1.780 km | 1.501 / 1.443 km | 0.751 / 0.694 km |

Within each branch, fitted `c` reduced conditional frequency RMS by 0.052 Hz for DS26 four centers and 0.021 Hz for DS26 five centers, with position error changes of +18 m and −88 m respectively. On DS29 it reduced RMS by 0.010 Hz for four and 0.072 Hz for five, with position error reductions of 59 m and 57 m. Each calibration pair holds the other inputs and budgets fixed. The different detector policies supply their own sets of retained candidates. [Calibration deltas and frequency objective](calibration.csv)

## Original DS29 v5 controls

All four genuine original policies completed on the same capture-era native file. They returned identical coordinates within each calibration arm on this recording. Their separate service timings include the original generation of evidence and plots. The 4 GiB original fit envelope is measured separately from the 512 MiB whole-IQ receiver trials. [Reference prediction seal and service logs](reference-prediction-lock.json) · [Original request and causal-input audit](reference-binding-audit.json)

| Original DS29-0491 policy | Service wall | CPU | Charged peak |
| --- | ---: | ---: | ---: |
| No repair | 307.26 s | 292.80 s | 2.3 GiB |
| Selective gap | 454.32 s | 317.68 s | 2.1 GiB |
| Omitted track one | 281.03 s | 261.44 s | 2.4 GiB |
| Omitted tracks | 321.35 s | 281.91 s | 2.3 GiB |
