# Frozen exact named solver on dense DS30-0374

The unchanged exact named solver completed DS30-0374 in **23.630 s** through saved-input process exit, versus **28.324 s** for the same-packet installed-v3 control, a **1.199×** speedup. It preserved both calibration arms, all **2,905 ordered owner and role rows per arm**, the original terminal and objective, the full 179-point map and path, and all eight encoded and decoded PNGs. The named saved control independently matched the original release. Across three same-packet 20 ms comparisons, wall time fell from **62.681 to 50.847 s** and all three reproduced the original science and products. None reached 1.6×. [Enrollment](exact-named-dense-protocol.md) · [Dense receipt](measurements/exact-named-DS30-0374.json.gz) · [Three-case reduction](measurements/exact-named-saved-panel.json)

| Saved physical recording | Issued / admitted | Wall through exit, named → exact | CPU through exit, named → exact | Wall speedup |
|---|---:|---:|---:|---:|
| DS30-0160 | 3,691 / 2,354 | 15.999 → 10.330 s | 15.994 → 10.317 s | 1.549× |
| DS30-0316 | 3,042 / 2,702 | 18.358 → 16.887 s | 18.353 → 16.829 s | 1.087× |
| DS30-0374 | 6,770 / 4,644 | 28.324 → 23.630 s | 28.268 → 23.616 s | 1.199× |
| Sum | 13,503 / 9,700 | 62.681 → 50.847 s | 62.614 → 50.761 s | 1.233× |

The median case ratios are **1.199× wall** and **1.197× CPU**. The CPU ratio of summed times is **1.234×**. The 0160 case includes a confirmed named history recovery that avoids the original full retry. The ordinary-route cases improved 1.087× and 1.199×. Dense solve CPU declined from 24.006 to 19.517 s, with 1,056 exact grouped rank curve calls, 1,428,167 candidate rows excluded by the visibility bound, 45,190 retained ordered Graph edges, 356 checked predictive map calls, and eight reused verified PNG reads. The optional constrained gate had no active invocation. [Earlier two-case report](exact-named-route.md)

| Recording | `c = 0` horizontal error | Fitted-`c` horizontal error | `c = 0` RF RMS | Fitted-`c` RF RMS | Ordered owners per arm |
|---|---:|---:|---:|---:|---:|
| DS30-0160 | 798.498 m | 1,089.003 m | 126.335 Hz | 126.093 Hz | 1,037 |
| DS30-0316 | 1,944.726 m | 1,863.056 m | 99.232 Hz | 99.054 Hz | 1,976 |
| DS30-0374 | 1,855.441 m | 1,935.370 m | 101.536 Hz | 101.520 Hz | 2,905 |

The table values are equal between each case's control and exact worker. Three fixes and zero withholds reproduced. DS30-0374 was selected by the smallest issued count above 5,000 among DS30-0155, DS30-0374 and DS30-0402. It was previously used for original-named final fit and for experimental cold finalists. This is its first run with the exact named composition. The runner used an enrollment adapter to supply the original archive authority and logical byte count from the previously sealed request. The scientific driver remained byte-identical to `f4370e443`. Nine tests passed. [Driver](exact_named_dense.py) · [Earlier DS30-0374 study](named-final-0374.md)

The dense worker verified 132 causal reads covering 235,972,530 logical bytes from a fully resident 47-snapshot view of 84,010,745 bytes. No new archive staging or original backing catalogue or waveform reads occurred. The earlier DS30-0008 index had zero hits among 40 distinct bodies. Prior standalone index export cost 4.320 s elapsed and 4.319 s CPU, including its own source preparation. The prior 0316 failure before inference cost 1.127 s elapsed and 1.121 s CPU. These costs are outside the clean three-run sum. Charging both costs once gives **1.113×** wall improvement. The original measured DS30-0374 raw named process took 164.405 s elapsed and 63.587 s CPU, a separate boundary. This experiment does not measure acquisition speed or a raw end-to-end ratio. Each candidate ran once under the shared low-priority CPU 2 slot. The separately timed historical controls carry cache and session variation.
