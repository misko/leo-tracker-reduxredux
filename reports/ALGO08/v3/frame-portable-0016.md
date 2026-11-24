# DS30-0016 selective visit frames, portable orbit index and conservative publication

One complete combined replay took **7.379 s** with the standard-compatible capture and earlier orbit index ready. It ran at **1.456×** against the historical installed v3 raw control, leaving **0.663 s** to reach 1.6×. The qualified selective reader with full Cairo previously took **6.890 s** on the same new recording. The combined candidate preserved the complete science and reproduced all four ordinary Matplotlib orbit PNGs on the same titled scene. [Frozen protocol](frame-portable-0016-protocol.md) · [Qualified encoding pair](visit-frame-raw-0016.md) · [Machine receipt](measurements/frame-portable-0016.json.gz)

| Complete run or added cost | Wall, s | CPU, s |
| --- | ---: | ---: |
| Historical installed named v3, original encoding | 10.745 | 10.742 |
| Same new recording, ordinary reader and full Cairo | 7.653 | 7.635 |
| Same new recording, selective visit frames and full Cairo | 6.890 | 6.865 |
| Combined candidate through exit, with scene capture | 7.370 | 7.341 |
| Combined candidate including readiness checks | 7.379 | 7.344 |
| Combined candidate with common custody checks also charged | 7.403 | 7.360 |
| Earlier published portable index construction | 4.320 | 4.319 |
| Prepared recording with fresh index construction charged | 11.699 | 11.663 |

The observed complete child included **0.052 s** for writing the verification scene after publication. Even subtracting that observation cost leaves about **0.611 s** to 1.6× with candidate-ready checks charged. The earlier compatible capture experiment paid a further **8.412 s** in measured stages, including 2.167 s of original hydration, 2.046 s for writing the encoding and side tables, and 4.199 s for independent full and prefix readback. Charging those stages and the earlier index construction brings the prepared replay to **20.112 s**. Those are archived preparation costs for reuse accounting. This run performed no conversion or fresh index build.

| Measured stage | Prior selective + full Cairo | New selective + portable + residual layout |
| --- | ---: | ---: |
| Authenticated raw acquisition | 2.352 s | 2.350 s |
| Regional orbit preparation within solve | 1.580 s | 1.323 s |
| Figure render | 0.502 s | 0.980 s |
| Decision through publication | 3.942 s | 4.329 s |

The earlier DS30-0008 producer cutoff was `1794556783056720638`, before the DS30-0016 cutoff `1794568912154038024`. Its reviewed 2,688,577-byte artifact served **19 bodies and 212,721 indexed rows** after guard and load in 1.8 ms. One body used the cold path, with zero invalid bodies or whole-index fallback. Both runs performed 99 verified reads totaling 177,013,672 logical bytes. The single-order through-exit comparison changes the renderer and index together. The orbit preparation clock is consistent with the earlier preparation-only saving of 0.219–0.240 s. On the candidate's exact saved scene, the ordinary renderer took **1.428 s** and the residual-layout renderer **0.887 s**, a measured standalone reduction of **0.541 s**. This render-only pair isolates ordinary versus partial Cairo on this scene. The live full-Cairo comparison uses a previous complete process.

The selective path authenticated 991,704,602 encoded bytes through all 13 members. It fed 416,654,057 bytes into the decoder and verified 545,600,000 decoded bytes. It processed 713 of 808 issued stereo visits, with 95 authenticated invalid visits. Both complete selective runs made 186 full-aperture and 1,240 short-aperture lane calls. The prepared capture, 46 catalogue references and portable index remained in tmpfs. The candidate exited zero with zero process input blocks and zero major faults. No backing waveform and no additional raw, named or omitted solve was run.

Both calibration endpoints, conditional RF RMS, all 115 ordered owners and roles per arm, the 179-point matched grid and the fit path equal the prior new-archive selective result. Native and terminal digests are byte-identical on this new recording identity. Fixed-zero and fitted operator-reference errors are **0.490 km and 0.980 km** versus historical named v3's **1.644 km and 1.661 km**. Conditional RF RMS is **134.021 Hz and 133.740 Hz** versus **109.375 Hz and 109.479 Hz**. The operator reference lacks an independent GNSS survey. The earlier cross-encoding comparison established exact normalized measurements, owner mappings and science against the original capture, with raster changes limited to the recording title band. This replay kept the new recording title. The same-scene ordinary renderer reproduced all four live orbit PNGs byte for byte, the residual-layout replay reproduced all eight, and both current position sidecars bind the independently decoded position PNG. This evidence is specific to the containing offer.

The exact merged runtime and one eligible raw child were frozen at `0ca13825d`. The isolated entry observes and serializes the real render packet after publication. The offline verifier then checks both fresh scenes and opens all publication products. Its first renderer-only check compared incompatible digest representations after drawing both scenes. The corrected verification repeated only the render check. The immutable raw seal is `0beae68396a94d8ae4ced1bccd4e4de3b7ef5459a3575e39bcad224139e479dc`. The unpacked machine receipt SHA-256 is `7f47d9c37f3e769de57874595b8214b85267938fc6777601fa2d311e3f250424`. Sixteen component and adjacent tests passed.

[Single-child driver](frame_portable_0016.py) · [Verification](frame_portable_0016_score.py) · [Earlier portable preparation](validated-satrec-reuse.md) · [Dense ordinary orbit layer guard](history-risk-residual-layout-0402.md)
