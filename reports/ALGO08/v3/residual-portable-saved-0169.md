# Conservative renderer on the original DS30-0169 saved detections

The single combined saved publication took **11.920 s** including admission, compared with **17.893 s** for installed v3 and **12.485 s** for the previous history-risk publication with its admission. At **1.501×** against installed v3, the combined result remains **0.737 s** above the 1.6× target. The history-risk route and portable index were already active in the previous routed control. This trial changed the renderer and verified its output on the exact same scene. [Frozen protocol](residual-portable-saved-0169-protocol.md) · [Complete verification receipt](measurements/residual-portable-saved-0169.json.gz)

| Saved input to verified process exit | Wall, s | CPU, s |
| --- | ---: | ---: |
| Archived installed v3 | 17.893 | 17.883 |
| Previous history-risk with ordinary renderer, child only | 12.065 | 12.060 |
| Previous routed publication with admission charged | 12.485 | 12.479 |
| Residual layout candidate, child only | 11.894 | 11.861 |
| Residual layout candidate with admission charged | 11.920 | 11.883 |
| Replay with earlier portable index construction charged | 16.240 | 16.202 |
| Replay with earlier index and saved archive staging charged | 16.743 | 16.700 |

The fresh child includes **0.593 wall / 0.581 CPU s** to serialize its 16.8 MB scene after publication. Subtracting only that measured observation cost gives **11.327 s** prepared, a sensitivity estimate still 0.144 s above the 1.6× threshold. The charged child improved by 0.170 s and the admission-charged comparison by 0.565 s. Their difference reflects the different admission clocks, 0.026 s new and 0.420 s archived. Regional preparation was 1.986 s versus 1.991 s, and the full numerical solve was 8.183 s versus 8.145 s. The portable artifact's earlier creation took 4.320 wall / 4.319 CPU s. The saved archive staging experiment took 0.502 wall / 0.498 CPU s, copying and authenticating 62.55 MB of unique bodies in tmpfs. Neither was repeated. [Prior routed control](history-risk-held-0169.md) · [Saved archive custody](family-endpoint-transfer-0169.md)

The real candidate rendered in **1.376 wall / 1.357 CPU s**, including **0.928 wall / 0.926 CPU s** for all four original orbit sheets. On the exact saved scene, ordinary rendering took **2.414 CPU s** and the conservative renderer took **1.367 CPU s**, a measured 1.047 CPU s saving in drawing and encoding alone. Those render-only wall clocks were 4.837 and 1.403 s. The long wall-to-CPU gap on the ordinary rendering makes CPU the cleaner comparison for this order. The independent replay reproduced all eight live encoded PNGs and all eight historical ordinary PNGs, including the original title. All four orbit PNGs were byte-identical between layouts. Both residual sheets, position and track changed pixels, and both position sidecars name the current decoded, verified position PNG.

| Exact across installed, previously routed and new candidate | Fixed `c = 0` | Fitted `c` |
| --- | ---: | ---: |
| Horizontal error against operator reference | 505.761 m | 348.126 m |
| Conditional RF RMS | 111.057639 Hz | 111.056612 Hz |
| Ordered owner observations and roles | 2,236 | 2,236 |

All three complete publications matched the original signed full-20 ms detections and terminal, both numerical paths and all 179 grid scores per arm. Fitting `c` lowered the location error by 157.635 m and lowered conditional RF RMS by 0.001027 Hz. The historical regional offer and causal cutoff stayed fixed. The worker consumed one saved handoff covering 4,219 issued visits, 3,527 admitted and 692 invalid. All 50 snapshots were already resident. It verified 129 logical reads totaling 230,529,444 bytes. The index served 11,192 rows from one body. The other 34 bodies used the cold path. No invalid body, whole-index fallback, major fault or process input block was recorded. The producer used the earlier DS30-0008 cutoff `1794556783056720638`, before `1794795840131019267` for the consumer. This saved experiment opened no raw I/Q or backing archive.

| Existing routed saved control | Index hits | Cold bodies | Existing conservative publication before this trial |
| --- | ---: | ---: | --- |
| DS30-0138 | 7 | 26 | Ordinary output only |
| DS30-0160 | 4 | 32 | Ordinary output only |
| DS30-0169 | 1 | 34 | Ordinary output only |
| DS30-0316 | 0 | 40 | Separate render-only control |
| DS30-0374 | 0 | 40 | Ordinary output only |
| DS30-0402 | 0 | 42 | Complete matched saved publication |

All six controls admitted the same earlier portable artifact by digest. Its zero-hit cases loaded and verified the artifact and prepared all bodies on the cold path. The DS30-0402 conservative publication also used that same artifact with 0 hits and 42 cold bodies. The DS30-0316 renderer-only scene was the preflight for that experiment. [Previous conservative renderer validation](history-risk-residual-layout-0402.md) · [Six-case saved timing cohort](history-risk-0138.md)

The first preflight stopped before launch because sparse checkout excluded the tracked enrollment fixture. Restoring the exact fixture allowed the one worker under the shared low-priority Gauss slot. The frozen source is `6b6e8642a`. The uncompressed verification receipt SHA-256 is `c6922be6d55412b6d3144d2bf95b28c236697113f74f2f3c55ea89746122b68e`. Twenty-one component and adjacent tests passed. [Single-child driver](residual_portable_saved.py) · [Offline checks](residual_portable_saved_score.py)
