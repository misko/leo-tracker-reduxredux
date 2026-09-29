# Exact overhead opportunities outside peak selection

Wave4's four-dwell ARM evidence reports 1,687.046 ms actual fused CPU per dwell
and 1,634.885 ms for `proposal + full_search total`, leaving 52.161 ms in the
outer fused wrapper.  Inside search, `total_cpu` is 1,175.720 ms while coarse,
acquisition, and timed final GLRT account for 842.704 ms.  The 333.015 ms
remainder includes ingestion, peak enumeration/retention, cache lookup and
other orchestration; it is not a timer for any one operation.  Conditioned
timing overlaps acquisition for initial conditioning and therefore must not be
added when computing this remainder.

Static inspection identifies these exact-output opportunities, in likely
priority order:

1. The fused wrapper copies one receiver from interleaved CI16 into a temporary
   `leo_presence_complex` array for every window.  `ingest()` immediately scans
   that array for finite/range checks and copies it again into the workspace's
   complex-double samples.  A stride-aware CI16 ingest can validate and convert
   directly once.  This is the clearest target within the measured 52 ms outer
   gap plus the unreported `conversion_cpu_ms`; candidate arithmetic need not
   change.
2. The wrapper clears `frame` bytes, marks at most four five-cell proposal
   neighborhoods, then scans every epoch to create `regional_epochs`.  Building
   the at-most-20 sorted unique clipped epochs directly removes an O(frame)
   clear and scan from every receiver/window while preserving the exact region
   list.
3. Production measurement can compile out per-candidate `clock_gettime` calls
   while retaining a single outer timer.  This preserves scientific outputs
   but changes diagnostic telemetry, so it needs a separately labeled timing
   build and exact candidate parity.
4. `full_frame_support()` is recomputed for each retained candidate although
   support depends only on epoch and sample count.  A small per-window lookup
   keyed by the restricted epoch inventory could avoid duplicate work.  The
   likely saving is smaller and should be instrumented before implementation.

Peak enumeration, stable sorting, scratch allocation, and top-eight retention
are deliberately excluded because a separate agent owns that optimization.
Candidate insertion sort (at most eight items) and the small linear final-score
caches are unlikely to dominate without measurements.  These are static
opportunities, not measured savings.
