# Complete-IQ deadline and runtime companion

The stock four-region receiver completed **73,832 of 132,740** dual-receiver detector calls within 20 ms wall time, compared with **28,302 of 132,740** for the released fifth center. Both receivers processed complete saved IQ faster than its recorded arrival span on all 20 recordings. Including assembly and both position arms, stock finished inside the corresponding recorded span on 20/20 and fifth center on 18/20. These are measured offline host replays. [Stage chart](stage.pdf) · [Matched recording table](stage.csv)

| All 20 recordings | Stock four regions | Released fifth center |
| --- | ---: | ---: |
| Complete verified raw services | 20 | 20 |
| Returned both position arms | 20 | 20 |
| Complete detector calls within 20 ms wall | 55.62% | 21.32% |
| Median of recording-level detector wall P50 | 16.68 ms | 31.20 ms |
| Median raw phase wall time | 107.76 s | 135.61 s |
| Median position phase wall time | 71.17 s | 75.67 s |
| Median raw through both position arms | 176.74 s | 214.19 s |
| Median charged worker CPU | 191.52 s | 316.54 s |
| Median journal service wall among measured | 180.71 s (18 runs) | 214.70 s (20 runs) |

The two fifth-center worker overruns were DS26-0162 at 303.41 s and DS29-0127 at 302.85 s. Both services finished inside their 450 s service limit and published both arms. The recorded delivery span is taken from each verified raw receipt. A 20 ms call deadline concerns one complete dual-RX invocation, including the differential scout when applicable. Comparing an unpaced read with the delivery span describes offline throughput and excludes paced queues and realtime delivery behavior. [Per-run clocks and support](resources.csv)

## Comparability

Six pairs ran sequentially under their study's same-core protocol. DS26-0197 and DS29-0316 are the original stock-first pair. DS26-0026 and DS29-0047 are the earlier fresh pair, and DS26-0255 and DS29-0330 are the newer fresh pair. In each fresh pair one recording ran stock first and the other ran fifth first. On these six pairs, **37,020/40,440 (91.54%)** stock calls and **21,238/40,440 (52.52%)** fifth calls completed within 20 ms wall. Median raw phase was 84.06 s versus 111.08 s. Fifth-center total worker wall was higher on all six, by 0.44 to 39.91 s. The remaining 14 contrasts compare separately scheduled runs with different core assignments and observed host conditions. The all-20 elapsed comparison is descriptive. [Per-pair schedule and signed elapsed changes](stage.csv) · [Group totals](summary.json)

The official twelve use their fixed-primary stock attempts, including the exact same service invocations present in the two overlapping crossover rows. The sensitivity table instead uses the first eligible stock attempt for those twelve and retains the other eight stock runs. That policy still has 20 complete raw inputs and 132,740 measured calls, with 72,463 (54.59%) at or below 20 ms. It has 19 total completed workers and 19 paired position results. The earliest DS29-0082 stock replay spent 334.05 s in the complete raw phase and timed out after 360.08 s. The fit and complete worker elapsed fields remain empty. [Separate first-attempt ledger](first-attempt.csv) · [Original twelve-attempt policy](../../track-recovery/wide-roster/README.md)

Each row binds the recording, clock, invalid visits, receiver projection, catalogue, original request, actual detector digest and installed solver source. The worker clock runs from start through the publication phase and includes raw processing, assembly and the single position worker for both zero and fitted calibration. Charged CPU uses the worker cgroup's stage boundaries. Systemd journal service duration is a separate boundary. The two archived stock receipts without an authenticated journal duration retain blank journal fields and their measured worker and supervisor clocks. Per-call CPU and wall quantiles stay recording-level. [Receipt and output hashes](prediction-lock.json) · [Official roster](../complete-roster/roster.json)

## Offline rebuild

    MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.complete_timing \
      --out /tmp/complete-timing

This command reads the frozen reports and rebuilds the tables and figure without I/Q reads or receiver execution.
