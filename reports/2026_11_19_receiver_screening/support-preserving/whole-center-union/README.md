# Fifth time-center union on two held whole-IQ recordings

The fifth center cut position error on both held recordings. On DS29-0316 it reduced error from 0.834 to 0.218 km at `c = 0` and from 0.852 to 0.218 km with fitted `c`. DS26-0197 improved by 33–55 m and remained above original v5 in both arms. Stock and the fifth-center candidate each published both positions on both recordings. Each was within 10% of original v5 on one of two recordings per arm. The fifth center increased detector CPU and reduced the number of calls that met the 20 ms wall target. [Zero-calibration charts](charts/c0/modifications.pdf) · [Fitted-calibration charts](charts/fitted_c/modifications.pdf) · [Per-recording scores](scores.csv)

The candidate keeps the four stock timing starts and unions the independent rank-one FFTW hint's clipped ±1-epoch neighborhood. The native search retains the original local-peak comparisons for stock epochs. New and original peaks then compete for the existing top eight and traverse the same fractional gates. A stock peak can survive the initial collection and still be displaced before publication as a native candidate. [Independent native qualification](../center-union/feature-gate.json) · [Protocol](PROTOCOL.md)

DS26-0197 and DS29-0316 were selected before scores by the SHA-256 of the first frozen segment manifest and complete saved-IQ availability. DS29-0316 was the sole remaining DS29 member of roof16 after excluding earlier whole-recording replays. The study uses existing recordings from one roof. Both branches share the original truth-free request, causal TLE history, original 25 km offer and screening center, capture clocks and installed compact phase release. Both calibration arms use the same branch-specific native observations. The four original v5 policies use their capture-era observations. [Selection and exclusions](selection.json) · [Matched stock source lock](source-lock.json)

Each recording ran stock first on its own fixed core pair while the native qualification was pending, followed by the candidate once qualified. The first activation command staged the qualified binaries and then exited because of a stray formatter artifact. It launched no service. The second activation removed the artifact and pinned the same candidate binary and FFTW sidecar. There was one stock and one candidate service per recording. [Initial activation receipt](candidate-lock.json) · [Measured activation receipt](candidate-lock-v2.json)

## Position and frequency

All two-value cells show `c = 0` / fitted `c`. Both methods were within either 5% or 10% of original no-repair v5 on **1/2** recordings in each arm. This threshold count uses both attempted recordings. Median errors across both published positions were 0.813/0.922 km for stock and 0.488/0.577 km for the union. [Per-arm summary](summary.json) · [All four capture-era reference options](scores.csv)

| Recording | Original v5 no-repair error | Stock wide error | Fifth-center error | Conditional RMS, stock → fifth center |
| --- | ---: | ---: | ---: | ---: |
| DS26-0197 | 0.528 / 0.689 km | 0.792 / 0.992 km | 0.759 / 0.937 km | 80.516 / 80.556 → 83.485 / 83.501 Hz |
| DS29-0316 | 1.007 / 1.011 km | 0.834 / 0.852 km | 0.218 / 0.218 km | 119.815 / 119.818 → 120.068 / 120.063 Hz |

Within the fifth-center branches, fitting `c` changed position error by +0.178 km on DS26-0197 and +0.001 km on DS29-0316. It changed conditional Doppler RMS by +0.016 and −0.005 Hz and the conditional objective by +4.968 and +14.872. The stock arms' position changes were +0.200 and +0.018 km. RF values characterize the observations selected by each acquisition method. [Paired calibration deltas](calibration.csv)

## Complete IQ and detector support

Identical capture manifests, clock/exclusion hashes, original TLE requests, and per-probe physical metadata authenticate the two branches within each recording. Each branch processed 6,761 valid dual-receiver visits on DS26 and 6,774 on DS29, with 11 and zero original invalid visits respectively. The candidate's live trace retained all 108,280 original timing-start entries and added a distinct covered neighborhood on 22,922 of 27,070 receiver probes. Independent native qualification verified the stock peak inventory with and without the hint before the common top eight. [Prediction and raw seal](prediction-lock.json) · [Per-visit report](visit-coverage.json) · [Complete visit trace](visits.jsonl.gz)

| Recording | Positive visits, stock → fifth center | Added / lost positive visits | Added / lost positive receiver probes | Identical stock gated payloads retained |
| --- | ---: | ---: | ---: | ---: |
| DS26-0197 | 2,934 → 3,049 | 121 / 6 | 339 / 15 | 17,521 / 18,537 |
| DS29-0316 | 2,997 → 3,205 | 210 / 2 | 417 / 7 | 19,186 / 20,317 |

A positive visit has a passing candidate on at least one receiver. Stock payload identity ignores ordinal rank and compares every other candidate field. The native common top eight retained 17,274 and 17,681 extra coarse peaks across the two recordings. Gains at new probes and losses of some final stock gates coexist with preservation of the original coarse support. The earlier fourth-center replacement measurements used different independent recordings, so the position charts here compare the fifth center with stock. [Full probe and native admission audit](probe-audit.json) · [Matched native-stage comparison with replacement](../center-union/PROTOCOL.md)

## Detector and service timing

All four complete services succeeded within 450 seconds at a 512 MiB charged cap with zero swap. Each measured peak was 512 MiB. The two modes ran sequentially on the same assigned core pairs, stock first. The 20 ms measurements include the scout, native GLRT and detector call bookkeeping. The observed complete-call detector CPU sums rose from 104.83 to 131.73 s on DS26 and from 105.97 to 132.25 s on DS29. Scout CPU accounted for 21.93 and 21.47 s. The same-core pairs are single host measurements, with no repeated timing runs. [Service and stage receipts](resources.json) · [Per-call and whole-service timing](deadlines.csv) · [Timing figure](resources.pdf)

| Recording and branch | Wall calls ≤20 ms | Call wall P50 / P95 | Raw / solution wall | Pipeline wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0197 stock | 6,304 / 6,761 | 15.58 / 20.98 ms | 77.71 / 48.55 s | 127.02 / 176.05 s |
| DS26-0197 fifth center | 3,522 / 6,761 | 19.86 / 30.92 ms | 96.00 / 64.46 s | 161.44 / 211.55 s |
| DS29-0316 stock | 6,282 / 6,774 | 15.69 / 21.00 ms | 76.79 / 55.63 s | 133.24 / 184.43 s |
| DS29-0316 fifth center | 3,349 / 6,774 | 20.04 / 33.13 ms | 110.88 / 61.25 s | 173.15 / 218.04 s |

The DS29 gain establishes a promising acquisition change on these two recordings from one roof. The loss of final stock gates and lower deadline compliance support keeping this implementation opt-in during qualification.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.whole_center_union_results score
.venv/bin/pytest -q tests/pipeline_eval/test_whole_center_union.py
```
