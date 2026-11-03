# Streaming Kalman v2 targeted duplicate revision

This is one post-result revision of the frozen v1 tracker. The v1 source and
artifacts remain unchanged. V2 changes only hypothesis clustering before active
beam selection and final output capacity selection; Kalman noise, gates, rate
bounds, gap, support thresholds, rolling births, and lane authority are the
same as v1. No parameter sweep or server-label tuning was performed.

Near-duplicate hypotheses are clustered when at least two thirds of the
smaller membership uses the same chronological source groups, shared CFOs
agree circularly within the existing 400 Hz measurement sigma, projected CFO
states agree modulo the lane-scaled alias spacing within 400 Hz, and rates
agree within 400 Hz/s. The best-scored hypothesis is retained. The continuation
rate condition preserves distinct trajectories at a frequency crossing.

The added dense regression presents eight near-identical candidates per source
and then starts a second curve late. Both curves survive; 3,391 duplicate
hypotheses are removed and only five materially different histories are
emitted, instead of allowing copies of the first curve to occupy the bank.
Existing curved-arc, crossing, aliases, gap, lane, clutter, and jitter tests
continue to pass.

## Frozen results

- Synthetic: 16 hypotheses, 235 used observations, 0.00467 s reconstruction.
- ARM-derived input: 125 hypotheses, 3,021 used observations, 0.18467 s;
  33 maintained segments represented excluding ref10, all 33 one-to-one;
  prediction-error p95 426.0 Hz.
- Server-derived input: 128 hypotheses, 3,917 used observations, 0.17559 s;
  47 maintained segments represented excluding ref10, 39 one-to-one;
  prediction-error p95 414.8 Hz.
- External peak host RSS was 12.0 MB.

The strict shared evaluator accepted both real outputs. Optimized host and
ASan/UBSan tests passed, and the Cortex-A9 hard-float toolchain produced both
ARM binaries. This remains an overlapping hypothesis bank rather than an
exclusive assignment, so its track count must not be read as a physical-object
count. Clustering can retain different partial histories of the same eventual
curve and can discard a valid close continuation if its source overlap and
rate fall inside the stated equivalence region.

`runs/` contains final stdout, machine-readable stderr, wall/RSS measurements,
and strict evaluator JSON. `artifacts/` contains frozen host and ARM binaries.
`component/` contains test and ARM-build evidence. `SHA256SUMS` records the
evidence, binaries, v2 source, and preserved v1 source snapshot hashes.
