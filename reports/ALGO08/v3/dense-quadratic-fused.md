# Fused geography with the actual quadratic graph on the dense saved proxy

One complete unprofiled saved replay cut CPU from **41.783 to 37.428 s** against the sealed original-projector quadratic control. The early geographic proof went from **8.939 to 4.690 CPU s**. Both used the incumbent ALGO08v3 DS30-0008 detector packet as a proxy for the dense input to the candidate graph. The candidate receiver's shortened waveforms were outside this comparison.

| Matched quadratic solve | Complete CPU s | Complete elapsed s | Early geographic proof CPU s |
| --- | ---: | ---: | ---: |
| Saved control, original projector | 41.783 | 41.797 | 8.939 |
| New replay, fused projector | 37.428 | 37.431 | 4.690 |

The saved packet digest, raw authority, causal archive, 25 km region and track asset matched. The actual candidate configuration uses maximum degree two, six minimum points, and two points per coefficient. The prepared graph digest matched exactly, with 7,016 observations, 6,576 graph points, 322 tracks and 144 with active curvature. Both replayed arms kept the same endpoints and RF RMS of 127.140 / 127.024 Hz, the same 4,328 ordered owner and role rows per arm, and the full 179-point grid, path and endpoint objective replay.

The full geographic prior still uses 11,177 catalogue orbits. The proof retained the 774 projected orbits, issued the same 25 probes, and stopped at the same `inside_score` with identical probe owners. The largest absolute score change was **2.585×10⁻¹³**, within the original projector study's **10⁻¹⁰** tolerance. The fused projector processed 79,838,100 cells with no fallback. Binding took 0.193 ms outside the solve clock. The comparison reuses the original control, so the measured 4.355 CPU second difference includes ordinary independent-run variation. This replay used saved detections and performed no acquisition, figure render, or publication-store write.

Three focused comparison and native-kernel tests passed. The runner pins the archived quadratic control SHA-256 `4b58d6487be44897f7528e383b2bb108f3e2dd0e5c81d9ae027fdaafbe91b5fb` and the original GraphAudit and solver sources from `fca52f6f9`. Reproduce from that exact instrumentation snapshot with the digest-pinned fused library and the standard one-core Gauss lock. The [earlier fused result](dense-geographic-kernel.md) used the original installed graph and retains its own report and timings. [Combined runner](dense_quadratic_fused.py) · [Summary](measurements/dense-quadratic-fused.json) · [Complete candidate receipt](measurements/dense-quadratic-fused.json.gz)
