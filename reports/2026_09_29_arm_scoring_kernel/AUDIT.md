# Independent review and follow-up

SOL independently inspected the v1 source/binary receipts, every host704-v3
raw-file hash, unique finite candidate inventories, score deltas and ARM
accounting. It confirmed correct interleaved dual-RX CI16 indexing and exact
CI16-to-FP64 conversion. The explicit FP64 dot retains each component's
summation order for the finite bounded inputs tested. It did not establish
equivalence for arbitrary overflowing or nonfinite complex operands.

SOL identified a concrete unsupported path: the raw diagnostic leaves the
FP64 input workspace unpopulated, so fractional interpolation must not use it.
V2 now rejects every offset other than exactly zero before accessing inputs.
The separate offset regression test passes. All four ARM dwells and the full
704-dwell host parity qualification were rerun against v2, with the same
scientific results. All-rate zero/full-scale/random controls were also rerun.

Terra's independent review of the reduced detector established that cached
rotations/templates and block rotations already exist in the full scorer.
Bounded magnitude is transferable with numerical qualification; reduced frame
counts, symbol diversity, candidate counts and search radii change the
workload/statistic and were not imported here.

Both reviews emphasize that supplied original coordinates and retrospective
positive-only timing cannot establish discovery recall or end-to-end capacity.
Global limited-complex compilation remains a diagnostic variant, not the
selected implementation. Capture concurrency and production integration are
not tested in this report.
