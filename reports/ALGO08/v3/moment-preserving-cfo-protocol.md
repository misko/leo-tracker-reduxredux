# Fixed-track polynomial-preserving CFO shrinkage

Use the frozen masked short receiver half-blend proposals on DS30-0019,
DS30-0274, DS30-0218 and DS30-0212. Reconstruct the ordinary unedited Graph
with the installed source and approved track configuration. Match its
track and assigned counts to the ordinary publication. Recover the exact
track and polynomial-piece membership and times from its native winners.
Unassigned proposed edits receive zero change. All anchors and rows
outside the original set of proposed edits keep their original CFO.

For each edited ordinary track, evaluate the released Legendre design at
its edited times using the fit's reference time, scale and actual degree.
For joined pieces use the released design constrained to continuity of
value and first derivative at the recorded join. Remove the Euclidean
orthogonal projection of the previous applied delta onto this restricted
design's column space. A track with insufficient column rank receives
zero. Use the standard binary64 SVD cutoff eps * max(shape) * s_max.
When the design spans all edited coordinates the remainder is exactly
zero. Multiply every remaining delta in each track by one common factor
at most one to meet the original half-bin absolute edit bound. Reserve
two CFO ulps for addition before checking the actual stored deltas. Do
not substitute alternate membership, wrap CFO, change unedited rows or
adapt the rule to a recording.

Seal the case masks, winner and membership hashes, raw and projected
delta energy in Hz², and maximum track-level moment before and after,
on the actual stored deltas. Test the moments against an explicit
binary64 summation and CFO-rounding bound. Track every original proposed
edit through zero remainders, unassigned rows and installed empties. Only
after computing the development projection for all four cases, open the
original installed receiver packets and compare unedited, the previous
half-blend and the projected edit using the frozen signed 250 Hz /
2-sample and 2,250 Hz / 6-sample readout. Record p95 absolute signed CFO
difference, paired restored/spoiled counts, and actual per-phase CPU and
wall time. The installed receiver is a same-capture measurement.

Rank 68, DS30-0280, was in progress at enrollment and remains held during
development. If the sealed four-case result has nonzero retained energy,
valid moments, and improves strict installed agreement over unedited in
at least three cases without a pooled net loss, wait for both authenticated
original rank-68 roles to verify and repeat the unchanged RF rule there
once. Derive its prior half-blend candidate-only with the original masked
rule, apply the same projection, then open its installed packet. Keep
that result separate. If the development screen fails, stop with
DS30-0280 unopened. Read saved metadata only on CPU 3. No raw waveform,
archive body, survey, receiver or position fit is in this study.
