# Complete ARM positioning with prepared thresholds

The freshly profiled prepared-threshold scorer, qualified catalogue-index
session and unchanged in-memory pipeline complete in **245.188230 wall seconds /
245.158701 CPU seconds**, with **151,676 KiB** peak RSS. This includes checkpoint
parsing, exclusive-track selection, location-track construction, TLE propagation,
the full 400-point regional search and final selected-site associations.

All 400 search points and status fields match the qualified ARM JSON exactly.
The direct independent host comparison passes the existing 1e-9 Hz tolerance;
the maximum score difference is recorded in `host-comparison.json`. Final
association JSON matches the frozen host output byte-for-byte. Search remains
budget-exhausted (`complete: false`); this does not establish global convergence.

This isolated run has no simultaneous GLRT workload and cannot establish loaded
throughput. Its time is about 4.8 seconds below the earlier unloaded final-scan
position stage, but that is a historical comparison, not an interleaved full-run
control pair. The short paired PGO benchmark separately demonstrates a 1.674%
CPU saving. Concurrent qualification follows in
`../cadence-four-threshold-pgo-v1/`.

`protocol.json` records the exact executable, input hashes and argument list.
`link-input-sha256.json` pins linked libraries and the catalogue-index object;
integration source hashes match the prior qualified pipeline. The binary,
source snapshot, compiler log, complete search progress, whole-process timing,
association output and comparison receipts are retained here. The link uses
the existing catalogue-index session object before the new scorer archive;
it does not replace that session with the archive's ordinary lookup variant.
