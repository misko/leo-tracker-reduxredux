# Native detector readout on attested DS30 visits

The installed 20 ms callback reproduced every archived selected row and exclusion in both authenticated prefixes. The prefixes contain **29 original visits on DS30-0163** and **15 on DS30-0419**. The original named continuation emitted no factors this early in either recording. The current 20/8 ms callback emitted **14 and 10 factors** before its end-of-recording held selector. Their preselection native factor lists matched exactly on every shared 20 ms anchor. [Frozen protocol](attested-visit-detector-protocol.md)

## Original custody and scope

Both independent decoders in the producer's attestation reached the same truncated Zstandard state. The worker independently authenticated the held original inventory and detector document, original first manifest and signed index bytes, and the detached stereo samples against every index row. It kept the original retune events, hardware counters, acquisition target, delivery clocks and bracket. A complete input visit has precisely the declared original stereo extent and exact original I/Q hash. The next incomplete visit entered neither detector. The whole encoded and decoded original member digests and frame checksum are unavailable from the truncated data. The result retains the held full original authority as a reference and supplies separate scope and derivative digests for every replay.

| Case | Preserved encoded prefix / signed full member, bytes | Verified stereo bytes | Issued / admitted visits | Exclusions | Original hardware span |
| --- | ---: | ---: | ---: | --- | ---: |
| DS30-0163 | 35,651,584 / 78,720,466 | 46,400,000 | 29 / 26 | 0, 22, 26 | 1.2591446 s |
| DS30-0419 | 18,874,368 / 79,163,761 | 24,000,000 | 15 / 9 | 4, 5, 6, 9, 12, 14 | 0.6406300 s |

The clock anchor on excluded visit 0 of DS30-0163 initializes the scope before the validity gate. The mixed schedule counts only admitted visits per edge, channel and actual RF, as the ordinary callback does. Both native contexts start at the original initial visit. Lanes and per-window metadata remain in original order, with no added or skipped visits before EOF of the verified prefix.

## Paid visit callbacks

| Case | Two-scan anchor / short lanes | Named 20 ms stereo callbacks CPU / elapsed, ms | Current 20/8 ms stereo callbacks CPU / elapsed, ms | Native kernel CPU named / mixed, ms |
| --- | ---: | ---: | ---: | ---: |
| DS30-0163 | 16 / 36 | 103.525 / 103.528 | 63.181 / 63.182 | 102.421 / 62.274 |
| DS30-0419 | 12 / 6 | 54.370 / 54.371 | 37.955 / 37.957 | 53.848 / 37.553 |

Each stopwatch encloses an actual full stereo visit callback or its native kernel, with a lightweight observer of its factor decisions. Which arm ran first alternated by original issued visit index. Context initialization, file verification and the archive check sit outside the callback clocks. The reductions are **40.34 ms** and **16.41 ms** over these sets of visits. These paid values cover neither complete intake nor a whole-member detector seal. No original payload read, stage completion, RF, held selection or solver ran.

## What changed before history selection

Both archived named prefixes have empty selections on all **52** and **18** admitted radio opportunities. Exact row equality verifies their radio, RF, channel, absolute counter and opportunity metadata and all empty selections. All original continuation votes are zero in the replayed interval. The true raw named candidate lists include **23** factors on DS30-0163 and **18** on DS30-0419 before continuation. The archive has no emitted signed factor or alias for those rows, so it cannot independently verify the unselected raw values. The experimental ledgers retain them with their native ranks and timing for inspection.

The actual mixed anchor has the same raw native factor list on all **28** shared full-aperture lanes. It emits one factor on 4 of the 16 DS30-0163 anchor lanes and 6 of the 12 DS30-0419 anchor lanes, reflecting its maximum verified margin rule before held-history selection. Its 8 ms nonanchors show the following raw support.

| Case | Short lanes | Both positive | Named raw only | Mixed raw only | Both empty |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0163 | 36 | 7 | 2 | 3 | 24 |
| DS30-0419 | 6 | 4 | 2 | 0 | 0 |

On the seven dual-positive short lanes in DS30-0163, the nearest original raw candidate in signed CFO has absolute CFO difference **26.36–219.95 Hz** and wrapped timing difference **0.26–1.05 samples**. The four corresponding DS30-0419 ranges are **60.59–258.43 Hz** and **0.13–0.82 samples**. These pairs use the closest unaliased numerical CFO in the same lane and happen to use original rank zero. They do not supply a selected original factor, satellite identity or localization comparison.

## Portable evidence

- DS30-0163 ledger SHA-256 `266a6df0b7cc36a324fd7cf0fa325f3c9059d5ca0faf4811d8dde031238f6b88`. [Compressed typed ledger](measurements/attested-visit-detector-DS30-0163.json.gz)
- DS30-0419 ledger SHA-256 `c1ee85e09d71cb5e42a0508e90eaf06c43e9ba3f99c0097369e5ef30b5b2e8a7`. [Compressed typed ledger](measurements/attested-visit-detector-DS30-0419.json.gz)

The ledgers are detached research evidence, with absolute original identities and separate pre- and post-continuation records. They contain no waveform bytes or full acquisition packet. The launcher at as-run commit `b7ea07b77` requires each external producer attestation digest. Both completed once under the shared Gauss lock on CPU2, nice 15, I/O priority 7 and one numerical thread. Seven component tests passed. [Runner](attested_visit_detector.py) · [Tests](../../../tests/pipeline_eval/test_attested_visit_detector.py)
