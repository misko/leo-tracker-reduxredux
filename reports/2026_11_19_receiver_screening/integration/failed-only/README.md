# Stock-first compact v5 with diagnosed exception recovery

The archive replay preserved all 149 stock compact fixes and added five. Three other diagnosed failures reached a scientific withholding. The policy left the original timeout and missing-native input in the denominator. Four fresh CLI probes confirmed an unchanged stock fix, a recovered previous-orbit assertion, a family-excluded repair that withheld, and a genuine unavailable input. [Both-arm roof and excluded-32 charts](charts/index.html), [prediction seal](prediction-lock.json).

The live route uses the unchanged five-refresh compact worker first. It retries the complete same request only for the exact orbit-grid or family-excluded calibration failure messages, or an attempted bare assertion with the actual frozen `orbit_modes.previous_bank` traceback at `assert good.all()`. Both workers bind the same complete captured GLRT, latest causal element snapshot, track configuration, request and original tile. Stock scientific outcomes and unrelated failures retain the returned status, positions, diagnostic fields and raw cause. In the archive replay, two verified standalone causal diagnostics supply the original previous-orbit witnesses. The mask, corpus and original four-role scores were sealed before comparison. [Protocol](PROTOCOL.md), [input and source lock](source-lock.json), [routing decisions and scores](scores.csv).

## Archive position and RF results

The table uses all 159 offered recordings. Each cell reports fixes / fixes within 5 km, followed by median / P95 error in km over published positions.

| Receiver | `c=0` | Fitted `c` |
| --- | --- | --- |
| Original v5 baseline | 143 / 141 · 0.980 / 3.155 | 143 / 141 · 0.988 / 3.266 |
| Original v5 selective gap | 141 / 139 · 0.974 / 2.833 | 141 / 139 · 0.949 / 2.589 |
| Original v5 one omitted track | 138 / 136 · 0.965 / 3.220 | 138 / 136 · 0.973 / 3.343 |
| Original v5 two omitted tracks | 132 / 130 · 0.970 / 3.399 | 132 / 130 · 0.993 / 3.378 |
| Unchanged compact | 149 / 146 · 0.990 / 3.545 | 149 / 146 · 1.014 / 3.541 |
| Stock-first archive replay | 154 / 151 · 0.989 / 3.483 | 154 / 151 · 1.009 / 3.484 |

The paired original-baseline denominator was 142 in each arm. The router and unchanged compact were within 110% of the paired original error on 138/142 in both arms. On those same recordings the router/original median and P95 were 0.980/3.159 versus 0.982/3.173 km at `c=0` and 0.996/3.288 versus 0.994/3.304 km with fitted `c`. On the excluded 32, the router increased fixes from 22 to 27 and within-5-km fixes from 21 to 26. Its median/P95 was 1.022/4.661 and 1.137/4.636 km, with all 15 paired original-baseline fits within 110% in each arm. The recovered five had no original-baseline position and correspond to the increased coverage. [Full subgroup statistics](summary.json).

Conditional RMS uses each solver’s own selected evidence. Across all 159, the medians for `c=0` / fitted `c` were 109.78 / 100.29 Hz for the original baseline, 69.61 / 69.58 Hz for unchanged compact, and 69.32 / 69.30 Hz for the route. The RF measures describe fit on retained support. Geographic error, smaller paired tails and changes in coverage are scored separately. [Measured repair outcomes](measured-repairs.jsonl.gz).

## Modular wall time and the operating cap

The archive time estimate concatenates measured standalone stock and repair intervals in serial order. Across the 158 attempted recordings, the stock median/P95 was 124.73/197.37 s and the serial estimate was 126.34/197.84 s. The eight retries added 612.83 s to 20,245.09 s of archived stock worker intervals. The archived DS26-0217 timeout retains its measured elapsed lower bound and the missing-native case carries no worker interval. Nine archived stock fixes had measured intervals over 195 s. All nine are retained in the original-timing archive figures. A uniform 195-second shadow cutoff would censor those recorded intervals. This sensitivity does not forecast completion on a different run schedule. [Cap sensitivity](cap-sensitivity.json), [archive intervals](scores.csv).

The four fresh runs used a 195-second cap per stage and nice 10 on separate single cores. Their results matched the archived status and both arm positions exactly.

| Fresh recording | Stock launch wall, s | Repair launch wall, s | Routed result |
| --- | ---: | ---: | --- |
| DS26-0036 | 49.54 | — | Stock fix, 1.260 / 1.196 km |
| DS26-0285 | 38.77 | 53.91 | Recovered fix, 2.615 / 2.608 km |
| DS26-0191 | 67.05 | 63.94 | Repaired branch withheld both arms |
| DS26-0172 | — | — | Native input unavailable, no launch |

The first fresh probe exposed an optional Python caret line between the already exact prior-orbit assertion source line and the bare exception. The final matcher accepts that traceback formatting and still requires the identical frame and failure. The initial receipts are retained, and all four final probes were rerun after the formatter-aware predicate was sealed. [Fresh per-stage and raw status summary](fresh-summary.json), [both fresh source seals](fresh-prediction-lock.json).

## Reproduction

```sh
python -m tools.pipeline_eval run --variant v5_failed_only --panel ds26-all159 --case DS26-0285 --timeout 195
python -m tools.pipeline_eval run --variant v5_causal_orbit_fit --panel ds26-all159 --case DS26-0285 --timeout 195
python -m tools.pipeline_eval.qualification.failed_only_results seal
python -m tools.pipeline_eval.qualification.failed_only_results score
python -m tools.pipeline_eval figures --panel screening --variant failed-only-all159 --variant failed-only-excluded32 --arm both --out /tmp/leo-failed-only-charts
```
