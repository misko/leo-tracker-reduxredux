# Waiting between wider antenna searches

Waiting two seconds after a failed wider search eliminated 47% of retries on each recording. It kept more successful measurements than spending the same number of retries at hash-selected times on each antenna and frequency. Final fitted error rose from 262 to 460 m on DS26-0237 and from 516 to 626 m on DS29-0082. Both missed the allowance of original v5 error plus 10%. [Recording-level scores](scores.csv) · [Retry counts](support.csv)

| Wider-search rule | DS26 retries / rescues | DS26 error, zero / fitted (km) | DS29 retries / rescues | DS29 error, zero / fitted (km) |
| --- | ---: | ---: | ---: | ---: |
| Original conditional search | 1,592 / 448 | 0.353 / 0.262 | 1,010 / 228 | 0.568 / 0.516 |
| Wait after failure | 840 / 315 | 0.533 / 0.460 | 530 / 164 | 0.420 / 0.626 |
| Same number per antenna and frequency | 840 / 250 | 0.485 / 0.399 | 530 / 134 | 0.830 / 1.301 |
| Wait after success | 1,265 / 284 | 0.469 / 0.359 | 848 / 165 | 0.596 / 0.960 |
| Same number per antenna and frequency | 1,265 / 347 | 0.471 / 0.387 | 848 / 179 | 0.582 / 0.559 |
| Oracle with advance knowledge of each success | 448 / 448 | 0.353 / 0.262 | 228 / 228 | 0.568 / 0.516 |
| Primary search alone | 0 / 0 | 0.889 / 0.780 | 0 / 0 | 1.094 / 1.279 |
| Original v5, no repair | — | 0.362 / 0.271 | — | 0.567 / 0.517 |

The original receiver retries with a wider search on the antenna that misses when the other antenna passes. The two causal rules observe the result only when they actually retry. After skipping a retry the detector returns the original primary candidates, including rejected candidates. The matched controls choose visits offline, independently of the rescue label at those visits. The oracle uses the eventual gate result and is a diagnostic upper bound on avoidable attempts. Rerunning the entire compact fit on its packet selections reproduced every scientific result field of the original conditional stream on both recordings. [Frozen protocol](PROTOCOL.md) · [Per-visit decisions](schedule-lock.json) · [Oracle comparison](oracle-audit.json)

With the wait-after-failure policy on DS29, fitting calibration reduced conditional RF RMS from 78.286 to 78.140 Hz and increased geographic error by 206 m. On DS26, RF RMS changed from 79.826 to 79.782 Hz and error improved by 73 m. All arms used the same per-policy observations, original region, causal satellite catalogue and numerical budgets. The chart for each policy includes all four original v5 options. [Fitted position charts](charts/fitted_c/modifications.pdf) · [Zero-calibration position charts](charts/c0/modifications.pdf) · [Retry decisions by recording](stage.pdf)

These are two five-minute recordings from one roof. The complete position inputs combine authenticated primary and conditional raw replay outputs. The ten new numerical fits took 36.7–77.2 seconds of wall time each under 512 MiB caps on host CPUs 22 and 23. The opportunity count is a count of detector calls. Separate saved-waveform trials measure costs when the online policy actually suppresses the wider search. [Measured fit times](position-time.csv) · [Online detector trial](../cadence-waveform/PROTOCOL.md)
