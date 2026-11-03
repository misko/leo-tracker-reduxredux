# Original32 source-balance regime diagnostic

This is a read-only descriptive join over all 32 original DS11 policy rows. No
model was refit, no association was recomputed, and the one unqualified raw
challenger at index 26 remains an IID fallback with zero paired change.

The apparent improvement is stronger at lower sample rates, but it is not
confined to a single rate. The 2.5 MHz group had 3/4 wins and a +995 m median
paired change; 5 MHz had 7/9 wins and +467 m; 10 MHz had 9/14 wins and +211 m.
The 7.5 MHz group had 2 wins, 2 losses, and the fallback tie, for a zero median.
The 2.5 MHz scans also had much larger original errors (6,985 m median) and
three of four occur in the last chronological quarter, so rate, time, and
available error headroom are confounded.

Chronology shows the same concentration. The first eight scans were evenly
split at 4 wins and 4 losses with a -2 m median change. The next quarters had
median changes of +205 m, +585 m, and +473 m. Descriptive rank correlations
with paired improvement were +0.292 for index, -0.261 for sample rate, and
+0.465 for original IID error. These small exposed groups do not identify a
time or rate effect.

The frozen association-count metadata does not show a clear monotone
explanation. Rank correlation was +0.184 with repeated sources and -0.081 with
effective weight fraction. Scans with an effective weight fraction below two
thirds did have 9/11 wins and a +509 m median change, but the middle and upper
bins are nonmonotone and the bins are post hoc. Selected per-track identities
were not serialized, so the diagnostic uses existing unambiguous/ambiguous and
repetition counts rather than recreating associations.

The result supports a narrow next question: whether the policy's improvement
transfers across rate and chronology under a new frozen cohort. It does not
support claiming that sample rate, capture time, or repeated-source count
caused the original32 improvement.
