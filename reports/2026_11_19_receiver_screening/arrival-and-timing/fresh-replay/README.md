# Two newly selected whole-IQ roof recordings

Stock and fifth center both returned 2/2 positions in each calibration arm on the fresh pair, with all fixes within 5% of original v5. Their position errors differed by at most 8 m across the fresh pair. The fifth center took 25–28 s longer from IQ through position on the same core pairs and missed more 20 ms detector targets. [Zero-calibration chart](charts/c0/fresh-replay-all.png) · [Fitted-calibration chart](charts/fitted_c/fresh-replay-all.png) · [Fresh scores](scores.csv)

This benchmark repeats the stock wide and genuine fifth-center comparison on DS26-0026 and DS29-0047. Selection used the lowest first-segment manifest digest after applying the earlier whole-IQ exclusion roster and confirming the earliest eligible recording's raw files. Both recordings use the same original roof and 25 km offer. The independent pair is reported separately from the earlier six. [Protocol](PROTOCOL.md) · [Full metadata rankings, eligibility and exclusions](selection.json) · [Frozen whole-IQ execution](source-lock.json)

The eight published roof16 DS29 cases were already used in complete replays. The expanded frozen DS29 archive contains 615 recordings and captures the original native contracts, causal catalogues and deployment operator's roof coordinates. DS29-0047 was the first authorized, available capture in the manifest ordering. Its 14 segments and every payload/index member passed the archive preflight. Its four comparison outcomes run the unchanged original archived v5 policies on the capture-era native input. DS26-0026 uses the published four-policy outcomes. Both branches and both original-policy calibration arms use their respective matched requests and observation sets. [Original reference source lock](reference-source-lock.json)

The metadata gate ranked 119 DS26 candidates after eight prior whole-IQ exclusions. It ranked 595 DS29 candidates after eight prior whole-IQ exclusions, nine unsupported capture producers and three missing original native inputs. The lowest ordered candidate in each group passed physical file preflight, with 212 segment payloads and indexes checked per recording. Earlier DS26-0026 comparisons began at stored factors. [Selection ledger](selection.json) · [Earlier stored-factor boundary](../../integration/compact-entry/PROTOCOL.md)

The stock and fifth-center services used the exact earlier binaries and installed compact phase release. DS26 ran stock first on cores 4/5. DS29 ran the candidate first on cores 6/7. The whole recorded boundary uses a 450-second cap, 512 MiB charged memory and zero swap. The original DS29 capture-era factor fits use one numerical thread per core on two serial lanes, a 600-second cap and 4 GiB with zero swap. Their factor-to-position times have a separate measurement boundary.

## Capture coverage and resources

All four complete whole-IQ services completed inside the enforceable cap and charged 512 MiB at peak with zero swap. DS26 retained all 11 original invalid visits and DS29 retained all 57. The branch comparison requires identical complete recording manifests, clocks, exclusions and noncandidate physical probe metadata. Positive probe counts gained 367/409 and lost 9/10 on DS26/DS29. Exact passing stock candidate payloads, compared after removing ordinal rank, were retained for 17,834/18,944 and 19,116/20,279 respectively. [Native and visit seal](raw-prediction-lock.json) · [Probe audit](probe-audit.json) · [All complete per-visit hashes and timings](visits.jsonl.gz)

| Recording and branch | Valid dual visits | Complete calls ≤20 ms wall | Call wall P95 | Pipeline wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0026 stock | 6,759 | 6,080 | 23.79 ms | 161.47 / 183.37 s |
| DS26-0026 fifth center | 6,759 | 2,932 | 39.00 ms | 189.59 / 226.68 s |
| DS29-0047 stock | 6,712 | 5,659 | 31.42 ms | 166.50 / 189.36 s |
| DS29-0047 fifth center | 6,712 | 3,070 | 35.88 ms | 191.77 / 216.59 s |

These are single observed runs on fixed matched core pairs. Call wall includes the full detector boundary. The fifth-center scout contributes to that boundary. [Whole-service receipts](resources.json)

## Position, frequency and original references

Every two-value entry gives `c = 0` / fitted `c`. Both methods met the 5% and 10% thresholds relative to original no-repair v5 on **2/2** recordings per arm. The canonical charts include all four original v5 policies. [Per-policy scores](scores.csv) · [All calibration plates, zero](charts/c0/modifications.pdf) · [All calibration plates, fitted](charts/fitted_c/modifications.pdf)

| Recording | Original v5 no-repair error | Stock wide error | Fifth-center error | Conditional RMS, stock → fifth |
| --- | ---: | ---: | ---: | ---: |
| DS26-0026 | 1.630 / 1.560 km | 0.547 / 0.553 km | 0.548 / 0.545 km | 84.532 / 84.523 → 86.932 / 86.883 Hz |
| DS29-0047 | 0.727 / 0.702 km | 0.392 / 0.355 km | 0.399 / 0.358 km | 93.905 / 93.948 → 95.883 / 95.806 Hz |

On DS26-0026, fitting `c` changed the stock and fifth position errors by +0.006 and −0.003 km, and changed conditional Doppler RMS by −0.010 and −0.049 Hz. On DS29-0047, fitting `c` reduced the errors by 0.037 and 0.041 km while changing conditional RMS by +0.043 and −0.077 Hz. The DS29 conditional frequency objectives changed by −3.590 and +7.614 respectively. RF measures describe the observations each detector selected. [Paired calibration and frequency contrasts](calibration.csv)

All four original DS29 services published both positions on the authenticated capture-era native input. The unchanged original worker used the same actual 72-hour causal catalogue roster and TrackConfig across the four requests, and the worker artifact hashes bind each request and result. [Original prediction seal](reference-prediction-lock.json) · [Canonical request and artifact digest audit](reference-binding-audit.json)

| Original DS29-0047 policy | Factor-to-position wall | Cgroup CPU | Peak cgroup memory |
| --- | ---: | ---: | ---: |
| No repair | 221.54 s | 183.73 s | 2.155 GiB |
| Selective gap | 272.68 s | 191.93 s | 2.171 GiB |
| Omitted track, one | 220.55 s | 192.75 s | 2.206 GiB |
| Omitted tracks | 243.64 s | 184.58 s | 2.184 GiB |

## Eight distinct recordings

The companion joins both fresh recordings with the previous six only after checking disjoint IDs and matching stock binary, fifth-center binary, FFTW sidecar, raw processing source closure, and installed compact numerical bytes. Both methods returned a fix on all eight recordings in both arms. The eight recordings share one roof and include the four retrospective crossover cases. [Pooled source cross-check](eight-authority.json) · [Eight-recording zero-calibration chart](charts/c0/fresh-replay-eight.png) · [Eight-recording fitted-calibration chart](charts/fitted_c/fresh-replay-eight.png)

| Statistic across eight recordings | Zero calibration, stock → fifth | Fitted calibration, stock → fifth |
| --- | ---: | ---: |
| Within 5% of original v5 | 5/8 → 6/8 | 5/8 → 6/8 |
| Within 10% of original v5 | 6/8 → 6/8 | 5/8 → 6/8 |
| Median error | 0.763 → 0.654 km | 0.765 → 0.696 km |
| P95 error | 1.910 → 1.657 km | 1.872 → 1.675 km |

The fresh pair reproduced the stock accuracy with extra detector work. The eight-recording distribution retains large improvements and regressions from the earlier cohort. [All eight per-arm scores](eight-scores.csv) · [Per-cohort distributions](summary.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.fresh_replay_results score
.venv/bin/pytest -q tests/pipeline_eval/test_fresh_replay.py tests/pipeline_eval/test_screening_figures.py
```
