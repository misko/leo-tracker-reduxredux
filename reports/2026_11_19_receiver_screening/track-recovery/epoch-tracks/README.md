# Causal timing and folded-CFO tracks through position

The forward linker reduced track-stage CPU by 64–68% on the two fresh Graph pairs. It preserved the accepted native winners and lost much of their long, curved track support. The unchanged phase-release solver returned both arms on three of four recordings, with larger location errors than Graph in all three. It failed in cavity nomination on DS29-0082. Graph returned both arms on every case. [Exact scores](scores.csv) · [Both-arm position figures](plots/index.html)

## Same-factor position and frequency

Every pair uses the same authenticated four-start wide GLRT factor bytes, causal archive and track configuration. Fresh Graph controls on DS26-0036 and DS29-0082 reproduce their archived coordinates and conditional RMS exactly. The two prespecified full-stride confirmations use sealed Graph controls of the same input, with no fresh matched Graph time comparison claimed there. The six fresh services were single-threaded, pinned to CPU4 or CPU5, and enforced 512 MiB, zero swap and a 210 s unit deadline. [Frozen inputs and software](plan.json) · [Terminal receipts](results.jsonl.gz)

| Recording | Graph error, zero / fitted (km) | Epoch-track error, zero / fitted (km) | Graph conditional RMS, zero / fitted (Hz) | Epoch-track conditional RMS, zero / fitted (Hz) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 1.003 / 0.935 | 4.568 / 4.415 | 85.469 / 85.487 | 84.405 / 85.010 |
| DS29-0082 | 2.489 / 2.346 | Failed / failed | 84.421 / 84.248 | — |
| DS26-0162 | 0.682 / 0.670 | 3.483 / 3.470 | 57.595 / 57.596 | 46.017 / 46.023 |
| DS29-0519 | 0.334 / 0.324 | 1.667 / 0.941 | 90.230 / 90.341 | 83.055 / 82.336 |

The epoch linker met the 10% same-factor Graph error limit on 0/4 in each arm. Its conditional RMS fell on the three cases that returned, while geographic error rose. DS29-0082 reached cavity nomination after building 45 tracks with two curved tracks. The original solver raised `nonempty observation mask matching full design required`, so the measured result carries a failed status and empty endpoints for both arms. The unit stopped at 14.912 s with a cgroup peak of 280,268,800 bytes, eliminating timeout and memory exhaustion as explanations for this measured failure. [Failure and resource receipt](results.jsonl.gz)

## Track support and cost

The linker preserves Graph's original maximum-margin gated winner for each probe. It considers only current and prior measurements in the same RF lane. It removes nominal counter phase before estimating the past epoch slope, compares the next wrapped phase and folded CFO, and keeps at most 12 active chains. Each chain goes separately through the original polynomial validator and support limits. The validator can remove unsupported chain members. [Prospective rule](PROTOCOL.md)

| Recording | Accepted winners, both | Owned points, Graph → epoch | Tracks, Graph → epoch | Curved tracks, Graph → epoch | Track CPU, Graph → epoch (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 3,656 | 3,140 → 2,025 | 103 → 119 | 57 → 7 | 1.878 → 0.604 |
| DS29-0082 | 2,063 | 1,789 → 705 | 71 → 45 | 29 → 2 | 0.713 → 0.259 |
| DS26-0162 | 5,518 | — → 2,970 | 165 → 174 | — → 7 | — → 0.763 |
| DS29-0519 | 4,768 | — → 2,423 | 141 → 154 | — → 7 | — → 0.698 |

On DS26-0036, 1,888 observation IDs belonged to tracks in both builds, 1,252 only in Graph and 137 only in epoch tracks. Median span fell from 25.89 to 10.64 s. On DS29-0082, all 705 epoch-owned IDs occur in Graph, which also retained 1,084 more. Median span fell from 16.30 to 9.93 s. Among shared members in each epoch track, its dominant Graph counterpart covered a mean 98.0% on DS26-0036 and 100% on DS29-0082. These are agreement measurements. Real satellite and true membership labels are unavailable. The planted fixture recovered both interleaved sources with the same folded CFO and rejected a phase jump with a compatible CFO. [Exact membership comparison](summary.json) · [All six track traces](results.jsonl.gz)

The earlier sparse method uses offline second-order path packing with CFO only and a different joint position backend. It retained more observations than its matched Graph and also changed position accuracy. The earlier causal track scout predicts possible acquisition starts from prior winners. It returned hints on 36.2% of valid probes across its eight recordings and stopped before forming complete position tracks. The current trial tests joint epoch and CFO as an end-to-end ownership rule through the unchanged phase-release solver. The observed loss of long arcs explains why accurate local timing continuation can still provide too little complete support. [Sparse path packing](../../factors/simple-tracks/README.md) · [Causal scout outcomes](../../receiver-core/causal-track-scout/README.md)
