# Synthetic numerical stress and cost

No recordings, optimizer or production model were run. All 14 synthetic tests
pass under production Python 3.14. The persistence parameter values here exercise
numerics; none is selected for an actual recording experiment.

## A real cancellation issue, now corrected

When clutter probability is almost zero, successive categorical priors are equal
and `rho=nextafter(1,0)`, computing `Z=1-sum(h)` loses substantial relative
precision. For synthetic priors `[1e-12, .3, .7-1e-12]`, `[1e-20, .3, .7]` and
`[0, .1, .2, .7]`, the original redraw vector's sum differed from one by roughly
`3.3e-5`, `0.25` and `0.31`, respectively. The assertion failed explicitly;
there was no silent clipping or numerical fallback.

The prototype now computes the mathematically identical quantity
`Z=sum(pi_current-h)` and divides that same nonnegative residual-mass vector
by its sum. Forward reset mass likewise uses
`sum((1-s)*alpha_previous)` instead of `1-sum(s*alpha_previous)`. This avoids
cancellation without changing the transition model or adding a floor. Regression
tests verify stochastic rows and preservation of prescribed categorical priors.
The immutable iteration108 kernel remains unchanged.

Other stress cases cover subnormal prior mass (`1e-320`), disjoint satellite
support, complete disappearance/reappearance, all-clutter observations, almost-unit
retention, 1,500-row sequences, explicit segment boundaries and agreement between
packed versus separately evaluated segment gradients. Gaussian tail underflow to
zero follows the existing narrow wrapped likelihood convention; divide-by-zero,
overflow and invalid floating operations are raised in the extreme tests.

## Cost measured on synthetic arrays

Each case used three timed calls after one warm-up, one separate traced-memory
call, single-thread numerical libraries and the production Python environment.
Measurements were `50*sin(row/30)` Hz, predictions added `linspace(-250,250,K)` Hz,
all satellites visible, resets every 100 rows, and synthetic `rho=0.6`.
These are host prototype costs, not embedded performance or position-fit runtimes.

| Rows N | Satellites K | Median call | Traced peak bytes | Returned array bytes |
|---:|---:|---:|---:|---:|
| 300 | 16 | 13.57 ms | 532,258 | 242,400 |
| 1,200 | 16 | 54.23 ms | 2,116,390 | 969,600 |
| 1,200 | 64 | 58.69 ms | 7,617,394 | 3,734,400 |

Exact observations are retained in [synthetic-cost.json](synthetic-cost.json).
Python per-row checks dominate these small timings; no optimization or compiled
implementation claim follows from the weak observed K dependence.

The current diagnostic return contains four `N*(K+1)` state arrays, two `N*K`
arrays and one N-vector of float64, totaling **`N*(48*K+40)` bytes**. Additional
working arrays include categorical priors, emissions, backward messages and the
independent likelihood audit; peak memory is O(NK), not just the returned size.
Inputs and allocator/process overhead are not fully characterized by tracemalloc.

A future production-oriented implementation could process separate segments and
release diagnostics, making additional recursion storage O(LK) for maximum segment
length L, plus any required full output. That bounded-memory version is not
implemented or benchmarked here. The prototype deliberately preserves diagnostic
arrays and retains the independent likelihood computation for verification.
