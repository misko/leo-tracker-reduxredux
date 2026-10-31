# Numerical optimizer audit

Final: 159 / 159 frozen DS26 fast cases have terminal receipts. No known-site coordinate or geographic error enters this audit.

Completed new-family trials: **153**; **145** centered trials have the same original TID, target identities/aliases, physical family prior, phase grid, starting point and round/evaluation budgets. **8** have no completed original same-TID trial and cannot demonstrate an optimizer-status improvement.

| Numerical status / integrity | Count |
|---|---:|
| Matched final role × c-arm fits | 580 |
| Original final ABNORMAL | 92 |
| Original ABNORMAL → centered success | 92 |
| Original success → treatment failure | 1 |
| All original failures → treatment success | 92 |
| Persistent optimizer failures | 0 |
| Centered optimizer rounds in completed helper receipts | 3530 |
| Counted evaluation-cap stops | 1 |
| Maximum physical evaluations in a round | 240 / 240 |
| Cap violations | 0 |
| Recorded helper/bootstrap hash mismatches | 0 |
| Worker-authoritative failed stages | 7 |
| Worker-authoritative timeouts (subset of failed) | 7 |
| Exceptions recorded by completed bootstrap receipts | 0 |
| Started changed stages missing valid helper receipt | 7 |
| Unstarted stages omitted by remaining-budget check | 0 |
| Case-level replay failures | 0 |
| Original source unavailable; no replay/comparison | 11 |
| Original/treatment scientific-input mismatches | 0 |
| Unexpected optimizer-round counts | 0 |

A fit is one role (`control` or `new_family`) × one c arm, using its final phase round. Numeric-round totals also include centered joint-position stages, but only where a completed helper receipt exists. A killed child may never flush that receipt: zero recorded bootstrap exceptions or hash mismatches does not mean zero worker timeouts, nor does it certify missing receipts. Worker `decision.stages` and per-stage receipts are authoritative for execution failures. Status success does not override RF, phase, incumbent, owner or quadrature gates. All comparisons use the joint 30 s/centered numerical treatment; this audit does not isolate the gradient effect from the reference change.

Detailed per-fit transitions, unmatched trials, evaluation counts, exceptions and source hashes are in the adjacent JSON. Initial-start coordinates are not used to rank fits.
