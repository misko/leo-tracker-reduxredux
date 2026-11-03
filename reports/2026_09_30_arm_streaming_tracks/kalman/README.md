# Bounded streaming Kalman research trial

This is the frozen first implementation of a chronological two-state
frequency/rate Kalman CFO tracker. It is a local research component and does
not fit an orbit or use server labels in reconstruction or configuration.

## Frozen configuration

- state: normalized frequency and frequency rate
- measurement sigma: 400 Hz
- white acceleration process sigma: 60 Hz/s²
- innovation gate: adaptive to covariance, with a hard 5,000 Hz ceiling
- rate bounds: -15,000 through +15,000 Hz/s
- maximum unattested gap: 4 s
- output minimum: 8 distinct chronological source groups spanning 4 s
- exact lane authority: receiver, channel, edge, and actual RF
- alias spacing and measured CFO are both scaled to canonical 11.2 GHz
- bounded bank: 96 hypotheses per lane; 24 slots reserved for two-point births
- association: best two gated detections plus an explicit missed-detection branch
- output: at most 16 tracks per lane

Every source group is processed in chronological order using the actual center
time of each candidate. Pair births are generated throughout the stream from
all candidates in earlier groups within the 4 s window; there is no global
seed-ranking cap. The serialized result is explicitly an overlapping
hypothesis bank and is not an exclusive assignment.

## Results

The host CLI reconstructed the synthetic input in 0.0089 s, the ARM-derived
observations in 0.2051 s, and the server-derived observations in 0.2052 s.
External wall times were 0.01 s, 0.22 s, and 0.22 s respectively. Peak host RSS
was 13.4 MB on the largest run. The shared parser/evaluator accepted both real
outputs. Each side produced 128 hypotheses and represented 14 maintained
segments excluding ref10; one-to-one counts were 14. Prediction-error p95 was
404.6 Hz for ARM-derived observations and 374.4 Hz for server-derived
observations.

Optimized host tests, ASan/UBSan tests, and Cortex-A9 hard-float cross-compiles
completed successfully. Unit coverage includes curved arcs, crossings,
noncanonical-RF aliases, gaps and late births, clutter, exact lane boundaries,
and candidate timestamp jitter.

## Limitations

The fixed 96-state beam can discard a physically valid path in dense clutter;
the birth reservation prevents total late-birth starvation but does not prove
global optimality. Two alternatives are retained only locally, and no global
exclusive assignment resolves duplicated or overlapping outputs. The 128 real
hypotheses contain substantial duplicates, so track count is not a candidate
count. The compatibility TRACK line is a weighted linear summary of the
selected Kalman membership, while association uses the evolving frequency/rate
state. No board timing or new RF collection was performed here.

`runs/` contains final stdout, reconstruction stderr, wall/RSS measurements,
and shared evaluator JSON. `artifacts/` contains host and ARM binaries.
Pre-correction directories retain rejected audit attempts and are not results.
`SHA256SUMS` records final binaries and run evidence.
