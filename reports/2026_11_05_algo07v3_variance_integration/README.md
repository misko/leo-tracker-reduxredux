# ALGO07v3: bounded variance batching integrated in development

2026-11-05. Development CLI change; no production deployment.

The owned [hierarchical likelihood](../../src/leo/analysis/localization_v3/hierarchical.py)
now batches independent equal-width variance reductions, preserving each group's
arithmetic and restoring group order before updating precisions. Singleton
groups and stacked matrix batches above 1 MiB retain the original reductions.
This is a per-stacked-tensor limit, not a whole-job memory bound. Priors, masks,
budgets, convergence tests, catalogue and association rules are unchanged.

The complete owned module is byte-identical to the externally qualified
candidate: SHA-256 `3b02974c822ef2504422dcdb85f10d16198ec8df2ef35936119e42a97877dab2`.
Its source was tested in private mount namespaces through both calibration
arms, all eight PNGs, grid/path values and atomic publication on two native scans:

| Native case | Branch | Complete output comparison |
| --- | --- | --- |
| DS26-0002 | Retained incumbent | Exact in two fresh baseline/candidate pairs |
| DS26-0066 | Accepted guarded reassociation | Exact against the completed integrated reference |

DS26-0066 keeps **2,770 points (70.5373%), 89 components and 20 satellites** in
each arm. Its candidate takes 855.082 s in this correctness run; the reused
reference took 761.514 s earlier. These are not a matched timing experiment.
[Complete comparison](../2026_11_05_algo07v3_native_canary/variance-ds26-0066/comparison.json),
[terminal receipt](../2026_11_05_algo07v3_native_canary/variance-ds26-0066/supervisor.json).

**833 component tests pass**, including scientific-oracle regressions, both-arm
fitting, contracts, storage, cancellation, publication and external verification
tools. The 76-test focused run also passes; it overlaps the broad suite and must
not be added to that count. [Broad tests](tests.xml), [test command](test-command.json),
[focused tests](focused-tests.xml).

The old kernel is frozen in an [external numerical oracle](../../tools/algo07v3_prevariance_hierarchical_oracle.py).
The probe and benchmark now use that reference, so comparisons do not become
new-code-versus-itself after integration. Runtime code never imports the oracle.
Existing older golden fixtures remain unchanged. The test chain checks that
the old solver matches its qualified prototype and the owned solver matches
the separately qualified variance prototype.

A fresh direct owned CLI execution has also **completed exactly** with the older
installations, bulk results and reports hidden, input bundle read-only and
networking isolated. It matches the completed pre-variance reference in both
calibration arms, all scientific evidence, all eight PNG bytes, grid/path data and
public fields. Exactly the declared hierarchical module changes; no runtime
modules are added. Its observed time is **243.059 s**. This is a fresh integration
check against a reused reference, not another matched timing experiment.
[Frozen plan](plan.json), [complete comparison](comparison.json),
[terminal receipt](supervisor.json), [isolation checks](isolation.json),
[summary](summary.json).

## Performance evidence and limits

The native alternating kernel probe saves 11.17% of kernel time across 6,772
exact calls. The first full pair is **43.63% slower**, with substantial host
interference and slower unchanged stages. The reverse-order repeat has
**244.383 → 234.399 s wall time (4.09% lower)** and
**271.20 → 259.14 s process CPU (4.45% lower)**, with 3.24% more peak reported RSS.
Both observations are retained. This supports a modest implementation improvement,
not a population-wide or cumulative speedup claim.
[Full timing evidence](../2026_11_05_algo07v3_native_canary/README.md).

The independent-family-arm concurrency prototype is not included in this
integration. Full DS26, ordinary production admission/deadlines, complete
historical metadata qualification and the cumulative tenfold target remain open.
Raw integration evidence: `/srv/bulk/leo-dev/algo07v3-variance-integrated-20261105`.
Earlier external variance reports reproduce at commit `fa1d31312`; their original
driver bytes are also preserved in that evidence directory.
