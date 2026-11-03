# Local tracklet linking v2 targeted revision

This is one post-result revision of v1, not an independently frozen research method. V1 diagnosis found that all eight lanes reached the chronological 1,024-fragment cap. V2 changes only that measured failure: each 8 s window generates the same bounded seeds, removes near-duplicate hypotheses with at least 80% membership overlap and near-equal frequency/rate, and retains at most 16 diverse fragments from that window. Every window can therefore contribute to chronological linking. Window size/step, scientific gates, linking logic, and the final 16-track-per-lane limit remain unchanged.

The new regression places many dense, early, three-source clutter bursts before a valid late track. The late track is reconstructed, demonstrating that early windows no longer consume a lane-wide fragment budget. Existing curvature, crossing, gap, alias, clutter, jitter, and noncanonical-RF tests also pass. Host and ASan/UBSan tests pass; Cortex-A9 hard-float binaries cross-compile successfully.

Strict shared evaluation passes. ARM observations produce 123 hypotheses, represent 40 of 62 eligible references, recover 36 one-to-one originals, and have 705.80 Hz local prediction p95. Server observations produce 124 hypotheses, represent 53 of 62, recover 46 one-to-one originals, and have 593.02 Hz p95. Host reconstruction timing was 0.00486 s synthetic, 0.28458 s ARM observations, and 0.33389 s server observations. These are workstation timings; physical ARM timing is delegated to the shared benchmark.

The frozen binaries are `artifacts/leo-local-tracklet-linking-v2` and `artifacts/leo-local-tracklet-linking-v2-arm`. Inputs, source, and binaries are recorded in `SHA256SUMS`.
