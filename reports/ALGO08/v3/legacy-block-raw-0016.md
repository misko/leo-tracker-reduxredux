# Original DS30-0016 with optional legacy block maps

The mixed reader completed the entire original DS30-0016 recording in **7.581 s elapsed and 7.574 s CPU**, versus **8.630 s elapsed and 8.611 s CPU** for the ordinary reader with identical scientific and publication settings. It used detached maps for five members and the ordinary authenticated full reader for eight. Both runs retained the signed original recording, all 808 issued visits and all 713 admitted visits. The two runs published the same detections, terminal, calibration endpoints, RF RMS, ordered owners, grid, path and eight PNGs. [Frozen protocol](legacy-block-raw-0016-protocol.md) · [Machine receipt](measurements/legacy-block-raw-0016.json.gz)

| Scope | Ordinary wall / CPU (s) | Mixed map wall / CPU (s) |
| --- | ---: | ---: |
| Authenticated acquisition | 3.612482 / 3.612193 | 2.877753 / 2.877666 |
| Held selection | 0.049618 / 0.049617 | 0.050160 / 0.050158 |
| Decision and publication | 4.388068 / 4.370325 | 4.128447 / 4.122277 |
| **Through exit** | **8.629779 / 8.611184** | **7.580689 / 7.574294** |
| Process input blocks and major faults | 1,816 / 19 | 392 / 0 |

The observed elapsed difference was **1.049 s**, including **0.735 s** inside acquisition and **0.260 s** in decision and publication. Both children submitted and consumed 11 bounded prefetch buffers covering 834,805,982 bytes. Prefetch worker CPU was 0.560 s on the ordinary arm and 0.169 s on the mixed arm. The ordered runs occupied separate lock turns after a mixed-arm startup failure. Waveform files remained resident on the same read-only bind across each child. The process-wide I/O and CPU differences outside the reader make the end-to-end gap unsuitable as an isolated estimate of decoder savings. The historical installed v3 reference took **10.745 s wall and 10.742 s CPU** on this original recording with its own receiver, solver and publication settings. [Exact child clocks and cache evidence](measurements/legacy-block-raw-0016.json.gz) · [Historical installed reference](history-risk-0016-cairo.md)

## Full custody and exact products

The preparer censused all 13 authenticated compressed snapshots during one ordinary full readback. It sealed each eligible map only after the installed reader verified the entire encoded and decoded member, including all 808 ordered per-visit hashes. All 242,675 original waveform, manifest and index pages, 20,102 causal snapshot pages and 658 portable input pages were resident. The original session `fast-e22b918df63370a0590757b70f71a0e6`, inventory `sha256:e22b918df63370a0590757b70f71a0e620792cf90cf78a833e601af7a0b395a6` and raw authority `sha256:64e945e9717c2612fdb3118d7b65c713076a1b56f5de49f8fdf291a3220fc252` were reused by both original-reader paths. Preparation created only detached metadata and a decoder binary in tmpfs. [Original member pins and map custody](measurements/legacy-block-raw-0016-custody.json)

The mixed child authenticated all **991,734,597 original compressed bytes**. The five mapped members covered **320 visits and 393,072,334 bytes**. They delivered 34 full visits and 250 prefixes, totaling **214,400,000 checked bytes**. Their native decoder processed 246,284,288 bytes in requested blocks and 7,995,392 in the preceding table-origin blocks it needed. The other eight members covered 488 visits and the ordinary path verified all **780,800,000 decoded bytes**. Excluded visits retained their signed original row and compressed-member binding. Mixed and ordinary shared the same native aperture schedule, causal cutoffs and the validated earlier portable index with 19 overlapping bodies used by history-risk. [Mixed member accounting and portable proof](measurements/legacy-block-raw-0016.json.gz)

Both detection files had SHA-256 `aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac`, including the signed, ordered probes and original exclusion records. The two results preserved 115 ordered owners per calibration arm, the complete 179-point grid, path and independently verified position-image bindings. All eight PNGs matched in encoded bytes, RGBA digest and dimensions. The renderer in both runs drew the four original orbit sheets, two Cairo residual sheets, track-RMS and position, with title `fast8-auto-20261113-112146-b04f5461-1-lower`. [Exact products and renderer evidence](measurements/legacy-block-raw-0016.json.gz)

| Calibration | Latitude | Longitude | RF RMS (Hz) |
| --- | ---: | ---: | ---: |
| Fixed zero | 37.845989267 | −122.489763136 | 134.021487 |
| Fitted | 37.847645952 | −122.496772434 | 133.739967 |

## Preparation and first use

| Charge | Wall (s) | CPU (s) |
| --- | ---: | ---: |
| Full authenticated map preparation including compilation | 1.718373 | 1.718283 |
| Member-validation pass, included above | 1.675874 | 1.675782 |
| Incremental census, prefix pins, seal, sync and decoder compilation within preparation | 0.090876 | 0.090812 |
| Mixed through exit plus full map preparation | 9.299062 | 9.292577 |
| Mixed through exit plus incremental map work when full validation is already scheduled | 7.671565 | 7.665106 |
| Mixed through exit, full map preparation and archived earlier portable build | 13.619422 | 13.611424 |

The five map files used 171,601 bytes. Detached custody used 6,933 bytes and the decoder binary 15,992 bytes. The incremental clock isolates instrumented work during the full read, conditional on an independently required validation pass. The first-use totals charge the actual augmented validation pass or its conditional incremental cost as shown. The earlier portable producer is reused, and its 4.320 s elapsed is shown separately. These totals exclude the outer orchestration outside the raw child, including 21.219 ms of shared admission and 7.691 ms of trial readiness checks. Candidate-specific map setup took 193.625 ms inside the measured child. [Preparation receipts](measurements/legacy-block-raw-0016.json.gz)

## Execution and recovery

The frozen initial runner stopped at module or argument bootstrap before any prior attempt opened waveform bytes. The corrected controller at `a78562085` prepared the maps once and completed the ordinary child. The indexed child in that slot stopped at the installed lazy-startup guard before opening waveform bytes. The indexed-only recovery at `14a9a20e3` deferred map setup until after that guard. It reused the prepared tables and the same argv in a new low-priority lock turn. The original ordinary child and first indexed startup evidence were sealed before the recovery. The offline reviewer used source-stage residency and the verified mount boundary to qualify the inputs while retaining the process-wide charged-block and fault counters. The terminal science and artifacts were read independently using current checkout read-only verification. [Measured settings, failed bootstrap and immutable completed pair](measurements/legacy-block-raw-0016.json.gz)

The unpacked result SHA-256 is `7e5f44b388a0674ab276282478122d218ef39adf9985acb31ef3e5a4d3b6afa0` and the measured seal SHA-256 is `45cb0fb701c9070c43b97f964940a878cc4f5d6f270823b09b11444e29f75416`. The retained ordinary comparator and exact common scientific source pins are in `/dev/shm/leo-v3-legacy-block-raw-0016-result02`. Eleven focused component tests passed. The experiment uses only the complete staged DS30-0016 recording and its containing offer. [Reusable mixed reader](legacy_block_input.py) · [Raw entry](legacy_block_raw_entry.py) · [Verification](legacy_block_raw_score.py)
