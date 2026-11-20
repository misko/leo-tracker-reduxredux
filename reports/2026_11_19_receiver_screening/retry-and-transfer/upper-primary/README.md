# Primary-only original GLRT on DS29-0082

Removing the original 22-anchor retry increased survey error from **0.568 to 1.094 km** at `c = 0` and from **0.516 to 1.279 km** with fitted `c`. The complete primary-only stream preserved all 9,736 physical probe rows while dropping 228 gate-positive receiver probes and 1,018 dense FFT grids. [Source lock](source-lock.json) · [Native input lock](primary-lock.json)

## Saved-IQ replay

The original producer evaluates 12 primary anchors on both receivers. It retries with 22 anchors on a receiver whose primary misses when the other receiver passes the fractional gate. The field-exact replay's sealed grid ledger distinguishes 12-anchor and 22-anchor FFT work and preserves conditioned-CFO tie-guard repeats. The measured worker traces confirmed 1,010 physical retries, including eight visits with a repeated 22-anchor grid and 228 visits where the retry passed the gate. [Historical field-exact replay](../../pilot-search-and-region/field-exact-waveform/README.md) · [Replay protocol](PROTOCOL.md)

Four capped workers recomputed both physical receivers from saved CI16 on all 1,010 retry visits. The complete factor stream incorporates the authenticated conditional replay's rows on the 3,858 no-retry visits. Clock anchor, delivery clocks, physical exclusions and receiver ordering match the original archive. The saved-IQ launch checks reproduced all 15 original conditional outputs and both physical retry directions. Seven no-retry controls had two misses and four had two positives. [Preflight evidence](receipts/smoke.json) · [Complete primary-only factors](native.json.gz)

| Original GLRT policy | Physical probes | Candidates | Rejected candidates | Gate passes | Positive probes |
|---|---:|---:|---:|---:|---:|
| Primary-only 12 anchors | 9,736 | 41,992 | 37,819 | 4,173 | 1,640 |
| Conditional 12/22 anchors | 9,736 | 42,162 | 37,580 | 4,582 | 1,868 |

The two policies gave identical complete output on 8,726 probes. The 228 gate-positive changes were losses when the conditional retry was removed. [Gate audit](audit.json) · [Changed visits](changed-visits.csv)

## Position and RF calibration

The compact primary-only solve used 1,640 observations on 52 tracks. The original conditional solve used 1,868 observations on 61 tracks. In each policy both calibration arms shared the same observations, candidates, priors and search budget. All positions used the original causal catalogue, request and 25 km offer. The publisher sealed both calibration arms before reading the survey reference. [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [Coordinates](receipts/actual/position.json)

| Detector or v5 control | Survey error, `c = 0` (km) | Survey error, fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Original primary-only 12 anchors | 1.0938 | 1.2788 | 75.365 / 75.251 |
| Original conditional 12/22 anchors | 0.5681 | 0.5158 | 97.003 / 96.684 |
| Full wide four-region | 2.4892 | 2.3457 | 84.421 / 84.248 |
| Original v5 baseline | 0.5669 | 0.5172 | 97.004 / 96.684 |
| Original v5 selective-gap | 0.5669 | 0.5172 | 97.004 / 96.684 |
| Original v5 omitted-track-one | 0.1154 | 0.4862 | 109.559 / 105.471 |
| Original v5 omitted-tracks | 0.1154 | 0.4862 | 109.559 / 105.471 |

Fitting `c` on the primary-only stream lowered conditional RMS by 0.115 Hz and moved the frequency score from 5,054.870 to 5,062.446. The fitted position moved 185 m farther from the survey point. Compared with the original conditional detector, the primary-only stream gave lower RMS and greater survey error in both arms. [Per-arm scores](scores.csv) · [Original v5 controls](v5-controls.csv) · [`c = 0` chart](charts/c0/modifications.pdf) · [Fitted `c` chart](charts/fitted_c/modifications.pdf)

## Measured host timing

The selected replay authenticated all 106 compressed IQ chunks and finished in **144.53 s** wall time. Detector work on the 1,010 selected visits used **516.24 CPU s**, and total worker CPU including reading, decoding and authentication was 548.34 s. The largest worker reached 197.89 MiB RSS and its cgroup reached 512 MiB with zero swap. No selected detector call finished within 20 ms. The qualified pruned fine-CFO kernel made 16,504 calls with zero fallbacks. [Raw supervisor receipts](receipts/raw-exits.json) · [Per-visit timing](timing.csv)

| Timing on original retry visits | Historical conditional | Measured primary-only |
|---|---:|---:|
| Detector CPU, median / p95 (ms) | 468.52 / 1,099.28 | 499.54 / 584.31 |
| Detector wall, median / p95 (ms) | 539.62 / 1,806.10 | 502.30 / 662.93 |
| Detector CPU total (s) | 592.42 | 516.24 |
| Dense grids in the complete recording | 10,875 | 9,857 |

The full historical conditional detector used 1,892.65 CPU seconds. Combining historical nonretry CPU with newly measured retry CPU gives a cross-execution estimate of 1,816.47 CPU seconds, or 454.12 seconds under ideal four-core division. The historical timing used CPUs 0, 1, 4–7, 20 and 21. The new timing used CPUs 12–15. [Timing chart](timing.pdf) · [Stage descriptor](stage-figure.json)

The compact service took 95.28 s wall and 35.16 cgroup CPU seconds. It peaked at 272.46 MiB with zero swap. The first compact launch stalled in a bulk XFS directory allocation before starting the receiver. The recorded service ran from local ext4 scratch using byte-identical copies of the sealed native input and raw receipts with the same original track configuration, causal catalogue and offer. [Native input lock](primary-lock.json) · [Executed compact command](receipts/actual/terminal.json) · [Resource receipt](receipts/actual/end.json)
