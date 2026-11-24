# Reverse-order North strict packed acquisition

The merged strict packed 20/8 entry completed the original North simulation in **10.544 s** after the fresh installed ALGO08v3 control took **18.757 s**. The **1.779×** paired speedup reproduces the 1.6× result against a fresh control in the other launch order. Against the fixed **16.133 s** archived named clock, this run gives **1.530×**, below 1.6×. Both orders ran the same originally signed simulated recording and containing offer. [First pair](north-strict-read.md) · [Reverse-order receipt](measurements/north-strict-reverse.json.gz)

| Launch order | Strict packed CPU / elapsed | Fresh named CPU / elapsed | Prebuilt vs fresh | Prebuilt vs archived | First use incl. conversion | First use vs fresh / archived |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strict, then named | 9.801 / 9.811 s | 17.248 / 17.255 s | 1.759× | 1.644× | 18.069 s | 0.955× / 0.893× |
| Named, then strict | 10.393 / 10.544 s | 18.667 / 18.757 s | 1.779× | 1.530× | 18.802 s | 0.998× / 0.858× |

The fresh 1.6× margins were 0.974 s and 1.179 s in run order. On the fixed archived denominator, the first run cleared by 0.272 s and the second missed by 0.461 s. For 2×, the strict route would have needed to save an additional 1.183 s and 1.166 s against the respective fresh clocks, or 1.744 s and 2.478 s against the archive. The earlier conditional zero-reader-cost estimate was 8.146 s with the original native and nonacquisition costs held fixed. Legacy first-use estimates each include the same previously measured one-time 8.258 s for conversion and independent full decoded verification. The reverse experiment reused the derivative and paid no conversion again.

Relative to the first pair, strict elapsed rose 0.733 s and named rose 1.502 s. Strict acquisition rose from 3.886 to 4.041 s and publication from 5.363 to 5.916 s. The reverse run recorded 28,040 process input blocks and 63 major faults for strict and 16,192 blocks and 94 major faults for named. The corresponding first-pair counts were 1,976 blocks and 12 faults for strict and zero for named. Waveform inputs were fully resident tmpfs before and after both launches. The counters are process-wide and the elapsed clocks include them. The merged source and process conditions changed alongside order, which limits attribution. These are two repeats of one cached simulation and leave transfer to physical recordings unmeasured.

## Scientific and input evidence

Both strict runs reproduced the signed detector, history route, complete geographic decision, both fit endpoints and 342 ordered owners per arm. The adaptive maps replayed all 78 sampled nodes and kept every minimum, low-loss point and failed point from the original 137-point comparison. All eight PNGs agreed in encoded bytes and decoded pixels. Both installed controls independently reproduced the originally published detector, opportunities, terminal, 137-point grid, 302 owners per arm and all eight PNGs.

| Evidence unchanged across repetitions | Named fixed c = 0 | Named fitted c | Strict fixed c = 0 | Strict fitted c |
| --- | ---: | ---: | ---: | ---: |
| Horizontal error | 105.690 m | 140.779 m | 111.954 m | 128.086 m |
| Terminal conditional RF RMS | 5.406 Hz | 5.167 Hz | 9.133 Hz | 8.921 Hz |
| All-owned figure RF RMS | 9.697 Hz | 18.570 Hz | 44.983 Hz | 50.415 Hz |

The reverse trial used the untouched merged implementation at `06faca9f663acbf752aa41a0675378bbe48ced9c`. Before launch the driver verified the externally sealed map, codec, all 19 member roots and the original manifest and index digests. At every boundary, all 385,609 original payload pages and 188 original index pages were resident, as were all 387,566 derivative pages. Inside the strict clock the ordinary CLI authenticated the full 1,585,924,800 derivative bytes in 2,400 encoded blocks and decoded 913,920,000 bytes for 304 actual full-anchor calls and 2,096 actual short calls. Strict resolved zero original waveform windows and used every mapped member. Both children ran pinned to CPU 2 at nice 15 and I/O priority 7 with one numerical thread under the shared lock. All 29 focused tests passed. [Reuse and launch driver](north_strict_reverse.py)
