# Source-balance family

This family leaves the original IID Student-t4, 100 Hz-scale candidate mixture
intact and changes only each track's contribution to a composite likelihood.
The grouping is frozen once, at the original same-scan IID training endpoint.
No held observation or reference coordinate participates.

A track is assigned to a physical source only if one visible candidate has at
least 0.90 conditional candidate weight. The bank's `candidate_ids` catalogue
row is mapped through the digest-bound archived roster to a physical NORAD.
The exact repeated-group key is `(NORAD, rf_hz, receiver_id)`. An ambiguous
track remains its own singleton and always retains unit weight. Candidate
mixtures remain complete during every subsequent objective evaluation.

The three screen-frozen variants are:

- `group_sqrt`: every member of a size `n` repeated receiver group has weight
  `n^-0.5`.
- `group_equal`: every member has weight `n^-1`, so each receiver-specific
  repeated group has total unit weight.
- `source_receiver_equal`: a `(NORAD, rf_hz)` source has total unit weight,
  split equally among receivers present and equally among that receiver's
  repeated tracks.

These are composite weighted objectives. They are not normalized physical
posteriors.

## Outcome

`source_receiver_equal` passed the exposed eight-scan screen (8/8 qualified,
7 wins, median 2,106.51 m versus 3,108.16 m), then improved the 23 qualified
fits on the fixed remaining-24 panel to a 2,350.77 m median versus 2,655.35 m,
with 14 wins. One replication scan remained an unqualified west-boundary
failure. Across the 31 qualified fits its unchanged-IID held diagnostic fell by
948.21 log-score units. The separately frozen additional-12 policy later had
only three paired wins among 11 matched estimates, a worse median and P90, and
one IID coverage failure. The source weighting therefore did not establish a
reliable or generalizable accuracy gain.
