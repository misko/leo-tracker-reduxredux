# Compact GLRT-64 validation

The report-owned compact workspace is scientifically exact for the current scanner
GLRT-64 call, but its whole-call benefit is too small and inconsistent to advance as
the route to 10x.

The design and implementation were frozen before loading the two metadata-selected
development cases.  The source lock remained stable, both input hashes were unchanged,
and every warm and measured candidate response exactly equaled the corresponding full
baseline response.  Equality covers the first detection, decision and full best
margins, reason, all 22 probe responses, and every retained candidate field.  The
component suite has 22 passing tests; an independent 20-case differential sweep also
found exact correlation-array and final-score equality.

| Rate | Baseline median CPU | Compact median CPU | CPU speedup | Wall speedup |
|---|---:|---:|---:|---:|
| 2.5 Msps | 1,434.273 ms | 1,364.505 ms | 1.051x | 1.050x |
| 5 Msps | 3,890.196 ms | 3,893.413 ms | 0.999x | 1.001x |

Each cell is the median of three counterbalanced full calls after one warmup per
method and case, pinned to CPU 0 with numerical thread limits set to one.  The timed
region includes CI16-to-complex64 conversion and the complete scanner analysis.  The
sum of the two per-rate CPU medians improves only 1.013x; that aggregate is descriptive
because it weights two different rates equally.

The result agrees with the profile: conditioned workspace work is a minority of a call,
while all 22 blind acquisitions remain.  Keep this prototype as exact implementation
evidence, but prioritize the acquisition score-map path.  A useful next prototype is a
batched implementation that accepts all overlapping probe views while returning the
same per-probe maps, candidate inventory, NMS/refinement results, and configured GLRT
confirmations.

This is a two-case development diagnostic.  It does not qualify sensitivity,
deployment, ARM behavior, or holdout performance.  The result receipt SHA-256 is
`1a7e6eb7ff4dc45065bbac1258fb8866f4968b9a4f8bfbf748b980e7721c9f74`.
