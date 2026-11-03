# Ordinary joint fit at the same 16-scan budget

Compare all nine early→middle, early→late and middle→late donor–target pairs from the disjoint frozen-association experiment. Fit one ordinary q=0.2 mixture location plus 16 scan timings using the exact union of donor and target scans. Use the established six starts: E=-2,0,+2 km, N=0, each with cold or training-grid timing initialization. Select highest qualified training score. No geographic or held outcomes select fits.

Reuse the three early+middle cumulative16 fits from the temporal-forecast experiment, verifying exact ordered sessions, original source qualification and score replay. Execute six new 16-scan fits for early+late and middle+late. Preserve unqualified starts and failures; no retries. Cap each dataset subprocess at 300 seconds, BLAS1.

At each joint selected endpoint, evaluate original-model within-track held likelihood on only the target window, using its corresponding joint-fit timings. Compare against constrained refinement, direct donor-position use and target-only fit on exactly those target scans. Geographic metric is reference distance with the existing spherical convention. Pair rows reuse target windows; totals are descriptive and not independent validation trials.

All arms have access to the same 16 scans, but use them differently. This test asks whether freezing associations adds value beyond ordinary pooling, not whether more measurements help under independent blind evaluation. Reference uncertainty and site-conditioning remain. No RF collection or production changes.
