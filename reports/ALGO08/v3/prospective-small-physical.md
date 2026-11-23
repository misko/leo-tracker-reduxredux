# Prospective physical validation stopped at input admission

The original 400–3,000 visit selection returned **zero previously untested fixes**. The one separately authorized amendment, **DS30-0316** at 3,042 visits, also could not run. Its original compressed payload and indexes had zero resident file pages and Gauss was above the frozen co-tenant I/O pressure limit. Neither arm launched, and no alternate recording was used. [Frozen protocol at `6053e48b5`](prospective-small-physical-protocol.md) · [Admission receipt](measurements/prospective-small-physical-admission.json)

## Original selection

The original panel and final signed decision both enumerate 100 cases. The named ALGO08v3 column had 92 completed fixes. Each of those 92 pair receipts matched the final decision's SHA-256, named release specification, completed decision and issued visit count. The only completed fix in the original range was **DS30-0057**, with 2,717 issued visits and a prior cumulative raw trial. DS30-0316 was the next complete case in issued-visit order, 42 beyond the original ceiling. DS30-0016 is outside the original 100-case roster. DS30-0227 is an 18-visit withhold. The original range was kept in the receipt with an empty assignment. [Signed roster selection receipt](measurements/prospective-small-physical-selection.json) · [Prior physical measurements](unified-short-layout.md)

## One amended case

The read-only inventory matched the six ordered manifest digests in the original signed pair and the independent case binding. Its 48 complete compressed members contain **3,743,823,589** compressed bytes and **4,865,567,824** decoded bytes. The corresponding indexes contain **8,239,767** bytes. The signed receipt records the original inventory, raw authority, offered region, archive, causal cutoff and historical 2,702 admitted visits. Its admission state comes from a passive `mincore` observation under the shared Gauss lock, CPU 2, nice 15 and best-effort I/O priority 7.

| Required admission check | Observed |
|---|---:|
| Compressed file pages resident | 0 of 914,043 |
| Index file pages resident | 0 of 2,044 |
| Authenticated members available for observation | 48 of 48 |
| Host full I/O pressure, 10 s average, before and after | 33.89% and 33.89% |
| Maximum allowed full I/O pressure | 10.00% |

The observer opened the original file descriptors and counted pages without reading waveform payloads. There was no read-ahead advice, warming, copying or eviction. Current paired elapsed time, CPU, position error, RF fit, numerical solve cost and PNGs remain unmeasured. The existing observations on DS30-0316 do not supply this new raw pair or a transfer test for its dense-proportional solver prediction. [Earlier solver transfer diagnostic](solver-transfer-budget.md)

## Reproduction

The metadata-only driver takes `selection` to reproduce the signed roster rule and `observe` for the sole amended case. Run `observe` under the shared low-priority Gauss slot using the original archive-readable account and release Python. An observation would describe the current page state, so it need not reproduce the historical counts. Three component tests passed. [Driver](prospective_small_physical.py) · [Tests](../../../tests/pipeline_eval/test_prospective_small_physical.py)
