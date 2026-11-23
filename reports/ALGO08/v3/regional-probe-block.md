# Fused four-position regional proof

Streaming one orbit through four positions reduced dense DS30-0008 proof CPU by **20.4%** and scoring CPU by **44.1%** at the paired median. The southern positive veto used **5.7% more** proof CPU. That exceeds the registered 5% veto overhead allowance. Both offers retained every native score, original owner and terminal decision exactly. [Frozen proof and receipts](measurements/regional-probe-block-four-lanes.json.gz) · [Protocol](regional-probe-block-protocol.md)

| Saved proof | Full CPU, stock → block | Scoring CPU, stock → block | Consumed / computed positions, block | Terminal |
|---|---:|---:|---:|---|
| Measured DS30-0008, containing | 2.881 → 2.329 s | 1.324 → 0.742 s | 25 / 28 | Inside witness, inference remains eligible |
| Southern simulation, 52.5 km omission | 0.342 → 0.361 s | 0.171 → 0.190 s | 96 / 96 | Positive bilateral veto |

The table shows five repeats per method. Dense proof CPU ranged from 2.805 to 3.877 s in stock and from 2.291 to 2.653 s in the block. The southern ranges were 0.324–0.358 and 0.361–0.364 s. Paired wall ratios were 0.796 and 1.057. Each run used one low-priority pinned Gauss core and one numerical thread. The proof clock includes fresh regional orbit geometry and the original terminal reducer. The scoring clock also includes packing and computing observers. The experiment ends at the proof and neither fits nor publishes a position.

The native kernel traverses the regional orbit bank once for each four-position call. It projects one orbit into time-by-position scratch arrays and updates each track's mixture before moving to the next orbit. Each track retains its own observation order and visits orbits in the original order. Strict comparisons preserve the first owner on ties. The compiler vectorized the four-position projection. Dense used seven calls and 298 KiB of native scratch. It computed 9,654,876 orbit-time cells across the three positions beyond the 25th-point stop, all within the measured clock. The scalar projector alone used 0.561 s median on dense and 0.086 s on the southern case. The southern run had only 26 tracks and never stopped early. Its stock scoring interval was already about 0.17 s, and the block did not recover its additional scoring cost on that packet. [Native kernel](regional_probe_block.c) · [Proof runner](regional_probe_block_trial.py) · [Hermetic tests](../../../tests/pipeline_eval/test_regional_probe_block.py)

## Guard the blocks at the first possible decision

The original reducer always requests the eligible far-exterior probes before checking the first score-based stop. The guarded schedule batches only those 24 probes and evaluates later points through the original native scalar path. Both cases finished with **zero speculative probes**. The dense request used six blocks and one scalar call. The positive veto used six blocks and 72 scalar calls. Every visited row, owner and terminal record matched the scalar control exactly. [Guarded proof seal and receipts](measurements/regional-probe-block-guarded.json.gz)

| Saved proof | Full CPU, stock → guarded | Scoring CPU, stock → guarded | Median paired CPU ratio, full / scoring |
|---|---:|---:|---:|
| Measured DS30-0008, containing | 2.932 → 2.167 s | 1.416 → 0.684 s | 0.739 / 0.483 |
| Southern simulation, 52.5 km omission | 0.343 → 0.349 s | 0.173 → 0.176 s | 1.017 / 1.022 |

Each side has three repeats. Dense full CPU ranged from 2.799 to 3.355 s in stock and 2.132 to 2.254 s in the guarded run. Southern full CPU ranged from 0.342 to 0.360 s in stock and 0.347 to 0.357 s in the guarded run. Paired wall ratios were 0.739 and 1.017. The guarded dense reduction passed the 10% CPU gate. The positive veto's 1.7% paired median increase was within the 5% allowance. Eight new regression tests and 67 relevant existing tests passed together. The reusable binding falls back to the prepared scalar scorer for unsupported layouts and retains original preparation errors. [Guarded scheduler](regional_probe_block.py) · [Reusable binding](regional_probe_block_binding.py) · [Component tests](../../../tests/pipeline_eval/test_regional_probe_block.py)

## Complete saved publication

Both complete publications returned identical fixed-zero and fitted endpoints, 4,367 observation owners and roles per arm, the 179-point numerical grid, position path, and all eight encoded and independently decoded PNGs. The guarded publication evaluated 24 probes through six blocks and one through the original scalar path without fallback. The original stock attempt timed out after 100 s during publication. It had already written a terminal that matched the completed stock retry byte for byte. The retry used the same input and one-core settings with a 150 s deadline. The first complete candidate and the completed stock retry were sealed before geographic scoring. [Prediction and recovery seals, scores and full grid](measurements/regional-probe-block-publication.json.gz)

| Saved DS30-0008 boundary | Stock completion | Guarded |
|---|---:|---:|
| Process CPU | 28.806 s | 29.367 s |
| Process wall to exit | 81.326 s | 97.817 s |
| Numerical solve CPU | 24.237 s | 24.781 s |
| Regional proof CPU | 2.981 s | 3.370 s |

The separate complete launches did not reproduce the proof-stage speedup. The integrated proof clock includes preparation and scoring together, and host contention varied between launches. The original timeout and retry make the complete wall measurements unsuitable for estimating a paired gain. Two earlier setup attempts reached no proof. One treated the recording directory as a file, then the release needed the standard service account to open its inventory. Input windows were not read. [Complete publication runner](regional_probe_block_publication.py) · [Bounded stock retry](regional_probe_block_retry.py)

The fixed-zero and fitted geographic errors were **0.919 km** and **0.857 km** in both builds. Conditional Doppler RMS was **140.961 Hz** and **140.950 Hz**, respectively. These results cover the complete saved DS30-0008 position and publication. The southern case was a simulated regional veto.

## Reproduce the guarded proof

Under the Gauss lock, pin CPU 2 at nice 15 with best-effort I/O priority 7 and one numerical thread. Build the stock track library with the [original flags](regional-track-scores.md). Build the block with `cc -std=c11 -O3 -march=haswell -ffp-contract=off -fno-math-errno -fopenmp-simd -fPIC -shared regional_probe_block.c -lm -o block.so`. Use a new local output directory and the frozen release interpreter and payload. Run `regional_probe_block_trial.py` with `freeze`, `dense` and `south-far`, passing `OUTPUT STOCK_LIBRARY BLOCK_LIBRARY --guarded` to each. The complete publication runner accepts `run OUTPUT PROOF_OUTPUT STOCK_LIBRARY BLOCK_LIBRARY` and uses the service account for the installed recording inventory. Run its `score OUTPUT RECEIPT` command in the repository scoring environment after the terminal seal exists.
