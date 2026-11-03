# Causal older-state preparation for DS11 uncertainty pilot

Use only the exact archive occurrences pinned by ds11_revision_support for
scans0 and16. For every track and every original candidate slot, propagate both
the exact original elements and the selected older elements on the original
observation times and timing grid. Preserve physical/catalogue identity order.
No new candidate search, missing-record deletion or baseline replacement.

Require original replay differences <=1e-8km position and <=1e-10km/s velocity,
matching the established bank replay tolerance. Require finite older states
and complete candidate propagation. Save older position/velocity arrays and
original candidate IDs in a separate local NPZ, binding inputs, archive paths,
code and the output digest. Do not modify original banks or archived bytes.

Each scan has one single-thread process under90seconds, no more than two
concurrent workers. Preserve failures; do not infer a geographic gain from
element differences or successful state preparation. No held residual scoring,
reference coordinates, optimizer fits, IQ or RF collection.
