# Installed ALGO08v3 timing repeatability on two physical recordings

The integrated original-file candidate has an order-sensitive **1.6×** result and reaches **2× in neither order**. Against the fresh ancillary stock pair, the positive-first candidate reached **1.605× summed / 1.825× reciprocal median**. Its sum cleared 1.6× by **22 ms**. The withholding-first candidate reached **1.573× / 1.714×**. Against all verified private-tmpfs stock timings, only **16 of 18** denominator combinations cleared 1.6× in both metrics for positive-first and **1 of 18** for withholding-first. The original comparison keeps its prespecified 10.744677 s and 1.497018 s denominator. [Integrated candidate results](integrated-original.md) · [Machine-readable ledger and reducer](measurements/raw-denominator-audit.json.gz)

## Installed process census

The census identified **nine** independent private-tmpfs stock processes and another **six** direct installed runs on page-cached backing files. All start at a fresh named child launch and stop at exit after publication. They use the same frozen installed ALGO08v3, source, recorded offer and causal catalogue digest for their recording on one low-priority Gauss CPU2 core with one numerical thread. Stock DS30-0016 reproduced 808 issued visits, 713 valid stereo visits, 440 factors, the fix, 109 owners per arm and the eight images. Stock DS30-0107 reproduced 29 issued visits, 27 valid stereo visits, zero factors and the `no_active_curvature` withhold with two null arms and zero products. The same completed child may appear in a run receipt, a later comparator and a cohort summary. Deduplication uses case and process start or, for older envelopes, the distinct immediately preceding cached-input sample and the primary process receipt. [Installed source and release checks](history-risk-0016-raw.md) · [Two-case original physical policy](history-risk-physical-cohort.md)

