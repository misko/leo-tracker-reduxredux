# Source-weight tempering (prepared, not launched)

The screen winner can strongly reduce the influence of a source seen through
both receivers. This new, separately declared family tests whether gentler
weighting preserves its location improvement while reducing failures and poor
unchanged-IID held diagnostics.

Starting from each scan's frozen `source_receiver_equal` weight `w`, the two
variants use `w^0.50` and `w^0.75`. Ambiguous singleton tracks remain exactly
weight one. Group membership, the physical NORAD mapping, the 0.90 training
threshold, candidate mixtures, optimizer budget, and screen indices
`0,4,8,12,16,20,24,28` remain unchanged. No geographic or positional prior is
added. Both scores are composite objectives rather than normalized posteriors.

## Outcome

`source_alpha050` passed the exposed screen; `source_alpha075` missed the
required median reduction (9.95%). On the fixed remaining-24 replication panel,
`source_alpha050` qualified all 24 and won 18 paired comparisons, but its median
was 2,694.60 m versus the IID median of 2,655.35 m. Its P90 and mean improved,
while its maximum worsened and its unchanged-IID held diagnostic fell by 183.78
log-score units. The selected screen median improvement did not replicate.
