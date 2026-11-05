# ALGO07v3: exact factor reuse experiment and 16/17 historical audits

2026-11-05. External experiment; the numerical runtime and production remain
unchanged. Complete-pipeline speedup is not established by this experiment.

The factorization-reuse candidate matches **all 6,772 likelihood calls** in a
complete native DS26-0002 run. Every field's dtype, shape and bytes match. The
complete scientific snapshot, both c arms, all 179 grid locations, recorded
paths and eight PNG hashes also match the previous native qualification.

![Interleaved likelihood timings](component-runtime.png)

| Measurement | Current owned kernel | Factor reuse candidate |
| --- | ---: | ---: |
| Summed likelihood time | 163.053 s | 159.250 s |
| Exact likelihood calls | 6,772 | 6,772 |
| Observed component saving | — | **3.803 s / 2.33%** |

The diagnostic executes both kernels on every input, alternating their order,
and returns the candidate result only after exact comparison. Any difference
aborts outside ordinary scientific exception handling. The diagnostic's
**536.354 s** total includes doubled likelihood work and comparisons, and is
not a normal pipeline runtime. The modest component saving does not justify
enabling the candidate without a complete-path measurement. It is not evidence
of the cumulative 10× target or a dataset-wide gain.

The existing scatter assembly remains unchanged. This candidate factors the
same Cholesky root once with LAPACK DGETRF and reuses it for the separate vector
and identity-matrix DGETRS solves. It retains the original transpose solve,
right-hand-side separation, priors, precision iterations and stopping rules.
Unlike the earlier failed combined-right-hand-side prototype, it does not change
the solve's right-hand-side shape. The previous eight-call experiment used the
older pre-scatter implementation; this run tests the current owned kernel.

The [probe](../../tools/probe_algo07v3_factor_reuse.py), [receipt](probe.json),
[native input/source bindings](native-receipt.json) and
[summary](summary.json) record the result. The raw native snapshot SHA-256 is
`4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68`.
The probe ran on CPU 0 with one BLAS thread and a 1,200-second outer bound.
The native qualification driver blocks legacy access. This diagnostic itself is
not the separate mount/network namespace isolation test.

## Complete-path comparison in progress

After the exact native probe completed, two fresh isolated CLI runs were launched
in baseline/candidate order. Both use CPUs 0–2, one BLAS thread, the same native
GLRT, causal archive, search region, validation budgets and presentation-only
evaluation reference. Only the kernel module differs, mounted read-only inside
a private namespace. The checkout and production installation are unchanged.
Each run includes scientific persistence, all PNGs and atomic publication.

[Predeclared pair plan](paired-plan.json), [isolated runner](run_kernel.sh).
Evidence directory:
`/srv/bulk/leo-dev/algo07v3-factor-reuse-20261105/paired`.
This report records the launched comparison, not completed paired results.
Host load rose above 30 runnable tasks during the baseline. Neither production
workers nor capture settings were changed. Even successful exact runs may leave
the small total speed effect unresolved under this contention.

## Historical audit: residual preparation now checked

The existing fresh published native result now matches **16 of 17 historical
audit sections**, adding the complete residual-recovery preparation for the
selected-one-family/no-gap branch. The comparison checks all fragments, selected
and eligible targets, preflight corrected measurements in both arms, ownership
maps, replay checks and the complete selected family's physical prior.

The original preflight carries extra preparation metadata. Before mapping it to
the compact native receipt, the verifier checks an exact known field set,
screen/search policy constants, epoch/collection causal cutoffs, the input
binding, and the original bank/latest-TLE/repaired-previous-TLE file hashes in
the exported descriptor. Unknown fields, changed bytes, altered policies and
future epochs fail. The selected-family protocol is bound through its original
source receipt. Its family prior is compared in full; it is not reconstructed
from the candidate. Only the original preflight elapsed-time field is excluded
from scientific comparison. Other incumbent/gap branches require their own
mappings and are rejected by this one.

The [first metadata-mismatch result](historical-before-metadata-mapping.json)
is retained. The [completed comparison](historical-comparison.json) has no
differing checked values. `numerical_recovery` is the remaining section.
Cross-stage metadata semantics, ordinary production admission, accepted-branch
coverage and the full DS26 population remain unqualified. The historical check
uses the prior completed owned run; it is not a substitute for comparing the
new full-path timing pair.

## Tests and remaining work

The broad suite passed **743 tests**. A subsequent focused comparator run passed
**57 tests**, including seven additional file/policy/cutoff tests; these runs
cover **750 distinct test cases**. No fixture was changed. The kernel probe
tests include zero/nonzero feature widths, sparse C/Fortran arrays, preserved
invalid-input errors and mismatch propagation that cannot become a fit rejection.
The comparator tests reject changed owners, priors, replay values, target sets,
unknown fields and unsupported branches. [Broad results](tests.xml),
[focused results](comparator-tests.xml).

Next: finish the complete pair, compare its full scientific archive and PNGs,
and decide whether the observed total benefit warrants integration. Regardless
of that outcome, the full DS26 denominator, final historical mapping, metadata,
production deadlines and cumulative 10× target remain open. No deployment.

`render.py --root /srv/bulk/leo-dev/algo07v3-factor-reuse-20261105` checks input and
source bindings, the complete native snapshot, all PNGs, the historical audit
and test results before rendering this figure.
