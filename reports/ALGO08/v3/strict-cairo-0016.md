# Physical DS30-0016 strict packed storage with history and Cairo

The same 20/8 receiver, signed history-risk solver and Cairo publication finished in **6.542 s with the prepared derivative and its setup**, a **1.642×** speedup over the measured installed ALGO08v3 control. Creating and independently reading back the derivative raised first use to **11.527 s**, or **0.932×**. The installed comparison is the immediately preceding authorized whole-recording run on the same staged original. This test added one candidate and no fresh stock execution.

| DS30-0016 from raw CLI through exit | Elapsed s | Process CPU s | Elapsed speedup vs installed |
| --- | ---: | ---: | ---: |
| Measured installed ALGO08v3, original stage | 10.745 | 10.742 | 1.000× |
| Measured history and standard renderer, original stage | 8.829 | 8.824 | 1.217× |
| Measured history and Cairo, original stage | 7.677 | 7.659 | 1.400× |
| Strict packed history and Cairo child | 6.525 | 6.524 | 1.647× |
| Strict packed child plus candidate-specific setup | 6.542 | 6.541 | 1.642× |
| Strict packed first use, including conversion and independent readback | 11.527 | 11.517 | 0.932× |

Creating the derivative took 2.810 s, complete verification of all decoded original windows took 2.103 s, and compilation and other paid conversion work brought the total to 4.985 s. Shared custody and environment setup took a separate 0.045 s. Including it gives 6.588 s prepared and 11.573 s first use. The prepared calculation clears the 6.715 s target by 0.173 s before common verification. The 1.134 s measured improvement from original-input Cairo with candidate setup charged came mostly from authenticated acquisition, which moved from 3.188 to 2.156 s. Decision and publication moved from 3.844 to 3.800 s. Each run used one low-priority CPU 2 slot. The strict process recorded 0 input blocks and 0 major faults, compared with 2,512 and 35 in the earlier original Cairo process. This is one observation per process on resident raw data, with the original Cairo run's process I/O retained in its measured clock.

All 13 original compressed member digests, all 808 original decoded windows including invalid captures, and all 1,616 encoded derivative blocks were checked. The signed source occupied 993,933,681 B including manifests and indexes. The private derivative occupied 968,827,674 B and all 65 member files remained resident. The candidate authenticated 966,263,232 encoded B and decoded 545,600,000 B in 93 full and 620 short stereo visits. There was no original-waveform fallback or backing archive access. Each candidate and comparison processed 713 admitted visits and preserved the 95 original invalid captures.

The native packet is byte-identical to original-input Cairo, with 506 signed factors and 115 ordered owners in each calibration arm. The history route, terminal, both endpoint and RF records, exact numerical path and 179-point matched grid agreed. All eight Cairo PNGs had identical encoded and decoded digests and the actual position image matched both sidecar pointers. The published candidate's horizontal errors against the operator site reference were 0.490 km at fixed `c = 0` and 0.980 km at fitted `c`, versus 1.644 and 1.661 km for installed v3. Candidate RF RMS was 134.021 and 133.740 Hz, versus 109.375 and 109.479 Hz for installed v3. The site reference has no independent GNSS survey. Since strict storage preserves the science of its original-input candidate exactly, it has no separate calibration or position effect.

## Reproduction

The frozen protocol and implementation are in commit `1892fb9bd`. Use the single `strict_cairo_0016.py run /dev/shm/leo-v3-strict-cairo-0016-result01` command through the release interpreter as `leo`, with numerical thread limits set to one. Inside a private read-only bind mount at the original recording identity, point the mount to the complete verified staging subdirectory and hold `/tmp/leo-algo08v2-2x-bench/gauss.lock` exclusively with CPU 2, nice 15 and I/O priority 7. The converter itself reads only the absolute staged paths. The separate `score` command takes the same results root with checkout `src` available for standard product verification. The installed scientific CLI and frozen assets are verified before the child starts. The archived score contains the exact child arguments, conversion and scope receipts, prior control clocks, media and numerical checks.

[Protocol](strict-cairo-0016-protocol.md) · [Runner](strict_cairo_0016.py) · [Score](measurements/strict-cairo-0016.json.gz)

The unpacked score SHA-256 is `cc2268406d1e6cc9c3d3a8aec364c92ef89783b1904ba61630d466f301591d6d`. Original-input Cairo score `b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39`, installed/ordinary raw pair score `920456558c3b3ed29fcad552ee9b369b1b5ca0fda456211b85c6ee73748f662f`, and staging custody receipt `daaffec8a4e8d944db2989c108b547ee81ce38cb53b41344de38617d9a2a139a` bind the sources.
