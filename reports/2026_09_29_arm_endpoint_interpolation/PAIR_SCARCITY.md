# Endpoint pair scarcity

The 32-dwell host cohort contains 64 receiver-dwell associations. Forty-two
have no paired endpoint candidate. The pair-count distribution is 42 with
zero, 8 with one, 8 with two, 5 with three, and 1 with five, for a mean of
0.6875 pairs per receiver-dwell. Consequently pairs-only performs local GLRT
work in 198 of 576 middle receiver-windows, whereas union supplies seeds to
all 576.

The timing gate is the main constraint. Among all 8-by-8 endpoint candidate
combinations, 49 of 64 receiver-dwells have some combination within the 8 kHz
CFO gate, but only 27 have any combination within the 8-sample circular timing
gate. Twenty-two have an edge satisfying both fixed gates. Of the 42 zero-pair
receiver-dwells, 27 have a CFO-compatible combination rejected by timing;
only 5 have a timing-compatible combination rejected by CFO. For combinations
already within 8 samples, the median minimum CFO difference is about 307 Hz,
well inside the frequency gate. For combinations already within 8 kHz, the
median minimum timing difference is 279 samples.

This follows directly from using only the retained top-eight blind candidates
at two windows 100 ms apart. Each inventory preserves duplicate coarse aliases
and many low-margin noise candidates. The same physical branch can therefore
be absent from one endpoint's bounded inventory, or represented by a different
timing basin, despite a compatible frequency estimate. The union result is
consistent with that diagnosis: its middle positives comprise 373 paired,
167 left-only, and 198 right-only candidates. Single-endpoint hypotheses add
substantial real coverage, though they also increase unmatched positives and
kernel work.

Plausible follow-up experiments are a larger endpoint inventory, duplicate
alias consolidation before enforcing the inventory cap, or a third sparse
anchor window to bridge endpoint identities. Relaxing the timing gate alone
would create many frequency-compatible edges hundreds of samples apart and
would need separate scientific validation. Ranking endpoint hypotheses by
margin before association may suppress noise, but cannot restore a physical
branch missing from one endpoint inventory.
