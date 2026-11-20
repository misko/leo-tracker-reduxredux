# Partner on a strict primary hit on new complete recordings

DS26-0066 and DS29-0085 were selected by first-segment acquisition manifest SHA-256, before any geographic scoring. They lie outside the earlier 22 complete receiver comparisons and prior eight antenna-intervention cases. Both come from the same roof. DS26-0066 has earlier captured-factor compact evidence. The new tests measure the complete wide detector path on archived IQ. All 212 declared payload and index members of each recording passed existence and size checks. DS26 is upper-edge and DS29 lower-edge. [Protocol](PROTOCOL.md) · [Selection and exclusions](selection.json) · [Frozen sources and original inputs](source-lock.json)

For every valid visit, stock searches both physical antennas across the same four timing regions. The candidate alternates its primary independently at each physical RF center and runs the second antenna only after a strict fractional gate hit by the selected primary. It keeps all four-region candidates on measured lanes, with an empty partner slot on a miss. Both policies use the same archived dual-receiver CI16 input, original capture-invalid visits, clocks and per-visit RF, original 25 km offer and causal catalogue. Both use the unchanged compact phase release and both calibration arms. [Physical dispatch plans](dispatch/) · [Frozen original DS29 policy requests](reference-source-lock.json)

Each recording runs stock then candidate on its fixed core pair, 2/3 for DS26 and 4/5 for DS29. The whole-IQ services use 300 seconds and 512 MiB charged memory with zero swap. The four original DS29 archived-native v5 controls use separate numerical cores 22/23 and the original causal request under a 600-second, 4 GiB zero-swap cap. The DS26 controls come from the published original four-policy archive.

## Actual antenna calls and timing

All four whole-IQ services finished with both calibration arms. Each replay processed every valid visit, with no scheduling drops. DS26 had 6,773 valid visits and zero archive exclusions. DS29 had 5,613 valid visits and 1,159 original exclusions. Both captured delivery spans were approximately 300 seconds. The projected conditional native document matched the measured bytes on both recordings. The recorded decision for every valid visit matched the independently projected primary gate. [Position and raw prediction seal](prediction-lock.json) · [Exact physical and gate parity](parity.json)

| Recording | Stock physical lane calls | Conditional primary / partner calls | Co-visible partner hits retained | Partner-only hits omitted |
| --- | ---: | ---: | ---: | ---: |
| DS26-0066 | 13,546 | 6,773 / 2,029 | 1,174 | 877 |
| DS29-0085 | 11,226 | 5,613 / 1,375 | 608 | 779 |

The conditional policy ran 35.0% fewer antenna calls on DS26 and 37.8% fewer on DS29. Detector CPU fell by 32.1% and 33.1% respectively. The sequential order is fixed because stock establishes the audit of the archived visit metadata. All four services reached 512 MiB charged peak memory with zero swap. Call latency includes all requested antenna analysis and dispatch for one whole visit. Whole-pipeline wall includes the position fit, and the services replayed the archive without pacing. [Full timing distributions](deadlines.csv) · [Observed services and resource limits](resources.json)

| Recording and policy | Calls with wall ≤20 ms | P95 call wall | Detector CPU | Whole pipeline wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0066 dual | 5,900 of 6,773 | 25.48 ms | 106.66 s | 189.49 / 193.86 s |
| DS26-0066 partner on hit | 6,396 of 6,773 | 20.30 ms | 72.37 s | 105.15 / 143.04 s |
| DS29-0085 dual | 5,029 of 5,613 | 24.29 ms | 87.05 s | 156.73 / 151.63 s |
| DS29-0085 partner on hit | 5,276 of 5,613 | 20.57 ms | 58.23 s | 83.87 / 115.19 s |

## Position accuracy and frequency fit

Partner on hit increased horizontal error on both recordings in both calibration arms. The increase was 179–180 m on DS26 and 536 m on DS29. Both policies met the +5% and +10% thresholds relative to original no-repair v5 on one of two recordings in each arm. DS29 met both thresholds. All attempted fixes and original policies appear in the per-recording charts. [Scores against all four original v5 options](scores.csv) · [Both calibration arms and per-recording charts](charts/README.md)

| Recording | Original no-repair v5, `c = 0` / fitted `c` | Dual four regions, `c = 0` / fitted `c` | Partner on hit, `c = 0` / fitted `c` |
| --- | ---: | ---: | ---: |
| DS26-0066 | 1.244 / 1.218 km | 2.201 / 2.191 km | 2.379 / 2.371 km |
| DS29-0085 | 2.407 / 2.062 km | 1.216 / 1.093 km | 1.753 / 1.628 km |

Conditional frequency residuals depend on the observations that each policy retains. Partner on hit increased DS26 conditional RMS from 73.612 / 73.570 to 76.951 / 76.866 Hz. It decreased DS29 conditional RMS from 93.701 / 93.595 to 92.339 / 92.044 Hz while geographic error increased. Within each fixed candidate set, fitting `c` decreased conditional RMS by 0.042 / 0.084 Hz for the DS26 dual and hit policies and by 0.106 / 0.295 Hz for DS29. The matched calibration pairs keep candidate sets, clocks, causal priors and numerical budgets fixed. [Calibration differences and frequency scores](calibration.csv)

## Original DS29 controls

The four genuine original v5 services all completed and returned both arm coordinates on the exact capture-era native input. All four selected the same coordinates within each calibration arm. The authenticated original worker timing includes its evidence and plot generation and begins at the numerical factor boundary. [Original terminal receipts](reference-prediction-lock.json) · [Exact staged-request and catalogue audit](reference-binding-audit.json)

| Original DS29-0085 policy | Service wall | CPU | Charged peak |
| --- | ---: | ---: | ---: |
| No repair | 299.41 s | 215.38 s | 1.6 GiB |
| Selective gap | 300.72 s | 210.48 s | 1.6 GiB |
| One omitted track | 228.12 s | 216.73 s | 1.5 GiB |
| Two omitted tracks | 230.55 s | 219.84 s | 1.6 GiB |