| Recording and source state | Elapsed s | CPU s | Input blocks / major faults | Primary timing evidence |
|---|---:|---:|---:|---|
| DS30-0107 private tmpfs | 1.273173 | 1.260751 | 4600 / 27 | [Ancillary stock-only repeat](measurements/stock-raw-repeat-0107.json.gz) |
| DS30-0107 private tmpfs | 1.388277 | 1.378079 | 784 / 0 | [Strict split study's fresh named child](measurements/strict-packed-0107.json.gz) |
| DS30-0107 private tmpfs | 1.406235 | 1.402678 | 1056 / 0 | [8 ms raw comparison](measurements/eight-ms-0107-pair.json.gz) |
| DS30-0107 private tmpfs | 1.417264 | 1.414697 | 32 / 1 | [Adaptive-withhold raw comparison](measurements/adaptive-withhold-0107.json.gz) |
| DS30-0107 private tmpfs | 1.466299 | 1.452979 | 1256 / 1 | [Continued-CFO raw comparison](measurements/continued-cfo-small-raw-0107.json.gz) |
| DS30-0107 private tmpfs | 1.497018 | 1.495600 | 0 / 0 | [Prespecified original cohort denominator](measurements/history-risk-0107-raw.json.gz) |
| DS30-0016 private tmpfs | 10.743031 | 10.718879 | 5448 / 18 | [Early pair, candidate failed but stock completed](measurements/history-risk-0016-raw-failed.json.gz) |
| DS30-0016 private tmpfs | 10.744677 | 10.742462 | 0 / 0 | [Prespecified original cohort denominator](measurements/history-risk-0016-raw.json.gz) |
| DS30-0016 private tmpfs | 10.861153 | 10.855225 | 232 / 2 | [Ancillary stock-only repeat](measurements/stock-raw-repeat-0016.json.gz) |
| DS30-0016 page-cached backing | 10.812561 | 10.809384 | 16 / 1 | [Original short-layout raw comparison](measurements/unified-short-layout.json.gz) |
| DS30-0016 page-cached backing, local catalogue | 10.824021 | 10.815568 | 0 / 0 | [Original cumulative raw comparison](measurements/raw-0016-best.json.gz) |
| DS30-0016 page-cached backing | 10.830622 | 10.796933 | 8 / 0 | [Combined weak raw comparison](measurements/weak-combined-raw.json) |
| DS30-0016 page-cached backing | 11.229058 | 11.226203 | 0 / 0 | [Matched frontier bypass comparison](measurements/combined-frontier-weak-bypass.json.gz) |
| DS30-0016 page-cached backing | 11.583266 | 11.522754 | 0 / 0 | [Matched frontier comparison](measurements/combined-frontier-weak-warm.json.gz) |
| DS30-0016 page-cached backing | 11.650622 | 11.645106 | 0 / 0 | [Original short bootstrap comparison](measurements/unified-short-bootstrap.json.gz) |
| DS30-0016 cold backing | 20.177621 | 11.131413 | 1941368 / 0 | [Installed cold frontier control](measurements/combined-frontier-weak.json.gz) |
| DS30-0016 cold backing, research stock process | 14.521100 | 11.347280 | 1941616 / 1 | [Original stock-control worker](measurements/full-short-DS30-0016-raw.json.gz) |

The 14.521100 s trial used the research driver’s stock-control worker. The 20.177621 s trial used the installed entry from an empty waveform page cache. Both are useful for interpreting I/O cost. The sensitivity below uses the warm strata. Saved signed-detection replays omit acquisition. Isolated detector timings, denial preflights, partial prefix/subset runs, and the initial named path-resolution failure omit part of the required work and contribute no sample. The other short-input controls from the original unified layout, bootstrap and frontier studies used DS30-0227. [Cold stock protocol](full-short-physical.md) · [Matched warm protocol](combined-frontier-raw-protocol.md)

Process input blocks and major faults include executable, dependency and plotting access. They do not identify waveform I/O. The strict private strand proves the original read-only tmpfs mapping, resident compressed waveform and index pages. The fresh repeat also proves both staged catalogues resident before and after each child. The six earlier backing clocks guaranteed waveform residency at launch. Their on-disk catalogue, index or dependency state could still differ. The 10.824021 s child used a staged local catalogue after an independently charged 7.266 s source-conditioning pass. The 10.812561 s pair had 45.64% global full 10 s I/O pressure at admission despite 16 stock input blocks. The 1.466299 s run followed an earlier 8.012 s stopped-clock staging pass at 50.30% full I/O pressure. The newer private runs paid no source conditioning during their child clocks. [Cumulative raw readiness](raw-0016-best.md) · [Original layout I/O context](unified-short-layout.md) · [DS30-0107 staging context](continued-cfo-small-raw.md)

## Fresh ancillary stock-only pair

The frozen order was DS30-0107 and then DS30-0016 under the same shared lease, private read-only original mappings and standard stock renderer. Both exited zero. DS30-0107 used **220892 KiB** peak child RSS and **0.0563 s** prelaunch setup. DS30-0016 used **572012 KiB** and **0.0622 s**. Host I/O `some avg10` moved from **0.48% to 0.39%** and **0.39% to 0.25%**, respectively. Raw waveform and causal archive files were already staged. The launch through exit clocks exclude separate setup and verification. [Ancillary protocol](stock-raw-repeat-protocol.md) · [DS30-0107 full score](measurements/stock-raw-repeat-0107.json.gz) · [DS30-0016 full score](measurements/stock-raw-repeat-0016.json.gz)

DS30-0107 independently reproduced the signed original terminal with zero factors, null fixed and fitted arms, and no figures, grid or path. DS30-0016 reproduced the 440-factor packet, both positions and RF residuals, 109 ordered owners per arm, scientific 179-point grid and path, and all eight encoded and decoded image hashes. The historic stored grid record includes metadata outside the scientific digest. Read-only 0016 scoring initially resolved the older installed storage API. The offline fix selected the current read-only API and normalized tuples to their archived JSON arrays. Both timed outputs stayed sealed, and no child was repeated. [Stock runner and offline verifier](stock_raw_repeat.py)

## Threshold sensitivity

For stock times `B` and fixed candidate times `C`, the summed speedup is `sum(B)/sum(C)` and the reciprocal median is `1/median(C_i/B_i)`. Two cases give the reciprocal of the mean of their two ratios. Each row holds the same measured candidate times and evaluates every possible pair of independently observed stock times in its scope. The 18 private comparisons and 54 fully cached comparisons are denominator sensitivity, with only two actual candidate orders. [Reducer and exact clocks](raw_denominator_audit.py)

| Integrated original-file order and stock scope | Summed speedup | Reciprocal median | Both ≥ 1.6× | Both ≥ 2× |
|---|---:|---:|---:|---:|
| Positive first, prespecified archived pair | 1.618847× | 1.931692× | 1/1 | 0/1 |
| Withholding first, prespecified archived pair | 1.587384× | 1.824084× | 0/1 | 0/1 |
| Positive first, fresh ancillary pair | 1.604648× | 1.824613× | 1/1 | 0/1 |
| Withholding first, fresh ancillary pair | 1.573461× | 1.714147× | 0/1 | 0/1 |
| Positive first, all private tmpfs | 1.589–1.634× | 1.813–1.945× | 16/18 | 0/18 |
| Withholding first, all private tmpfs | 1.558–1.602× | 1.704–1.836× | 1/18 | 0/18 |
| Positive first, all fully cached originals | 1.589–1.739× | 1.813–2.031× | 50/54 | 0/54 |
| Withholding first, all fully cached originals | 1.558–1.705× | 1.704–1.913× | 19/54 | 0/54 |

The private stock timings allow a **7.510128–7.723857 s** candidate sum at 1.6× and **6.008102–6.179086 s** at 2×. The fresh pair allows **7.583954 s** and **6.067163 s**, respectively. Adding the cached backing runs extends the upper budgets to **8.217275 s** and **6.573820 s**. The positive-first candidate reached 2× in reciprocal median alone in four of 54 broader warm combinations because of longer backing timings. The integrated worker timings already include the worker’s normal startup and real media checks. Charging the experiment’s additional prelaunch admission and waveform-denied probes raises the two sums to **12.164 s** and **12.415 s**, which clear neither gate in either warm stratum. [Integrated paid scopes and preparation](integrated-original.md)

The ready split format’s 7.084 s sum, including candidate-specific setup, clears both 1.6× gates across all private combinations and clears the 2× reciprocal-median gate alone in 15 of 18. The 12.388 s first-use scope clears neither gate. The authenticated frame-indexed 7.408 s child sum also clears both 1.6× gates across all private combinations, and passes 2× reciprocal median alone in seven of 18. Both scopes rely on an already prepared derivative. Every warm summed budget is shorter than the candidate’s elapsed sum at 2×. [Split first-use and ready costs](strict-cairo-0107.md) · [Indexed frame timing](visit-frame-raw-0107.md)

Run `python3 reports/ALGO08/v3/raw_denominator_audit.py` after integrating the pinned `integrated-original.json.gz`. The reducer only opens existing compressed receipts. It binds the integrated receipt SHA-256, checks identical clocks when citations alias the same process, and regenerates the source-indexed evidence. [Component tests](../../../tests/pipeline_eval/test_raw_denominator_audit.py)
