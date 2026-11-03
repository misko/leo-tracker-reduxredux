# Source-consistent N8 comparison

Freeze the exact `grid_DS7_balanced_0`, `grid_DS8_balanced_0` and `grid_DS9_balanced_0` scan memberships (eight time-balanced scans per dataset). Reuse the first-scan quality sidecars, export the remaining 21 through the already corrected pinned read-only public adapter, and bind every point to its existing baseline export. No IQ or RF collection. Per-export cap 60 seconds; one sequential export stream per dataset, at most three streams. Preserve failures; do not replace a scan.

Use the unchanged seeded-greedy source-consistent selector from the single-scan pilot independently per scan. Rank/select only by training support and deterministic IDs; enforce all-point source disjointness. Keep all eight scans and report coverage losses. No margin-based weights or reference-based selection.

Reuse the qualified all-track six-start fit, requiring exact ordered membership and score replay. Fit source-consistent tracks using the same six cold/grid starts and original q=0.2 model and numerical gates. Select by training likelihood only; preserve failed starts. Per-dataset fit cap 180 seconds.

Compare reference distance after selection and evaluate both parameter vectors on the SAME source-consistent held tracks. Different track-set likelihood totals must not be compared as improvement. These exposed panels are not independent blind trials, the reference uncertainty is unknown, and candidate banks remain site-conditioned. Do not promote from three outcomes alone.
