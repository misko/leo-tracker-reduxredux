# Causal rolled-pilot excess on wide GLRT factors

The selector uses a candidate's exact and symbol-rolled fractional GLRT scores and a recent background scale from the same receiver, channel, RF and edge. In the six locked wide replays, it preserved 23,837 positive probes and changed 1,536 winners. Of those substitutions, 1,199 were within 1 kHz of folded CFO and 0.2 µs of wrapped epoch. The other 337 shifted folded CFO by more than 1 kHz. The per-recording factor scan took 55–108 ms. [Predeclared protocol](PROTOCOL.md) · [Factor audit](factor-audit.json) · [Winner replacements](winner-changes.json.gz)

The adjusted phase-release finished 5/6 positions in each calibration arm. Unchanged wide finished 6/6. Among the four reserves, the number of fixes within 110% of original v5 error fell from three to zero at `c = 0` and from two to one with fitted `c`. All six recordings come from one roof with containing offers. [Scores](scores.csv) · [Charts](figures.json)

## What the control measures

The capture-era, narrow and wide archives all satisfy the same `exact − rolled ≥ 0.025` gate on their authenticated development cases. The rolled template uses symbol roll 17, a separate residual CFO maximum and the exact template's selected fractional timing. The recorded candidate lists contain conditioned template scores. An independent full-search false-alarm probability would require off-epoch search cells or prior no-emitter trials across the full search. [Native fractional score implementation](../../../../native/adaptive/detector/kernel/private/full_search.c) · [Score semantics audit](pilot-semantics-audit.json)

The rule ranks passing peaks by `(exact − rolled) / (rolled + Q95)`, where `Q95` is the earlier lane's 95th percentile of within-visit rolled maxima. It uses at most 128 nonempty earlier visits and starts ranking after 32. Recording-wide median Q95 ranged from 0.0465 to 0.0489. Across the six captures, 4,495 of 73,825 available current rolled maxima exceeded their earlier Q95. The proxy behaves as a relative score scale. It preserves the original pilot gate and supplies the release's original Graph with one numerically authentic winning peak per positive probe. [Filter implementation](../../../../tools/pipeline_eval/variants/peak_null.py) · [Per-capture proxy coverage](factor-audit.json)

The 80 kHz coarse CFO grid has 21 nominal centers for ±800 kHz and 11 for ±400 kHz. At the archived rolled-tail threshold the median fitted maximum-CDF exponent for the selected exported candidates ranged from 3.28 to 3.38 across the development narrow and wide arms. This descriptive statistic accounts for correlation only among the exported template values. Using the same wide lane's within-visit maximum scales for retained alternatives without assuming 21 independent search cells. [Effective exported-slot audit](pilot-semantics-audit.json)

## Score-boundary controls

- Exchanging rolled values by a half-turn within the same lane and candidate-count stratum changed 8,680 winners. This reproduced 308 of the original 1,536 replacements. The pairing of exact and rolled values at the same probe materially affected the ranking.
- Each development capture contributed an exchangeable score-level null of 2,048 probes with eight slots. The unchanged gate admitted eight probes in each panel, and the selector preserved those eight without a winner change. When exact and rolled scores were identical, both panels admitted zero. These are score-level controls sampled from exported rolled scores.
- A single planted excess of 0.075 per probe ranked first on 2,044/2,048 and 2,048/2,048 probes for both rules. A separate 64-probe test with a broader discrete score distribution gave 64/64 for margin and 58/64 for the adjusted rule. [Control data](pilot-semantics-audit.json) · [Component tests](../../../../tests/pipeline_eval/test_peak_null.py)

## Phase-release receiver outcomes

| Split and rule | Fixes per c arm | c = 0 median / max error | Fitted-c median / max error | Within 110% of v5, zero / fitted |
|---|---:|---:|---:|---:|
| Development, unchanged wide | 2/2 | 1.746 / 2.489 km | 1.641 / 2.346 km | 1/2 · 1/2 |
| Development, adjusted | 2/2 | 1.615 / 2.574 km | 1.497 / 2.406 km | 1/2 · 1/2 |
| Reserve, unchanged wide | 4/4 | 1.057 / 1.326 km | 1.062 / 1.338 km | 3/4 · 2/4 |
| Reserve, adjusted | 3/4 | 1.041 / 1.058 km | 0.958 / 1.051 km | 0/4 · 1/4 |
| All six, original v5 | 6/6 | 0.818 / 1.320 km | 0.832 / 1.458 km | 6/6 · 6/6 |
| All six, unchanged wide | 6/6 | 1.162 / 2.489 km | 1.127 / 2.346 km | 4/6 · 3/6 |
| All six, adjusted | 5/6 | 1.041 / 2.574 km | 0.958 / 2.406 km | 1/6 · 2/6 |

Error distributions use published positions. Coverage and error-threshold counts use every scheduled capture. In the five jointly completed pairs, adjustment improved position on two and worsened it on three in each arm. DS26-0036 error fell from 1.003 to 0.656 km at `c = 0` and 0.935 to 0.588 km with fitted `c`. Conditional Doppler RMS on that case rose from 85.47 to 87.87 Hz and from 85.49 to 87.91 Hz, respectively. Conditional RF RMS increased on four jointly completed pairs in both arms. The unchanged endpoints and RF RMS values exactly match the earlier full-IQ wide replay for all six in both calibration arms. [Scores](scores.csv) · [Exact replay parity](summary.json)

DS29-0247 reached cavity processing in the adjusted run. Systemd recorded the 165.031 s active deadline and 343.4 MiB peak memory, with no position returned on the worker pipe. The wrapper raised when its follow-up stop call also timed out. The prediction seal was reconstructed from the eleven intact per-case outputs plus the authenticated kernel deadline and empty output for this request. The unchanged wide run fixed both arms in 65.75 s. [Deadline receipt](deadline-terminal.json) · [Prediction seal](prediction-lock.json)

Across the five completed pairs, the median adjusted-minus-unchanged wall cost for the prefilter plus native preparation was +0.277 s (−5.56 to +2.69 s). Median standalone process CPU changed −0.782 s (−17.45 to +10.85 s). Median standalone wall changed −5.85 s (−20.44 to +12.16 s). Each pair used the same pinned CPU, one thread, 512 MiB and zero swap. The in-memory prefilter timer excludes intermediate JSON serialization. The partially observed DS29-0247 run remains outside these completed-pair timing comparisons. [Runtime, per-phase costs and observation counts](runtime.json) · [Source lock](source-lock.json) · [Causal history](causal-history.json)

Each chart includes distinct published and unmeasured positions and uses the original v5 endpoints at the same capture. [Six-capture chart and reserve chart](figures.json) · [Score lock](score-lock.json)

## Source preservation during formatting

The deterministic archive preserves the exact bytes of the seven Python sources bound by the measurement, audit, timeout, and scoring receipts, plus the preformat component test. Its manifest lists member hashes and the original receipt hashes. Use the source members when checking those original receipts. The archive SHA-256 is `9471c5bafb95d9a945286de771ace886d23670de803c0dede79895eb661b9dca`. [Measured source archive](measured-sources.tar.gz)

The working files were formatted with Ruff. The science ASTs match the archived sources, and the test AST matches after normalizing the order of its leading imports. Source, prediction, score, and figure evidence rehash against the original receipts. This cleanup used component checks without numerical replay.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/acquisition-support/peak-null \
  --out /tmp/peak-null-figures
.venv/bin/pytest -q tests/pipeline_eval/test_peak_null.py
```
