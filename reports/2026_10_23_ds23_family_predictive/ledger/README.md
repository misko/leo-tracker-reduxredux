# Physical-ID rejection ledger prototype

The pure `coverage_with_ledger` wrapper applies explicit rejected native physical observation IDs to an unchanged coverage port. It refuses any rejection overlapping original parent accepted IDs. After ordinary coverage returns, it removes every whole association record intersecting the ledger and rebuilds accepted IDs, associated count, percent and associated-track count from the remaining compatible records. It does not merely decrement a total.

Whole-record removal preserves the meaning of stored whole-track quality statistics: slicing a record would leave statistics that do not certify the retained subset. Any collateral removal of protected parent IDs raises an error. Collateral nonprotected removal is possible for a partially intersecting record and should be audited by callers; it is absent in these replays. Input ownership/count inconsistencies and duplicate physical ownership raise errors. A second application produces the identical coverage object. Input objects are deep-copy preserved.

`active_curved_points` and `predictive_points` remain unchanged because they describe fitting evidence, not postfit associations. Fits, their gates, observations and global coverage helper remain untouched. This is a research prototype, not a production policy or a claim that excluded observations are physically invalid.

The frozen protocol hashes the two saved source results and wrapper/runner source before replay. This replay applies the wrapper to the previous saved coverage objects, without new position fits, RF collection, catalogue access or GPS use. The earlier capsule separately established exact coverage-helper replay; this task does not repeat its numerical pipeline.

| Case | Arm | Prior coverage IDs | Ledger coverage IDs | Whole records removed |
| --- | --- | ---: | ---: | ---: |
| 0232 | c=0 | 2088 | 2088 | 0 |
| 0232 | fitted c | 2097 | 2088 | 1 |
| 0365 | c=0 | 2194 | 2194 | 0 |
| 0365 | fitted c | 2194 | 2194 | 0 |

All nine re-admitted 0232 fitted-c IDs are removed, with zero collateral IDs and every parent accepted ID retained. Complete coherent coverage objects are in `results.json`. Five owned tests pass: protected overlap, consistent whole-record accounting/idempotence/wrapper behavior, collateral protection, duplicate/stale input rejection, and saved-result parity. Replay runs in milliseconds using only the standard library.

From the repository root, reproduce using `.venv/bin/python -B <this>/run_replay.py`, then `.venv/bin/python -B <this>/test_coverage_ledger.py`, with `PYTHONDONTWRITEBYTECODE=1`. The existing protocol must match, and its archived input files must remain at their recorded paths. No production adoption or publication is performed.
