# Exact full-catalogue normalization on complete fixed scans

Select the earliest frozen outside-pool target in each DS7/DS8/DS9, as in the
catalogue probe, but include every bank-eligible track. Freeze five locations:
center, N24 and the three existing N8 positions. Evaluate at timing −5, 0,
+5 seconds; these are pointwise scores, not fitted or integrated timing.

Reconstruct exact causal catalogue snapshots through read-only ports. Score
training and full tracks under three expressions, retaining q020 background:
(1) retained numerator / retained-visible count, (2) retained numerator /
full-visible count, (3) full numerator / full-visible count. Expression (2)
is a pointwise lower-bound approximation to (3), not an independently normalized
probability model. Separately report denominator effect (2−1) and omitted
numerator effect (3−2). No model fit or reference-based selection.

Require every retained prediction/visibility replay and complete-scan original
likelihood replay to pass (<1e-6 Hz and <1e-7 log units). Record omitted leading
candidates and signal mass at every track setting. Compare location rankings
at each fixed timing, including each location's score relative to center.
Do not compare raw density offsets as a new accuracy result. Three workers
with 180-second caps; preserve failures. No new RF or production changes.
