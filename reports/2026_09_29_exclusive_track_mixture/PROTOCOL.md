# Exact soft source-exclusion mixture

Use the same three balanced N8 sets and all eligible tracks from the source-consistent comparison. A latent active-track set may contain no two tracks sharing a probe source group. Inactive tracks retain the existing normalized linear-trend background density; active tracks use the existing conditional retained-candidate satellite density. Start from independent signal probability 0.8 and condition that prior on source consistency.

For fixed graph G, signal densities f_i and background densities b_i:

`log p(y|x,G) = sum log b_i + log Z_G(log(4)+log f_i-log b_i) - log Z_G(log(4))`,

where Z sums products over every independent set, including the empty set. Connected components in the inspected exported pilot graphs have at most eight tracks. Enumerate all independent sets exactly per component; refuse components above 12 tracks rather than approximate silently. Posterior active probabilities give analytic mixture-gradient weights. With no conflicts this reduces exactly to the existing q=0.2 model.

This is a normalized working density on the fixed exported-track contrast space, conditional on the conflict graph and retained banks. It is not a calibrated raw-IQ likelihood: background-track dependence and data-dependent candidate/graph construction remain approximations. No track is omitted from scoring, and every hypothesis uses the same observation dimensions.

For each dataset, use two local starts: the saved all-track fit and the saved hard source-consistent fit. Select the highest qualified NEW training score; preserve failures. Original optimizer/bounds/audit gates apply. Per-dataset cap 180 s. This is a two-start diagnostic, not a global optimum or six-start benchmark replacement.

Evaluate both new-model and old-model held conditional scores at the old and new parameters on the same complete track set. Separate model replacement from parameter movement. Report retained coverage, expected active count, geographic distance after selection, and all failures. No RF collection, source input changes or production changes.
