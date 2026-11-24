# Two-case raw Cairo comparison with the DS30-0107 withholding control

The Cairo-enabled DS30-0107 child exited successfully in **0.540487 s wall / 0.539035 CPU s** and withheld both calibration arms. With the actual DS30-0016 Cairo fix, the median paired Cairo-to-installed elapsed ratio is **0.537759** and the ratio of totals is **0.671255**. The median passes the 1.6× threshold of 0.625. The sum misses it, and neither statistic reaches 2×. Both cases reached their enrolled scientific decision. [Frozen protocol](history-risk-0107-cairo-protocol.md) · [Machine receipt](measurements/history-risk-0107-cairo.json.gz)

| Physical case | Cairo child elapsed / CPU s | Reused installed v3 elapsed / CPU s | Elapsed Cairo ÷ installed | Decision |
| --- | ---: | ---: | ---: | --- |
| DS30-0107 | 0.540487 / 0.539035 | 1.497018 / 1.495600 | 0.361042 | Withheld, zero PNGs |
| DS30-0016 | 7.676812 / 7.658570 | 10.744677 / 10.742462 | 0.714476 | Complete, eight verified PNGs |
| Sum | 8.217299 / 8.197605 | 12.241696 / 12.238062 | 0.671255 | Two expected decisions |

The CPU median paired ratio is 0.536669 and the CPU ratio of sums is 0.669845. These use actual fresh CLI launch-through-verified-exit clocks. The installed v3 denominators are the prior measured stock processes for the same two recordings. Neither stock process was rerun. The earlier ordinary candidates took 0.614869 s on DS30-0107 and 8.828567 s on DS30-0016. The DS30-0107 candidate withholds before rendering, so its elapsed difference from the ordinary candidate cannot be credited to Cairo drawing. This is a one-fix, one-withhold cohort on resident inputs, with sequential launches.

The new DS30-0107 launch admission was 0.102476 s and the original paired admission was 0.107613 s. The measured DS30-0016 Cairo preparation was 0.036025 s. Charging these separately recorded Cairo admissions on top of both child elapsed times, while retaining the published installed child clocks, gives **0.573662** median and **0.682569** summed. Both gates therefore have the same outcomes under that sensitivity. The DS30-0016 launcher clock begins after initial stage readiness. The fixture installation, read-only namespace and lock wait are outside both child clocks. [DS30-0016 raw Cairo follow-up](history-risk-0016-cairo.md)

## Signed DS30-0107 output

The fresh child reproduced the exact native packet and terminal from the already sealed ordinary candidate. One traversal of the 29 issued windows produced 27 admitted stereo visits, 54 signed opportunities, 19 factors, and the same exclusions for visits 27 and 28. The latter remains an empty capture window. Its scan report is byte-identical to the earlier ordinary report. Its opportunity projection also matches installed v3 per receiver and channel, and the full native opportunity ledger matches. The original region, sample-clock cutoff and recording authority were verified. The graph proof withheld as `no_active_curvature`. Fixed-zero and fitted calibration each had a null location and no RF value. The standard store returned no arms, path, grid or PNG artifacts. No scientific publication or Cairo renderer was entered.

The recording was the existing tmpfs stage exposed under its original canonical pathname by a private read-only bind. All 8,184 payload pages and 20 index pages were resident before and after exit. The 51 causal copies were resident, the current source and library pins verified, and the candidate recorded zero input blocks or major faults. The benchmark held the global Gauss lock on CPU 2 at nice 15 and I/O priority 7 with one numerical thread. No new waveform transfer, original backing reads, or collection occurred.

The timed source is `428b862f6`. The offline scan-report comparison expanded the proof using the existing products after exit. Fourteen focused tests passed. To reproduce, invoke `history_risk_0107_cairo launch <fresh-tmpfs-root>` in the existing read-only DS30-0107 namespace and the standard shared Gauss environment. Run `score <result-root> --output <external-receipt>` separately. [Trial runner](history_risk_0107_cairo.py) · [Tests](../../../tests/pipeline_eval/test_history_risk_0107_cairo.py)
