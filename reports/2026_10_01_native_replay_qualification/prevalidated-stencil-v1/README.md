# Prevalidated immutable-session interpolation

The private stencil fast path avoids repeating snapshot/pointer/index checks
only when the scorer has constructed the stencil itself and owns an explicitly
immutable, validated orbit session. Public/ordinary calls retain all checks.
The interpolation arithmetic and output-finiteness checks remain unchanged.
Mutable or mismatched snapshots fall back to the checked path; allocation
fallback still uses the generic interpolator. No persisted contract changes.

Both complete host traces (fresh native tracks and published server tracks)
remain exact. Component tests exercise stencil boundary equality, nonfinite
output, immutable binding/unbinding and changed metadata. ARM core, stencil
and immutable-session tests passed. ASan/UBSan passed with the changed scorer
instrumented (the unchanged orbit/search/vendor objects were not instrumented).

Fresh PGO training used the same four sites as the previous build. Four trials
on the 16 disjoint evaluation sites ran control/optimized/optimized/control;
all scores were identical. Mean CPU fell 1.55%, from 12.423166 to 12.231006 s.
`protocol.json`, source snapshots, source hashes, profile data, build log,
payload hashes and unit receipts preserve provenance.

Full ARM qualification is in `../regional-arm-prevalidated-v1/`. All 400 search
points and full selected-site associations equal the preceding ARM results
exactly. The independent host comparison passes the predeclared 1e-9 Hz bound
(largest intermediate delta 5.684341886080801e-13 Hz; selected score exact).
Search used 158.581110 wall / 298.280391 CPU seconds, peak RSS 79,748 KiB;
full associations used 2.166501 wall / 3.278568 CPU seconds. The search still
exhausts its 400-point budget; no global convergence is claimed.

The updated separate-stage sum is about 597 CPU seconds per scan. That small
nominal reserve is not a concurrent or sustained result. Earlier overlap
failures remain open until the updated build is tested under contention.
