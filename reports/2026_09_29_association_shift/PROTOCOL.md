# Association response between pooled and panel fits

For each of the 18 saved eight-scan fits, compare its selected training point and scan timings against the selected N24 point with the same scans' N24 timings. Both endpoints are fixed. Use all tracks; no new optimization, reference coordinate or held score enters the comparison.

For each track, reconstruct the original normalized q=0.2 mixture over retained visible satellite candidates and the linear-trend background. Where visible support is identical, decompose exactly:

`log Z_panel - log Z_pool = E_pool[log component_panel - log component_pool] + KL(p_pool || p_panel)`.

Report the frozen pooled-responsibility term, the posterior response KL, top-component changes, conditional-satellite MAP changes, signal responsibility changes and posterior total variation. This identity quantifies the response of soft association at fixed endpoints; it does not identify true satellites, isolate a causal mechanism, or give a new fit's performance. Candidate probabilities are conditional on retained site-conditioned banks. Timing and position both change between endpoints.

If visible support differs, retain the track in total score and support-change counts but omit its finite-support decomposition. Do not silently align incompatible supports. Require direct summed scores to replay saved panel score and independently evaluated pooled-subset score within 1e-7; require per-track decomposition error below 1e-8. Preserve all 18 panels regardless of outcome.

Per-dataset process cap 300 seconds, BLAS1. No new RF or production changes.
