# Frozen second-TRAIN-group blind baseline protocol

Use exactly the 79 scans in the frozen Sep 21 16Z TRAIN group, in manifest
order. Verify every receipt session ID and every cache/receipt content hash
before fitting. No validation or test session may occur in the cohort.

Materialize all cache arrays once in the parent, retain all tracks spanning at
least three seconds, and fork four workers. Run the Cartesian product of nested
scan counts 1, 6, 16, and 79 with Sacramento 250 km and Reno 500 km priors.
Each task uses the published tau-zero scorer, beam width 3, and fixed grid levels
100, 50, 25, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, and 0.1953125 km.
The objective uses only training-mask rows and profiles one constant CFO per
track. Do not use published coordinates, identities, held rows, or reference
coordinates in search.

Seal all eight search results before complementary-row and reference scoring.
Any worker failure aborts the aggregate result; do not publish partial arms.
Record source and input hashes, exact membership, per-task runtime, and cache
bindings. This is a replication on a second TRAIN group, not validation.
