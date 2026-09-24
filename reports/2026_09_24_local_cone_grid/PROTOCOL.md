# Frozen TRAIN-only local cone grid

Search two prespecified local regions centered on frozen cell 3
(37.90230600858144, -122.39601220145329) and frozen cell 5
(37.80184772652388, -122.41023886955833). Each is a 20 km by 20 km square in
local east/north coordinates. The centers and extents are frozen without using
the reference coordinate.

Evaluate the union of each region's 5 km lattice first. Score seven methods at
every point: ordinary unconstrained visible-Doppler baseline and staged fixed
cones with full FOV 10, 20, 25, 30, 40, and 50 degrees. For each cone, use
nominal axes 20 degrees apart, at most 15 degrees shared tilt, the existing
one-degree tilt and five-degree yaw/tilt-azimuth grid, baseline winner IDs frozen
before orientation fitting, and one visible-candidate refit after orientation.
Use one canonical receiver mapping because the full yaw grid makes the exchanged
mapping equivalent; verify parity at benchmark points.

Within each original region and for each method separately, select the best
point with deterministic coordinate ties. Evaluate a clipped 3-by-3
neighborhood at 2.5 km around it. Repeat method-specific selection and a 3-by-3
neighborhood at 1.25 km. Deduplicate shared points before
evaluation. Thus at most 50 coarse + 126 first-refinement + 126
second-refinement points are evaluated. This one-seed-per-method fallback was
frozen after the three-point benchmark projected the two-seed serial design
above the 20-minute wall limit; it retains independent refinement in both
regions without adding multiprocessing state risk. Selection uses
training loss only. Retain the best final evaluated point per method and region;
do not use held loss or truth for search or selection.

Use the same first six scans from both TRAIN groups, randomized training/held
masks, training-only CFO, ordinary visibility candidate rule, >=3 second track
span, occupied-second weights, and all-track capped squared-RMS denominator at
800 Hz. Held rows are evaluated only after each point's assignments and
orientation freeze. Cache RF costs and local directions once per geographic
point; reuse the baseline-direction angle table across all cone widths.

Before the full grid, benchmark three prespecified points: the two region
centers and their coordinate midpoint. Record preparation and orientation
times, projected worst-case runtime, memory, and mapping parity. Do not launch
if the projection exceeds 20 minutes.

Seal all inference results before calculating distance to the existing
reference coordinate. Then add a clearly labeled post-seal error column and
truth marker to the plot. Compare against the old cell 3/cell 5 errors without
claiming guaranteed improvement or using the comparison to alter the search.
Use no VAL/TEST, new RF, QNAP write, or deployment.
