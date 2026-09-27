# Matched DS6 fragment-linking position refit

Refitting position does not rescue the simple shared-fragment-offset model.
It worsens held prediction in all three scans with links and leaves the no-link
scan unchanged. This model is not promoted as an accuracy fix.

| MS/s | Separate-offset error (km) | Shared-offset error (km) | Shared held log-score change |
|---|---:|---:|---:|
| 2.5 | 3.670 | 3.759 | -73.88 |
| 5 | 8.482 | 7.794 | -32.30 |
| 7.5 | 0.505 | 0.526 | -48.77 |
| 10 | 6.284 | 6.284 | 0.00 |

Both arms retain all 221 tracks across the four development scans. The same
training-derived catalogue assignments and integer alias corrections apply to
the linked groups in **both** arms. All unlinked tracks retain their original
catalogue mixtures. The only model difference is separate offsets versus one
common offset per linked group. Each arm refits geographic position and shared
scan timing, selecting among four starts by training score. Whole-visit holdout
assignments remain unchanged. Exact orbit propagation audits the winners.

All eight selected winners converge and lie inside the local search bounds.
Four tests pass: training isolation in each arm, one-fragment equivalence,
source/input seals, complete track/group retention, training-only selection,
exact-propagation audit, and identical outcomes for the scan with no links.

These are conditional catalogue labels, not externally confirmed satellites.
The fitting code never loads the operator reference; the separate summarizer
scores the frozen locations afterward. A small improvement in one geographic
error does not outweigh the consistently worse held prediction or establish
DS6-wide accuracy. The complete 43-scan fixed-model baseline remains the
comparison point. No RF was collected and no production service was changed.
