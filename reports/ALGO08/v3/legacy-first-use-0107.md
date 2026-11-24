# Original-file first-use map publication on the DS30-0107 withholding

One first-use child withheld and published the exact independently verified replay map in **0.595 s wall / 0.590 CPU s**. This closes the original-file first-use completion check on a genuine withholding after the earlier DS30-0016 fix. The sole runtime change lets a durable withheld terminal publish maps after the exact session, visit count and verified raw authority match. The released map decoder, receiver, decision and publication options stayed pinned. [Frozen protocol](legacy-first-use-0107-protocol.md) · [Machine receipt](measurements/legacy-first-use-0107.json.gz)

| DS30-0107 boundary | Wall, s | CPU, s |
| --- | ---: | ---: |
| Historical installed ALGO08v3 raw | 1.497 | 1.496 |
| Earlier ordinary original-file 20/8 ms raw | 0.549 | 0.547 |
| Earlier ready all-member map with lightweight audit writer | 0.536 | 0.532 |
| Fresh first-use acquisition, decision and replay-map publication through exit | 0.595 | 0.590 |
| Fresh first use with measured common preflight charged | 1.719 | 1.688 |

The fused process was 46 ms slower than the ordinary historical 20/8 ms child and 59 ms slower than the available ready-map path. The paired clocks are separate process observations. The common preflight took 1.124 s, and the separate no-waveform setup probe took 0.462 s wall. The probe establishes startup admissibility and is outside the operational first-use clock. Both native libraries came from the prior qualified positive run. The portable artifact was already resident and no new index build was charged. [Ready map comparison](lightweight-audit-0107.md) · [Earlier positive first-use result](legacy-first-use-0016.md)

The one raw traversal authenticated **33,519,983 encoded bytes** and all **44,294,856 decoded bytes**. It preserved all 29 signed visits, including the partial 136,857-sample visit and the zero-sample visit. Both remained excluded from the detector as in the ordinary control. The signed packet and terminal kept 27 admitted visits, 54 ordered opportunities and 19 factors. The emitted map reopened against the already authenticated encoded snapshot and verified its 640,000-byte sample prefix. Both output files matched the trusted **14,872-byte literal map** and **881-byte custody document** byte for byte. The child only received the prior custody commitment. It regenerated the map contents without reading the prepared map or repeating an original payload read. Publishing the two new map files took 0.378 ms wall. The child exited zero with zero input blocks or major faults. No waveform backing storage was used.

Both ordinary and ready endpoints reproduced the exact signed native file, scan report, graph proof and withheld terminal. Each calibration arm had a null position and no RF fit under `no_active_curvature`, with no figure, fit path or grid. The positive DS30-0016 first-use child finished in 8.038 s with a fix and all figures. Across those two observed outcomes the first-use children sum to **8.632 s** against **12.242 s** for historical installed v3, or **1.746× median paired and 1.418× summed** before separate admission. The summed measure misses 1.6×. The positive and withheld workers used the same numerical path and preparation algorithm with the generic terminal guard correction for the withholding case.

The source froze at `7a3780d6e` on base `14d810878`. Eleven tests passed, including exact partial and empty synthetic visits through the real fused decoder, byte-identical independently sealed map replay, both ordinary terminal outcomes and corruption rejection. One full raw child ran. The unpacked machine receipt SHA-256 is `ad6447bd88e41222e3ad25b1827631c68ff64ef7d38de10c7065ba1288526f6b`. [Driver and scorer](legacy_first_map_0107.py)
