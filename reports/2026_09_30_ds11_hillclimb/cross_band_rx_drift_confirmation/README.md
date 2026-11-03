# Remaining-24 confirmation: small receiver-difference gain replicates

The unchanged cross-band leave-NORAD model passes the declared additional-panel
measurement gate. Sixteen of24 scans improve, versus the required15; mean scan
gain is2.864 native Hz and median gain0.602Hz. This is held receiver-difference
prediction, not geographic improvement.

All369 eligible pairs have enough donor identities and a qualified slope.
Of7,540 held pairs,5,821 receive the drift prediction;1,719 retain the constant
prediction outside the donor-center time interval.188/369 track pairs improve.
Slopes range from-8.580 to+7.156Hz/s, median-0.509Hz/s. All24 scans remain in the
aggregation, including eight adverse scans. Per-scan results and every held
absolute error are retained in `outcome.json`.

The screen and confirmation have23/32 positive scans, but the effect is small
and source weighting matters. The metric averages pair gains within NORAD,
then NORADs within scan. It does not count the10,140 held pairs as independent
trials. These are same-site recordings with conditional training-selected
identities, not independent deployment validation.

Two tests pass: exact AST equivalence after reversing declared index, gate,
description and binding changes; and numerical behavior parity. The bounded
single-thread execution exits0. Independent source/aggregation checks pass.
A separate standard-library scalar replay reconstructs all499 target pair
training/held samples, donor exclusions, medoids, slopes, intercepts and
predictions across both panels. All10,140 held errors agree exactly (0Hz
maximum discrepancy).

One track appears in two pair rows in the screen and two tracks do so in
confirmation. A correction layer must avoid double correction and order
dependence: conservatively leave every pair touching such a track unchanged
and report lost coverage before geographic testing.

The next step is a fixed-position likelihood ablation on the screen with three
allocations: RX0 unchanged, symmetric, RX1 unchanged. Preserve causal banks and
the original reference-free training endpoint. Better differential prediction
does not identify common drift or a preferred allocation. Geographic promotion
still requires qualified single-scan fits and lower position error, reporting
all allocations and failures rather than choosing an anchor by truth.
No position fit, new IQ, RF collection or orbit replacement occurred here.
