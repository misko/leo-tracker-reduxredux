# Native FFTW scout through complete saved-IQ positioning

Both native FFTW services reproduced the NumPy scout's selected hints, complete detector factor files and both calibration-arm positions exactly. They finished in **146.08 and 185.04 seconds** on the assigned host cores, versus **333.87 and 289.75 seconds** for the independent NumPy runs. The faster implementation preserved the geographic outcome of the differential policy. Both differential implementations met the original v5 +10% bound on **1/2** recordings in each calibration arm. Stock wide met it on **2/2**. [Frozen protocol](PROTOCOL.md) · [Parity audit](audit.json)

[Both position distributions](charts/index.html) · [Zero-calibration PNG](charts/c0/frontier-whole-fftw.png) · [Fitted-calibration PNG](charts/fitted_c/frontier-whole-fftw.png) · [Zero-calibration PDF](charts/c0/modifications.pdf) · [Fitted-calibration PDF](charts/fitted_c/modifications.pdf)

## Complete acquisition and gate parity

The two recordings come from the first-manifest hash selection frozen before the earlier whole replay. Both deployments use the same saved dual-receiver waveform, installed reader, acquisition clocks, original 25 km tile, causal TLEs, hinted 21-bin GLRT and phase-release receiver. This experiment started two additional FFTW services. It joined the independently sealed NumPy and stock controls only after sealing the fresh FFTW results. All six services completed within 450 s at 512 MiB peak charged cgroup memory and zero swap. [Source freeze](source-lock.json) · [Independent FFTW prediction seal](prediction-lock.json) · [Prior stock and NumPy study](../whole-replay/README.md)

| Recording | Total / valid visits | Receiver probes | Changed candidate arrays vs NumPy | Changed candidate arrays vs stock | Gate positives, stock → differential |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0168 | 6,774 / 6,774 | 13,548 | 0 | 8,044 | 24,050 → 25,160 |
| DS29-0604 | 6,771 / 6,756 | 13,512 | 0 | 8,866 | 17,508 → 18,522 |

All 27,060 selected rank-one hints, hint insertion decisions and final candidate arrays matched NumPy. Both complete native JSON factor files were byte-identical to NumPy, including all 43,682 gate positives. The invalid rows and clock metadata also matched. The difference from stock comes from the shared differential timing policy. It created 401 newly positive receiver probes on each recording and lost 21 and 17 stock positive probes on DS26 and DS29 respectively. The visit and audit files retain output hashes, counts, winners and measured clocks. [Per-visit measurements](visits.jsonl.gz) · [Stock/NumPy probe trace](../whole-replay/visits.jsonl.gz)

## Host service and 20 ms detector deadlines

| Recording | Deployment | Full service wall / cgroup CPU (s) | Complete detector wall p50 / p95 (ms) | Wall ≤20 ms | CPU ≤20 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0168 | Stock wide | 219.60 / 302.17 | 24.71 / 32.18 | 248/6,774 | 271/6,774 |
| DS26-0168 | NumPy differential | 333.87 / 495.76 | 51.74 / 66.35 | 0/6,774 | 0/6,774 |
| DS26-0168 | FFTW differential | 146.08 / 207.77 | 18.01 / 22.21 | 5,555/6,774 | 5,863/6,774 |
| DS29-0604 | Stock wide | 177.03 / 263.17 | 23.77 / 30.43 | 562/6,756 | 607/6,756 |
| DS29-0604 | NumPy differential | 289.75 / 451.96 | 50.43 / 64.97 | 0/6,756 | 0/6,756 |
| DS29-0604 | FFTW differential | 185.04 / 287.25 | 28.03 / 35.23 | 50/6,756 | 50/6,756 |

The table times acquisition, assembly and positioning from worker entry. The CSV also preserves the service supervisor's elapsed clock. The per-visit clock includes scout, hinted GLRT and native output decoding where applicable. FFTW used CPU pairs 0/1 and 8/9. The previous stock and NumPy services used pairs 14/15 and 22/23 under different schedules. The host kernel reports maximum frequencies of 5.5/5.7 GHz for 0/1 and 4.7 GHz for the other pairs. These elapsed and CPU times describe the full deployments under their actual assignments. The separate matched single-core evidence measured scout CPU medians of **19.19→6.17 ms** on the primary waveforms and **21.09→5.78 ms** on the confirmation waveforms. [Service and deadline data](deadlines.csv) · [Direct matched scout study](../differential-runtime/README.md)

## Geographic error and conditional frequency fit

| Recording | Original v5 no-repair error, zero / fitted (km) | Stock error, zero / fitted (km) | FFTW and NumPy error, zero / fitted (km) |
| --- | ---: | ---: | ---: |
| DS26-0168 | 1.515 / 1.551 | 0.805 / 0.796 | 1.724 / 1.722 |
| DS29-0604 | 0.982 / 1.041 | 0.735 / 0.734 | 0.760 / 0.775 |

Each method returned both estimates in both calibration arms. Stock met the +5% and +10% original no-repair v5 thresholds on both recordings. The differential policy met both thresholds on DS29 only. The standard chart shows all four original v5 options. [Position and v5 scores](scores.csv)

FFTW also matched NumPy's conditional RF fit exactly. Conditional RMS was 84.76 / 84.76 Hz at DS26 and 98.64 / 98.59 Hz at DS29. The corresponding stock values were 70.86 / 70.87 Hz and 95.52 / 95.48 Hz. These fits use each detector's selected observations. The geographic result uses the surveyed roof separately. [RF and threshold data](scores.csv)

The replay uses the standard capped `whole_iq` service with the verified FFTW scorer as a local sidecar to the hinted native detector. Its SHA-256 is `558e5832a1e489c23bff6ec2dd3203a780b9473c7e8284c00290621ee269c4f8`. The publication can be regenerated from the two independent seals and their published traces. [Chart specification](figures.json) · [Figure data seal](figure-lock.json)

```sh
python -m tools.pipeline_eval.qualification.whole_fftw_results publish
```
