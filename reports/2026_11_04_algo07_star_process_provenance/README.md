# ALGO07*: verify process provenance before allowing operational differences

The first complete production-path/ALGO07* smoke pair now passes its process
provenance comparison. This is one qualification checkpoint, not a full
scientific-equivalence or performance claim. Production and all numerical
workers remain unchanged.

The case is DS26-0002, recording
`fast8-auto-20261024-152202-b7823fab-1-upper`. Its fresh executions and final
scientific comparison are documented in the
[full smoke report](../2026_11_04_algo07_star_full_smoke/README.md).

| Process evidence | Production path | ALGO07* | Comparison |
| --- | ---: | ---: | --- |
| Original and copied receipt groups | 42 | 42 | All match |
| Receipt files, including copies | 279 | 279 | All audited |
| Recorded process/supervisor identities | 27 | 27 | Roles verified from recorded work and ancestry |
| Denied reads | 0 | 0 | Required in every receipt |
| Missing child receipts | 0 | 0 | Launch counts checked for every process |

The [machine-readable comparison](comparison.json) contains the per-group
digests and input/model/job bindings. Every exported file is rehashed before
the audit; the comparator does not trust an unverified file inventory.

## Why PID replacement needs more than a filename filter

Later recovery workers read earlier process receipts while validating exported
evidence. Therefore their own read sets include paths ending in different PIDs
between two fresh executions. The first conservative audit left 16 of 42 groups
unequal despite matching process counts and interpreter launches.

The new comparator resolves each such path through the exported descriptor's
original source location, validates the referenced receipt group, and identifies
the target by its verified role and work digest. It retains the read set and
parent/child structure. The source guard records a sorted unique set of reads;
the comparator checks that convention and re-sorts after mapping PID paths.
It does not treat the list as chronological read events.

Copied receipts can have relocated input paths, so each copy's group is audited
independently. Numeric PIDs are not assumed to identify the same work across
reference and candidate executions. Unknown receipt references, missing children,
duplicate identities, denied reads, cycles and normalization collisions fail the
audit. A changed earlier read changes the downstream work digest as well.

This establishes equality of recorded process structure and read evidence.
It does not by itself establish equality of the scientific content at those
paths, nor does a post-run hash establish the bytes at every historical read.
The frozen runtime/input checks, scientific-value comparator and bound hash-link
checks remain separate requirements.

## Implementation and tests

- `tools/algo07_star_receipts.py` validates process forests and dependent receipts.
- `tools/compare_algo07_star_receipts.py` checks complete exported inventories,
  stage bindings and paired process evidence.
- Component tests cover renamed PIDs, nested references, missing children,
  altered read evidence, cycles, denied-read schema, duplicate paths, corrupt
  exported bytes and different native-input bindings. Passing provenance must
  leave scientific/artifact qualification flags false.

The focused ALGO07* suite passes 45 tests; lint passes for the new modules and
tests. The real smoke pair additionally passes all 42 process comparisons.
This check runs over existing exports; no new inference or RF acquisition was
performed for this report.

## Remaining gates and optimization order

The [execution plan](../../docs/operations/algo07-star-plan.md) now includes a
checkpoint table. Full intermediate scientific/hash-link validation is still
outstanding. The publication discrepancy is also retained: the reference grid
completed 179 locations while the candidate completed 96 under the same
30-second budget, with equal scores at their shared locations. Seven PNGs match;
the position PNG does not. This audit does not waive that failure.

After the zero-change coordinator qualifies, evaluate one transport improvement
at a time, then exact reuse of repeated calculations. The observed 1.5 GB of
repeated logical content is an opportunity, not a measured speedup. Each accepted
iteration requires fresh paired DS26 results for both calibration arms and
controlled sequential timing. The full DS26 comparison remains outstanding;
one successful endpoint pair is insufficient for promotion.
