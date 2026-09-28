# Sparse coarse-proposal qualification

This approximate search experiment preserves every 20 ms window and final
scoring formula. It changes discovery: a subset of the original 16 frames and
12 anchor symbols proposes 32 separated peaks; nearby epochs receive the full
original coarse statistic. Only cells with repaired neighbors can become final
local maxima. The usual eight candidates then receive complete fine,
conditioned, verification, and GLRT evaluation. Missing discovery hypotheses
can lose hits. This is not an exact-equivalence optimization.

First screen budgets 1 frame / 3 symbols, 2 / 6, and 4 / 12 on the fixed
64-dwell metadata-balanced set. A 16 / 12 control must exactly match the
preceding full-search build. No RF is collected. Files and frozen baselines
remain unchanged. Test partial inputs, all four rates, zero input, repaired
neighbor identity, and peaks at both epoch boundaries before measurement.

Score individual margin >= 0.025 hits with maximum-cardinality one-to-one
matching within the same receiver/window, epoch difference <= 2 samples and
tracking CFO difference <= 8 kHz. Report positive-window recovery separately.
Unmatched new positive results do not count as recovered baseline hits and
are not automatically classified as false positives. Every counted candidate
must have completed GLRT; absent windows or failed executions invalidate a run.

Use the 64-dwell results to decide which variants justify CPU0 ARM timing and
the 704-dwell cohort. Prioritize the 2.5 MS/s 80% and 90% individual-hit targets;
report every rate, rather than hiding rate-specific failure in a mixed total.
Parameter selection is exploratory on this corpus. For an expanded candidate,
also report the remaining 640 dwells separately from the 64 used to select it.
This remains same-dataset evidence rather than a guarantee on future captures.

After all three 32-center budgets failed the 80% screen, the bounded follow-up
widened to 128 centers at 4/12 and 8/12. Both were subsequently evaluated over
all 704 dwells. This follow-up was selected from the first 64 cases; the 640
remaining cases are reported separately. The 4/12 option is an 80% candidate
for the current 2.5 MS/s priority, not an assumed 80% mixed-rate result.

Timing compares complete search on saved RAM input against verification-fusion
V1. No speed estimate from host CPU or operation counts is an ARM measurement.
The current coarse stage occupies about 59% of full CPU time, so even removing
it entirely would only provide about 2.4x overall speedup. A successful sparse
proposal is one step toward a faster pipeline, not enough for the 40% headroom
goal by itself.
