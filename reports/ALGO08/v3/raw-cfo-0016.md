# Fixed-epoch CFO refinement on original DS30-0016 I/Q

The refined receiver improved horizontal error in both calibration arms of DS30-0016. Error fell from **1.311 to 1.010 km** at `c = 0` and from **1.694 to 1.558 km** with fitted `c`, relative to the historical unrefined 20/12 ms receiver. Every published observation retained the same satellite assignment and conditional or predictive role. This is one original physical recording and one newly measured refinement run. [Frozen protocol](raw-cfo-0016-protocol.md) · [Full scored receipt](measurements/raw-cfo-0016.json.gz)

## Position and RF fit

| Original signed receiver | Error `c = 0` (km) | Error fitted `c` (km) | RF RMS `c = 0` (Hz) | RF RMS fitted `c` (Hz) |
|---|---:|---:|---:|---:|
| Installed named ALGO08v3 | 1.643669 | 1.661443 | 109.375 | 109.479 |
| Historical mixed 20/12 ms | 1.311046 | 1.694025 | 121.526 | 120.291 |
| Mixed 20/12 ms with fixed-epoch CFO refinement | **1.009776** | **1.557704** | 118.260 | 117.490 |

Against the unrefined mixed receiver, the gains were 301 m and 136 m for the two arms. Against named v3, the gains were 634 m and 104 m. Fitting `c` in the refined run reduced RF RMS by 0.771 Hz and increased position error by 0.548 km relative to `c = 0`. The named receiver had lower in-sample RF RMS for both arms. Horizontal errors use the fixed DS30 operator site authority. [Original comparison](raw-0016-best.md) · [DS30 reference audit](../../2026_11_21_ds30_full/reference-audit.json)

## What changed in the signed recording

| Schedule and radio | Opportunities | Named-v3 factors | Unrefined and refined factors | Changed CFO values |
|---|---:|---:|---:|---:|
| Full anchor, radio 0 | 93 | 38 | 47 | 0 |
| Full anchor, radio 1 | 93 | 20 | 27 | 0 |
| Short primary, radio 0 | 620 | 252 | 272 | 169 |
| Short primary, radio 1 | 620 | 130 | 129 | 70 |
| **Total** | **1,426** | **440** | **475** | **239** |

All three packets match the same 1,426 opportunities across 713 admitted and 808 issued visits, original timing and RF, signed inventory, raw authority, causal cutoff and 25 km operator offer. The refined and unrefined mixed packs retain the same 475 factors, integer and fractional epochs, ranks, verifier scores, margins and pass flags. All full-anchor tuples match. The frozen rule scored the original selected epoch on the full stereo window and changed 239 of 401 positive short hypotheses. It skipped 151 when the trailing frames failed support and 11 when the correction was inconsistent. The held DS30-0169 rule, library and step were fixed before this comparison. [Held DS30-0169 lane result](short-cfo-refine.md)

Among 303 short lanes already matched to a published named-v3 rank-zero factor within 2 samples modulo the pilot period and 250 Hz before refinement, signed CFO difference RMS fell from 94.587 to 68.556 Hz. Radio 0 fell from 89.419 to 62.432 Hz over 205 matches and radio 1 fell from 104.577 to 79.862 Hz over 98 matches. Of those 303 comparisons, 177 improved, 39 worsened and 87 stayed unchanged. The named CFO is an aperture measurement comparator. The position table uses the independent, fixed site authority.

The exact Graph retained 4,137 ordered edges in both mixed runs, with 13 to 14 tracks and 354 to 362 assigned graph points. Final ownership and predictive continuation matched exactly in both calibration arms, including order, with 93 conditional and 23 predictive observations per arm. All 116 final owners came from radio 0, and 96 carried a changed CFO. The named baseline had 109 owners. Relative to named v3, both mixed receivers added ten and dropped three in each arm, with the same 106 shared observation assignments. The refined run took the active installed Graph and the accepted signed finish. It produced a complete 179-point grid and position path bound to the position PNG, and all eight officially addressed PNGs were independently decoded and checked.

## Charged runtime and admission

| Process boundary (s) | Historical named v3 | Historical mixed | Refined |
|---|---:|---:|---:|
| Start to sealed detections (elapsed) | 5.881 | 6.657 | 4.995 |
| Sealed detections to terminal (elapsed) | 3.179 | 2.796 | 2.518 |
| Terminal to exit (elapsed) | 1.764 | 1.044 | 1.015 |
| **Whole process elapsed** | **10.824** | **10.497** | **8.529** |
| **Whole process CPU** | **10.816** | **9.908** | **8.314** |

The refinement itself used **0.319 CPU s / 0.326 elapsed s** inside 3.762 CPU s / 3.975 elapsed s of authenticated acquisition. The lookahead worker used 0.145 CPU s in the current run and 1.352 CPU s in the historical mixed run, despite serving the same 834.806 MB in 11 hits. The latest clock comes from a single candidate-only session with historical controls. The elapsed difference includes that session and its other costs. The paid local refinement is the isolated measured increment.

The first passive check found zero resident payload pages. The single permitted conditioning pass read 991,734,597 bytes in 3.018 s elapsed and 0.202 CPU s with 1,937,024 input blocks. The first candidate launch then exited at the installed import guard before any waveform or detector call, using 0.321 s elapsed and 0.318 CPU s. After the import ordering fix, `--help` and a nonexistent-recording probe passed their expected preflight checks. The authorized recovery used the original 242,128 resident pages before and after its sole successful raw acquisition, with zero additional conditioning bytes. The final process reported 4,344 input blocks and zero major faults. These counters include all opened files.

The optional raw entry takes the existing unified arguments plus `--cfo-refinement-library` pointing to the checked DSO from the held lane study. It keeps the original unified source, named solver and five existing DSO digests byte-identical. The receiver binds its own canonical `sha256:701c05ac380d8c1b4b528ddbfd6925d1c13dd9b1832dbe2959f52c3177065d66` recipe to the same original recording through one genuine acquisition and one authenticated handoff. Activation happens after the installed startup guard and closes the full-verifier context at the end of each pilot edge. The documented numerical run is frozen at `4fb79030c`, with actual products under `/dev/shm/leo-v3-raw-cfo-0016-result03`. All 29 scoped tests passed. [Raw entry](short_cfo_raw.py) · [Trial](raw_cfo_0016_trial.py) · [Scorer](raw_cfo_0016_score.py) · [Component tests](../../../tests/pipeline_eval/test_raw_cfo_integration.py)
