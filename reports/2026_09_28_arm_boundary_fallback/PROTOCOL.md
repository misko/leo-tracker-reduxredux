# Selective conditioned-search fallback

Objective: retain a measured ARM speedup over full refinement while recovering
at least 90% of original individual GLRT hits, especially at 2.5 MS/s, and
report all four supported rates. Every original window and coarse candidate
remains evaluated; recovery is not dwell confirmation or positive-count parity.

Start from the fine-direct experiment. After its final GLRT, calculate the
distance of residual CFO from either end of the principal interval:
`abs(abs(tracking_cfo - acquired_cfo) - 1/(2*4.4e-6))`.
If this is at most 1,000 Hz, execute the original conditioned grid over
interpolated fine CFO +/-2 kHz, including guarded exact near-maximum rechecks,
then rerun GLRT at the conditioned winner. Otherwise retain the direct result.
Do not apply modulo corrections or copy any oracle frequency into outputs.
Verification ranking remains skipped, so this remains an approximate variant.

The threshold was chosen retrospectively from the existing 704-dwell
fine-direct diagnosis: all 3,370 baseline-positive same-proposal frequency
branch differences were within 1 kHz of the boundary, while only 9,477 of
123,904 total candidates met the predicate. Thus this entire 704-dwell
qualification set is development data for the threshold; its 640-dwell
remainder is not an independent held-out test of this new rule. Report this
selection limitation openly. A boundary predicate learned here must still be
executed on IQ; retrospective coverage is not measured recovery.

First run the established 64-dwell screen, then all 704 if promising. Validate
the fallback against exact original conditioned scoring, nonfallback against
the direct path, all rates, partial/zero data, and boundary predicate edges.
Use the original one-to-one maximum-cardinality hit matcher within the same
receiver/20 ms window, <=2 epoch samples and <=8 kHz tracking CFO with margin
>=0.025. Report unmatched positives and recovered positive windows separately.

ARM timing uses CPU0 of PLUTO+ 192.168.1.15, saved IQ processed from RAM, no
RF collection and no simultaneous capture. Compare the same four full
120 ms dual-RX dwells with the original full-refinement baseline and the
fine-direct variant. Record fallback counts and actual GLRT kernel calls;
a second GLRT does not add a new candidate evidence entry. This intermediate
goal does not establish the broader real-time 40% headroom objective.
