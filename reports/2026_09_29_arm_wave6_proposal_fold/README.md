# Wave 6: shared-base three-lag proposal fold

This isolated prototype starts from `arm_wave5_final/builds-v2`.  It retains
the lag-1, lag-3, and lag-5 feature definitions, normalisation, resampling,
ranking, and top-four selection.  The power feature remains omitted.

For every frame, the fused pass loads and converts each base CI16 sample once,
then loads each of the three delayed samples and writes to three independent
complex folded buffers.  Each output cell is still updated in increasing frame
order.  The ARM path shares base NEON loads for the common valid prefix and
uses the prior per-lag fold routine for unequal tails.

The three buffers use `3 * n * 8` bytes: at 2.5 MS/s (`n=3333`) this is
79,992 bytes total (78.1 KiB), or 53,328 bytes (52.1 KiB) incremental over the
single-buffer implementation.  No power buffer is allocated.

`build.py` produces host, sanitizer, and ARM cross-build receipts.  ARM
execution is deliberately outside this prototype's scope.

Validation: the host32 gate (704 windows) and host704 cohort (15,488 windows,
86,439 emitted candidates) have zero changed windows and candidates against
the sealed Wave5-final-v2 reference.  The frozen host704 audit reports
19,217 recovered hits from 19,581 reference-positive hits, unchanged from the
base.  Root's ARM4 physical run also had exact candidate parity and measured
908.417 ms per dwell, versus 960.455 ms for the base: 52.038 ms (5.42%) lower.
Its proposal-fold stage was 154.575 ms versus approximately 206 ms.  These are
ARM measurements; host timing is not used for that comparison.
