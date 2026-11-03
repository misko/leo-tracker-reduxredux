# Certified progressive coarse-pruning feasibility

This is a source and saved-evidence analysis. It changes no detector,
contract, golden, device software, or RF data and performs no new replay.

## Deployed retention rule

The corrected deployed interval mode selects `refinement_mode == 7`, which
sets circular epoch separation to 5 samples and CFO separation to 10 kHz.
The coarse grid is spaced by 80 kHz. Candidates are sorted canonically and
greedily retained; a candidate is suppressed when both its circular epoch
distance from an earlier retained candidate is less than 5 and its CFO
distance is at most 10 kHz.

The eighth score from an arbitrary set of eight retained seeds is not a lower
bound on the final eighth score. For example, same-bin seeds at epochs
0, 5, ..., 35 are mutually retainable. A later-discovered higher-score peak at
epoch 3 suppresses the seeds at epochs 0 and 5. Only seven scores at least as
large as the old eighth score are then guaranteed.

## Sufficient safe threshold

Let `S` contain eight fully evaluated exact local peaks. Require every pair in
`S` to have disjoint conflict neighborhoods. Under the deployed rule, this is
true when each pair has either:

- coarse CFO distance greater than 20 kHz; or
- circular epoch distance at least 9 samples.

For the deployed 80 kHz grid, different coarse bins satisfy the first test.
For same-bin seeds, the second test is necessary and sufficient on the
10,000-sample epoch circle.

Any other peak can then conflict with at most one member of `S`. During the
full greedy ordering, associate every seed that is suppressed with the earlier
retained peak that suppressed it. Disjoint neighborhoods make that association
injective. Retained seeds plus their distinct retained suppressors therefore
provide at least eight retained peaks whose scores are at least
`T = min(score(S))`. A cell may be discarded only when its certified upper
bound is strictly less than `T`; equality remains live because score ties use
canonical CFO and scan-order keys.

A proposed implementation must establish each seed as a real exact local peak
by evaluating its center and immediate epoch neighbors. A deterministic
partial pass may propose locations, but proposal scores alone cannot establish
the threshold. If eight guarded seeds cannot be established, the path must
fall back to the current complete interval computation.

## Saved-evidence check

Visit 301 exposes the coarse coordinates and scores. Both receiver rows retain
eight candidates, and all eight conflict neighborhoods are pairwise disjoint:

| receiver | threshold `T` | screened cells | possible peaks | exact repaired cells |
|---:|---:|---:|---:|---:|
| 0 | 0.18950116401959863 | 210000 | 40981 | 24 |
| 1 | 0.19075593345708686 | 210000 | 40895 | 24 |

The corrected 32-visit slice reports eight retained candidates in all 64
receiver windows. Its normalized visit receipts intentionally omit
`coarse_bin` and `coarse_score`, so they cannot prove the disjoint-neighborhood
guard. Refined/acquired CFO is not a substitute for the coarse bin. No rerun
was made to fill that diagnostic gap.

## Expected bound tightness

Each coarse cell is the mean of nonnegative normalized correlation
contributions. Before a contribution is evaluated, Cauchy-Schwarz gives the
trivial certified upper bound 1. If `r` of `S` contributions remain, the cell
upper bound is at least `r/S`, even when every completed contribution is zero
and numerical error is ignored. Consequently the visit-301 thresholds cannot
discard a cell before more than 81.0499% and 80.9244% of its contributions are
complete. Positive completed scores and outward numerical error bounds only
delay pruning. Contribution-progressive execution can therefore avoid less
than about 19% of correlation work on this evidence before accounting for its
bookkeeping and sparse-lane cost.

A tap-prefix bound is possible:

`(|z_prefix| + prefix_error + sqrt(E_rx_tail * E_ref_tail)) / sqrt(E_rx * E_ref)`.

It must include FP32 accumulation error, float template conversion error,
underflow, outward-rounded tail energies, and the existing final averaging
error. It also requires the full received-energy denominator before a lane can
be certified. With roughly uniform energy, its remaining-energy term has the
same approximately 81% progress limit at `T ~= 0.19`.

This mechanism could produce a bounded incremental improvement. The evidence
does not support it as a route from the measured roughly 419-times-dwell
runtime to real time.

## Bound evidence

- `native_glrt_reference.c`, SHA-256
  `7a6aedac1f7b1587c70a87a6ac054f0abc0e0d20d0f03c1a5f82531458355496`
- `kernel/private/full_search_reference.c`, SHA-256
  `efc89b2a155095edec35a8497cb1e1ac15b8f490f32edeaea7cd3cd12af0dcbb`
- visit-301 host output, SHA-256
  `6f04ff806502262dc2ae9c229477a0e348ba087ca49475a025ef351a3a4ebb14`
- corrected-32 summary, SHA-256
  `2ee25a4683f74a662aa6a032679d8ff59b79d96c461e48c28408f02040e8a16a`
