# ALGO07*: DS26-0170 fails because the discovery deadline omits three targets

The optimized DS26-0170 candidate finishes inference but **fails strict scientific
qualification**. Its first differing process group is ALGO03 discovery: the
reference evaluates eight targets, while the candidate crosses the existing
600-second admission limit after the fifth and skips three. The terminal-read
optimization is only installed at the final ALGO07 storage boundary; the
divergence occurs earlier, in the unchanged ALGO03 worker.

![Recorded discovery work and admission threshold](discovery-boundary.png)

Both runs preserve the original 1,200-second stage budgets. ALGO03 records the
same 1,168-second recovery allowance after preparation/reserve, and its discovery
admission limit is `min(600, 0.7 * recovery_allowance)`, or 600 seconds. The worker
checks this before starting each target; an already admitted target can finish
after the limit. It does not interrupt an inclusion solely because discovery
admission has closed.

| Evidence after the first five targets | Reference | Candidate |
| --- | ---: | ---: |
| Sum of recorded child-stage durations | 380.909484 s | 635.631133 s |
| ALGO03 process receipts | 16 | 13 |
| Additional targets annotated | 3 | 0 |
| Total available targets considered for admission | 8 | 8 |

These durations exclude Python bookkeeping. Admission uses actual elapsed wall
time, so the sums locate the boundary but are not an exact reconstruction of
every clock read. The numerical workers are pinned and unchanged. These are
shared-host executions at different times, not a controlled timing trial; the
duration difference cannot be attributed to a particular host resource from
these receipts alone.

| Omitted target | GLRT points | Reference outcome | Candidate outcome |
| --- | ---: | --- | --- |
| `a6b06e9895ba90815a29` | 35 | `unstable_identity` | `discovery_budget_exhausted` |
| `a5d11aa5f4141cb314d1` | 32 | `ambiguous_identity` | `discovery_budget_exhausted` |
| `3f26523f1eb74e47f7ec` | 31 | `unstable_identity` | `discovery_budget_exhausted` |

The first five attempt statuses match. The 99-point first target qualifies on
both paths; the later 37-point fifth target is rejected on both. The reference
also rejects the three extra targets. A separate, limited outcome diagnostic
rehashes the complete exports, validates all six public terminals per path, and
then compares the complete selected public result, full owner dictionaries and
all six stage decision labels exactly. All three projections are equal:

| Final output, identical on both paths | c=0 | Fitted-c |
| --- | --- | --- |
| Associated observation IDs and satellite assignments | 3,353 | 3,353 |
| Latitude | 37.863571924067934 | 37.86348259169218 |
| Longitude | −122.48040045343036 | −122.48036056618852 |

This explains why the final outcome agrees in this case. It does **not** establish
that omitted targets are always harmless. The strict comparator still fails,
and this diagnostic is not an alternate acceptance gate or a numerical tolerance.
The missing work and original failure are retained.

## Consequence for optimization and qualification

This repeats the discovery-boundary mechanism previously observed in
[DS26-0102](../2026_11_04_algo07_star_deadline_divergence/README.md). ALGO07 includes
time-dependent work admission, so unchanged scientific code alone cannot
guarantee identical intermediate work under different wall-clock conditions.
Replacing the time limit with a target quota would be a policy change and is not
part of the current candidate.

Continue the predeclared DS26 comparisons and record deadline-sensitive failures
separately. The next diagnostic for this class is a matched logical-cancellation
replay with actual numerical children, keeping the ordinary wall-clock failures
visible. Existing worker control-flow tests cover the admission boundary and
preservation of earlier accepted recovery using explicitly stubbed children;
they do not substitute for that numerical replay or full-cohort qualification.

The optimized adapter remains at two full scientific passes, DS26-0002 and
DS26-0267, plus this failed case. The full population is still 159 fast members,
158 with available native inputs. No production change or end-to-end speedup is
claimed.

## Optimized DS26-0267 publication follow-up

The first independent ordinary-clock publication pair for this optimized case
also finishes. Both paths produce all eight PNGs; seven are byte-identical. The
reference grid admits 66/179 locations and the candidate 65/179. Every shared
paired score is exact, published scientific values have zero differences, and
the path-sidecar difference is solely its position-PNG hash binding. Full
artifact parity remains **false** because both grids are incomplete.

Both retain 4,028 associated points out of 5,154 and identical evaluation errors
of 451.017666 m (c=0) and 540.373645 m (fitted-c). Evaluation coordinates enter
presentation only. The frozen renderer's 2,149 files verified before and after.
This is a first comparison for the optimized case, not a rerender-until-pass
attempt, and its independently reused scientific reference does not qualify a
paired performance claim.

Evidence: [strict failure](verification.json), [process comparison](process-difference.json),
[limited diagnostic summary](diagnostic-summary.json),
[publication comparison](ds26-0267-publication.json), [hash bindings](evidence.json).
The saved diagnostic and publication runners preserve the executed procedures.

## DS26-0162: a separate accounting representation issue

The unchanged-worker DS26-0162 pair has identical process provenance and zero
hash-link errors. Its initial comparison reports 326 differences, all integer
versus floating-point types at `budget_seconds`: copies of two completed ALGO03
child receipts propagated through 169 files. All other scientific values in
7,584 JSON documents, 608 binary/text files and 366 process receipts compare
exactly. The original failed comparison remains saved.

| Completed child | Reference timeout | Candidate timeout | Reference elapsed | Candidate elapsed |
| --- | ---: | ---: | ---: | ---: |
| Target 7 audit | 552.181124 s (float) | 600 s (int) | 13.261421 s | 18.028681 s |
| Target 7 retry | 538.758938 s (float) | 600 s (int) | 184.842375 s | 176.160735 s |

The pinned producer writes `min(600, remaining)`. Python returns the integer
cap when it wins and the floating-point remaining duration otherwise. The
classifier already accounts for differing completed subprocess wall budgets,
but it previously rejected every type difference before reaching that rule.

A narrow new accounting class accepts only this known complete receipt shape,
matching nonempty commands and stage names, successful integer return codes,
elapsed durations below each recorded limit, and exactly an integer cap of 600
versus a positive finite float below 600. Other numeric type changes, solver
budgets, unknown schemas, changed commands, failed work and invalid durations
remain differences. A malformed string budget also now fails classification
instead of raising an incidental comparison exception.

The comparator, receipt, publication, CLI and deadline regression selection has
**107 passing tests**. Inference and frozen numerical code are unchanged. The
original DS26-0162 exports are being rehashed and rechecked under this explicit
accounting review; a pass is not claimed before that check completes. This rule
does not affect DS26-0170 or DS26-0102, whose different admitted work fails before
field accounting is reached.
