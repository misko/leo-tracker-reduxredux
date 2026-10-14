# Matched 34-recording development comparison

The user authorized parallel use of all cores on 2026-10-14 to complete the
before/after A/B/C position-error histograms. This supersedes the earlier
single-science-process scheduling restriction, not the numerical budgets.

The population is the original membership's 34 fast, eight-channel development
recordings. The 20 locked recordings remain separate until an algorithm and
selection rule are frozen. All arms fit c. Before uses the original generic
discovery and initialization; after uses the prespecified dense discovery
coverage control and its qualified downstream adapters, as on 009 and 013.
This does not substitute the newer 039 selector or relative-phase experiments.

Completed generic results are reused. Six older legacy cases without compatible
generic parents require the generic chain; these are not retries of failed
generic runs. Existing failures and archives remain unchanged. Each arm retains
the same observations, partition, priors, 100 discovery points, six proposals,
and original per-fit time/iteration limits. Candidate pools and discovery
locations may differ by design. No reference error selects starts or models.

Execution uses explicit bounded waves with at most 24 subprocesses, one BLAS
thread per subprocess and no simultaneous writes to a scientific namespace.
Every wave has an immutable job manifest, separate logs and launch/termination
records outside scientific directories. Each command keeps the original
internal limit and external TERM/KILL grace. A clean checkpoint requires a new
explicit numbered invocation; failed or orphan runs are never retried.
Existing numerical source closures are not edited. No new RF collection occurs.

The host has 24 physical cores (one thread per core) and approximately 100 GiB
available RAM at launch. Other host services remain running. CPU load, memory,
checkpoint rate and fit failures are monitored; concurrency can be reduced if
contention compromises the unchanged wall-clock budgets. Historical serial
results versus parallel results have a scheduling limitation, which must be
reported with runtime and stationarity evidence rather than hidden.

All twelve model outcomes must be sealed before evaluation for each case/arm.
Histograms use matching recording membership for A/B/C and before/after;
missing or failed runs remain explicit misses rather than being dropped.
Report completed/eligible counts, median, p90, maximum, and fraction below
0.5 km with the distributions. A partial chart is labelled partial. Full DS21
accuracy and the 0.5 km target are not established by this launch.

## Preparation scheduling qualification

Wave 001 launched 24 case preparations. Twelve completed and twelve hit the
unchanged 60-second training-preparation deadline (`SliceHardStop`), before
any position fits or candidate discovery. The failed cases are 007, 029, 031,
033, 039, 043, 045, 055, 057, 061, 071 and 077. These original namespaces and
failure receipts remain immutable. This wave is a failed scheduling trial,
not a position-accuracy measurement.

Further preparation waves use at most six workers. To complete the intended
population, a separately recorded preparation-only recovery is permitted for
these twelve cases, in new per-label initialization namespaces. An explicit
mapping must bind each original failed preparation to its new namespace. The
planner permits this only for a saved `SliceHardStop`, with no completed case
protocol, discovery or downstream stages. This exception changes scheduling
only: preprocessing, training partition, original numerical sources and limits
remain identical. It does not authorize retrying any discovery or position fit.
The final report must retain the initial scheduling failures and distinguish
recovered preparation from first-attempt completion.
