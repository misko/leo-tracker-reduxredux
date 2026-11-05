# ALGO07v3: independent family-arm concurrency prototype

2026-11-05. External experiment; no runtime integration or deployment.

The family policy currently fits c=0 and fitted-c sequentially for each curved
gate round, then fits its two predictive-linear alternatives sequentially. The
arms within each pair use the same frozen observations and priors. A pair's
shared rejection decision must finish before the next round or linear proposal.

The [prototype](../../tools/probe_algo07v3_parallel_family.py) replaces only
those two independent pair evaluations with the existing bounded process
adapter. It consumes results in c0/fitted-c order. Masks, rejection rounds,
linear-entry selection, convergence budgets, priors and paired adoption remain
unchanged. It does not parallelize dependent decisions or numerical-policy
receipts. Child failures abort the stage rather than becoming rejected science.

Three [tests](tests.xml) pass: exact numerical records and rejection/mask history
on whole and masked synthetic observations, plus failure propagation when one
child fails. An initial test mistakenly used the flat likelihood comparator on
a nested tuple; the corrected test uses the established recursive scientific
fingerprint, including array dtype/shape/bytes and exact floating representations.
The failed test receipt is retained externally.

A bounded native DS26-0002 probe is running on CPUs 4–6, one BLAS thread per
process. It copies the incoming context outside timing so reference and
candidate start with the same cache state. It compares the complete family
policy outputs, then compares the full native scientific snapshot and all eight
PNG bytes after inference. No reference answer enters candidate inference.
This diagnostic computes both methods and is not normal full-pipeline latency.
It records parent and waited-for-child CPU time separately for the stage.

The larger DS26-0066 variance correctness experiment runs separately on CPUs
0–2. Both share the host, so any timing interpretation must retain that context.
No speedup or native equivalence is claimed before the probe finishes. Even a
successful two-arm speedup addresses only this stage, not the cumulative
tenfold target or full DS26 qualification.

[Source/input plan](plan.json). Raw evidence:
`/srv/bulk/leo-dev/algo07v3-parallel-family-20261105`.
