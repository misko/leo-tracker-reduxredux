# DS30-0016 validation of the 20/8 ms adaptive saved route

The frozen adaptive route completed the entire authenticated saved DS30-0016 publication in **4.370 s elapsed / 4.365 CPU s**. The identical-source fixed-map control took **4.166 / 4.136 s**. The adaptive grid itself saved **17 ms**, while the complete saved process took **0.204 s longer** in this comparison. Combining the fresh saved clock with the earlier separately measured acquisition gives **7.511 s**, or **1.441×** versus the archived **10.824 s** deployed ALGO08v3 run. It misses the 1.6× allowance by **0.746 s**. This is a separate-clock estimate. [Protocol](weak-all8-adaptive-protocol.md) · [Sealed receipt](measurements/weak-all8-adaptive.json)

## Complete signed weak input and held decision

One fresh worker read the original authenticated 20/8 ms acquisition output, replayed the original held-history selector on its complete chronology, and passed the newly verified signed packet once through normal inference and publication. The signed opportunity ledger covered **808 issued, 713 admitted and 95 excluded visits**, producing 1,426 radio lanes. The original acquisition had 186 full 20 ms anchor lanes and 1,240 short 8 ms lanes. The candidate made zero fixed-epoch CFO tail calls. The archived continuation mask identifies 249 eligible short tails across 212 stereo visits. None were taken or filled with a longer-aperture CFO. [Original acquisition](eight-ms-physical.md) · [Identical-source full-layout control](weak-all8-combined.md)

The history gate requires strictly positive gains on both radios. Ties, disagreement or sparse support use the unfiltered route. History minus unfiltered held scores were **−25.287 and −11.749 nats**, reproducing the original unfiltered decision and all **506 signed factors**. The installed no-active-curve proof did not fire. Its graph point floor is eight and its named curvature span threshold is 20 s. The longest lane span was 35.435 s. The exact regional test reproduced the original 24 probes, 12 tracks and 301 graph points, stopping at `eligible_exterior_separation`. The unchanged named survivor accepted both calibrations. The final exterior refresh had no bound arm to evaluate. The measured fixture is a containing positive. No new withheld or omitted-offer result enters its accuracy or timing figures. [Independent archived physical withhold](eight-ms-0107-pair.md)

## Comparison with deployed ALGO08v3

The named comparator used the same original recording authority, native lane opportunities, causal cutoff and supplied region. It used its original full-aperture receiver. Both paths published a complete fix. The adaptive map preserves the complete fixed-layout 20/8 ms fit exactly.

| Endpoint or observation measure | Deployed v3 | Frozen 20/8 ms, fixed and adaptive maps |
|---|---:|---:|
| `c = 0` horizontal error | 1,643.669 m | 490.071 m |
| Fitted `c` horizontal error | 1,661.443 m | 980.010 m |
| `c = 0` conditional RF RMS | 109.375 Hz | 134.021 Hz |
| Fitted `c` conditional RF RMS | 109.479 Hz | 133.740 Hz |
| Published owners per arm | 109 | 115 |
| Selected native factors | 440 | 506 |

The larger calibration-arm error on this recording is 980.010 m for 20/8 ms and 1,661.443 m for v3. Fitted `c` lowers 20/8 ms RF RMS by 0.282 Hz while increasing horizontal error by 489.939 m compared with the fixed-zero arm. The retained 20/8 ms owner roster has 92 conditional and 23 predictive observations per arm. The renderer inherits the `ALGO08v2` presentation label and its whole-roster residual summary. The table reports the conditional RF RMS and survey error from the sealed scientific result and offline survey join. [Resident named baseline](raw-0016-best.md)

| Original radio index | Positive lanes v3 / 20/8 ms | Common positive lanes | Median absolute CFO difference | p95 | Maximum | Above 250 Hz |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 290 / 318 | 244 | 80.848 Hz | 155.508 kHz | 646.974 kHz | 36 |
| 1 | 150 / 188 | 117 | 92.475 Hz | 91.572 kHz | 487.589 kHz | 23 |

These tails compare the selected signed winning CFOs at the same receiver opportunities before track ownership or alias alignment. The receiver can choose different hypotheses at the same lane, so the tails measure disagreement across receiver outputs and do not measure CFO error against the same signal. The 250 Hz count describes that disagreement and adds no runtime threshold.

## Map and through-exit timing

The adaptive worker evaluated **156 of 179** full-layout reference locations, beginning with 59 actual paired samples. Every retained coordinate, failure field and objective value matched the corresponding full-layout row in both arms. It retained all **114 fixed-zero and 117 fitted-`c`** locations within 4.5 objective units of their respective minima. Both full-grid minima and score ranges remained the same. There were no failed full-layout rows. The 312 real objective callbacks produced 310 native factor and predictive calculations because each arm reuses its own endpoint evaluation. The adaptive map binds the actual phase state, original terminal and owner digests, original regional transform and unchanged fit path to its new position image. Each of the other seven PNGs matched encoded bytes and decoded RGBA. The 1680 × 960 research map labels the 156 sampled locations and leaves the omitted areas without interpolated scores. [Full map](development/weak-all8-adaptive-standard.png) · [Adaptive map](development/weak-all8-adaptive-sample.png) · [Research layout contract](live-adaptive-grid.md)

| Measured scope | Elapsed s |
|---|---:|
| Deployed v3 original waveform through exit, archived resident run | 10.824 |
| Older real 20/8 ms raw process on its earlier solver, archived | 8.639 |
| Authenticated 20/8 ms acquisition component of that raw run | 3.141 |
| Original fixed-map saved process through exit | 4.166 |
| Fresh adaptive saved process through exit | 4.370 |
| Separate-clock sum with fresh saved adaptive path | 7.511 |
| 1.6× allowance against deployed v3 | 6.765 |
| Measured producer cost of the earlier reusable index | 4.320 |

The candidate used a checked index built from an earlier causal archive. It paid compatibility and artifact load, recovered 19 of 20 distinct source bodies from that index and reparsed the unmatched body in the timed process. The port still verified the original causal sources. Its recorded preparation scope took about 1.3 s. The separate serial sum including the entire earlier index build would be **11.832 s**. No new from-empty index build or unindexed comparison ran on this request. With the historical 3.141 s acquisition fixed, a 1.6× result would require the complete saved charge to fall to **3.624 s**. [Portable preparation](portable-orbit-index.md)

The grid measured 0.184 s with the full map and 0.168 s with adaptation. The adaptive worker's numerical solve was 2.175 s and rendering 0.512 s. The full-layout archival clock had 67 major faults and 3,712 input blocks versus 1 and 80 on the candidate. The measured 0.204 s through-exit difference includes the rest of the worker and process variability. The same source, routes and readback criteria qualified the archived control, so a duplicate standard run was unnecessary. No new original waveform was opened and the separate-clock ratio carries no end-to-end claim.

Launch `weak_all8_adaptive.py launch FRESH_TMPFS_ROOT` and then `score FRESH_TMPFS_ROOT` with the pinned release environment and shared Gauss CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. The trial verifies the archived source bytes, signed packet and causal producer. Seven focused and adjacent tests passed. [Runner and verifier](weak_all8_adaptive.py)
