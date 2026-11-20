# New complete saved-IQ recordings for stock and fifth center

DS26-0255 and DS29-0330 were selected blind to detector and position outcomes. The first frozen segment manifest SHA-256 determined the order after the complete prior-waveform exclusions, including DS26-0026 and DS29-0047. The first metadata-eligible recording in each group passed preflight for every declared payload and index path and size. Physical file availability was checked for those two selected recordings. Both are upper-edge captures from the same original roof installation and 25 km offered region. [Protocol](PROTOCOL.md) · [Complete selection ledger](selection.json) · [Frozen numerical and waveform authority](source-lock.json)

Stock ran first on DS26 on cores 4/5. The released fifth center ran first on DS29 on cores 6/7. Each service is a complete saved-IQ replay under a 450-second limit with 512 MiB charged memory and zero swap. The paired branches use the original clock and invalid visit inventory and the same installed compact phase release, causal TLE and TrackConfig. The original four v5 policies on DS29 use the original capture-era native factors and a separate one-thread factor-to-position boundary. The original published DS26 policies complete the four-reference panel. [Complete paired raw seal](raw-prediction-lock.json) · [Original reference plan](reference-source-lock.json)

The optional lighter arm was frozen before geographic scores. The direct whole-IQ ABI `leo_native_glrt_analyze_center_union_v1` passed independent qualification against the released fifth center on both edges, with exact native rows, scout ranks, support, fractional gates and absent-hint controls. The lighter binary and the same FFTW scout were pinned separately. [Direct qualification](lighter-qualification.json) · [Measured third-arm activation](lighter-source-lock.json)

## Whole-IQ support and primary runtime

Each recording contained 6,774 scheduled visits. Both primary branches retained 67 original invalid visits on DS26 and 47 on DS29. Every valid visit and both receiver lanes reached the detector. The raw seal verifies the same manifests, clocks, exclusions and noncandidate physical metadata within each pair. All four primary services completed under 512 MiB charged memory and zero swap, with 512 MiB peaks. [Per-visit digests](visits.jsonl.gz) · [Per-branch service evidence](resources.json)

The fifth center gained and lost 499/16 positive probes on DS26-0255 and 342/6 on DS29-0330. It retained 19,885/21,135 and 18,991/20,125 stock passing payloads respectively, where equality ignores candidate rank. Original coarse starts survive the union and some final gates change after the shared top eight. [Probe and native nomination audit](probe-audit.json)

| Recording and branch | Valid dual detector calls | Call wall ≤20 ms | P95 call wall | Pipeline wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0255 stock | 6,707 | 6,432 | 19.48 ms | 182.81 / 189.86 s |
| DS26-0255 fifth center | 6,707 | 3,987 | 28.50 ms | 183.25 / 225.13 s |
| DS29-0330 stock | 6,727 | 6,263 | 21.35 ms | 176.45 / 191.78 s |
| DS29-0330 fifth center | 6,727 | 4,378 | 26.06 ms | 202.90 / 214.09 s |

Call timing includes the complete dual-receiver detector work. Wall and CPU refer to the measured host and assigned cores.

## Position error and calibration

All six whole-IQ services returned both calibration arms. The fifth center improved the fix on DS26-0255 and worsened it on DS29-0330. On each of the two calibration arms, stock, released fifth, and lighter fifth each placed one of two recordings within 105% of original no-repair v5 and one of two within 110%. Stock met both thresholds on DS29 and the fifth-center branches met both on DS26. This study covers two upper-edge recordings from one roof. [Position scores and all original v5 options](lighter-comparison/scores.csv) · [Stock and fifth center charts](charts/README.md) · [Three-way lighter kernel charts](lighter-comparison/charts/README.md)

| Recording | Original no-repair v5 c = 0 / fitted c | Stock c = 0 / fitted c | Released and lighter fifth c = 0 / fitted c |
| --- | ---: | ---: | ---: |
| DS26-0255 | 0.384 / 0.420 km | 1.545 / 1.317 km | 0.208 / 0.320 km |
| DS29-0330 | 0.831 / 0.793 km | 0.340 / 0.402 km | 1.558 / 1.522 km |

Within each measured branch, fitting c changed conditional RMS by −0.010 Hz for DS26 stock and −0.017 Hz for DS26 fifth center. Their position errors changed by −0.227 km and +0.112 km respectively. DS29 stock and fifth center changed conditional RMS by +0.036 Hz and +0.034 Hz and changed position error by +0.062 km and −0.037 km. The lighter kernel reproduced both fifth-center ablations. These comparisons hold the native factors, catalogue, request and search budget fixed within each branch. [Calibration effects including frequency score](calibration.csv)

## Lighter fifth center

The lighter branch independently replayed all 13,434 valid dual-receiver visits and retained the same 114 invalid visits. No detector call was lost. All 26,868 full candidate arrays, selected scout hints, native factor content and both scientific result arms matched the released fifth center, including the frequency outputs. The native archives keep the different compiled producer identities. Both lighter branches peaked at the charged 512 MiB limit with zero swap. [Whole-recording parity](lighter-comparison/parity.json) · [Observed services](lighter-comparison/resources.json) · [Prediction seal](lighter-comparison/prediction-lock.json)

| Recording | Detector CPU, released → lighter | Dual calls with wall ≤20 ms, released → lighter | P95 detector call wall, released → lighter | Whole pipeline wall, released → lighter | Whole pipeline CPU, released → lighter |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0255 | 127.99 → 116.12 s | 3,987 → 5,242 of 6,707 | 28.50 → 32.77 ms | 183.25 → 201.57 s | 225.13 → 217.27 s |
| DS29-0330 | 126.34 → 118.61 s | 4,378 → 5,023 of 6,727 | 26.06 → 31.97 ms | 202.90 → 162.50 s | 214.09 → 209.05 s |

The lighter kernel used 9.3% and 6.1% less detector CPU than the released fifth center. Its detector wall median fell from 19.43 to 17.66 ms on DS26 and from 19.06 to 18.03 ms on DS29. The lighter services ran after the first pair on each assigned core set. P95 call wall rose on both recordings, and end-to-end wall moved in opposite directions. Every branch processed the entire supplied validity inventory in offline replay. [Complete timing distributions and stage boundaries](lighter-comparison/deadlines.csv)

## Original v5 reference boundary

The four DS29 reference services used the official original worker, the same capture-era native file, causal catalogue and region, and policy-specific original requests. The original worker received no surveyed coordinates or measured error. All four completed successfully within the independent 600-second, 4 GiB zero-swap envelope. These service times include original evidence and figure preparation. The DS26 controls are the previously published position arms. [Original reference receipts and recorded predictions](reference-prediction-lock.json) · [Read-back of staged DS29 request and source digests](reference-binding-audit.json)

| DS29 original policy | Service wall | CPU | Charged peak |
| --- | ---: | ---: | ---: |
| No repair | 242.25 s | 221.50 s | 2.1 GiB |
| Selective gap | 282.67 s | 228.99 s | 2.2 GiB |
| Omitted track one | 322.53 s | 266.39 s | 2.2 GiB |
| Omitted tracks | 301.40 s | 252.53 s | 2.3 GiB |
