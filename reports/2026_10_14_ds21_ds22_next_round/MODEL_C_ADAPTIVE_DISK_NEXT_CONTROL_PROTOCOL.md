# Prospective all-start C disk releases: two calls

The frozen zero-fit screen completed in 40.329 seconds including preparation,
54 objective evaluations and no optimizer calls. It replayed all six original
C-all endpoints for before029, before037 and after029. These cohorts remain
separate from one another and from the retrospective mechanism qualification.

| Case | Independently stationary originals | Trigger | Original KKT | Analytic outward objective/km | 0.1 m finite difference |
|---|---:|---|---:|---:|---:|
| Before029 | 1/6 | None | — | — | — |
| Before037 | 4/6 | Start5, shape-all | .000204701 | -4.14653235 | -4.14653367 |
| After029 | 6/6 | Start3, shape-low | .000123216 | -50.90907253 | -50.90907442 |

Both triggering disks have radius 25 km within the prespecified tolerance.
Before029's sole accepted original is interior at radius 9.688956 km. The other
five nonstationary before029 endpoints do not qualify, even where their radial
derivatives are negative. This screen supplies no evidence that a disk release
can repair that case's large error.

Importantly, both triggers are losing original basins. Before037 trigger objective
31741.317921 exceeds its start3 incumbent 27741.020228 by 4000.297693.
After029 trigger objective 37493.647493 exceeds its start4 incumbent 32862.774268
by 4630.873224. Auditing only the original training winner would miss both.

The approved next operation calls the unchanged original fitted-c fitter exactly
twice: before037/start5 and after029/start3. Each call passes the exact saved
physical endpoint vector/nuisance, unchanged objective, bank and physical prior,
20-second/600-iteration cap, and one new 25 km disk centered on its own endpoint.
The original and recentered effective starts must agree, including the explicit
at-most-1e-8 timing-face margin. No recursive release, extra incumbent, relift,
clipping, candidate selection or retry is allowed. The original 18 endpoints and
their acceptance statuses remain available to the deterministic training selector.
Before029 is a zero-release control and retains its original selection.

This adds at most 40 optimizer seconds and two calls to the already incurred
18 original C-all calls. Upstream model/initialization/discovery costs are separate.
The whole operation includes preparation and independent replay within 120
seconds internally, TERM at 135 seconds, KILL at 140 seconds. Each optimizer
claim is exclusively created before invocation, and each return or exception has
a termination receipt. Unexpected failure leaves no completed scientific terminal.

Both outcomes and the training-selected endpoints must be sealed before reference
or held comparisons. Report each release's objective gap to its incumbent and
whether it remains a losing basin. No conclusion about all global search modes
can follow from just these two continuations.

Source screen namespace `local/model-c-adaptive-disk-next-screen-v1` has 966
frozen bindings. Terminal SHA256
`59dae12cdbcdc8054435d0602b7f3df0c0876a00d107144ec62c7417dd05788e`;
seal SHA256 `4a790a33bd911bb49d13b17124133893c707270703919418cc962a876ae960dd`.
The new runner is `tools/ds21_model_c_adaptive_disk_control.py`; its fresh output
namespace is `local/model-c-adaptive-disk-next-control-v1`.
