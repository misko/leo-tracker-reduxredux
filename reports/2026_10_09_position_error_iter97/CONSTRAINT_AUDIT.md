# Independent audit: the corrected postfit sits on one satellite timing face

This audit uses only the saved iteration97 vector/gradient, the deterministic
zero-sum basis and constraint algebra. No objective evaluation or new fit ran.

The active physical constraint is **satellite100185's total timing shift at the
upper+20-second bound**. It is row15 (zero-based) in the17-satellite bootstrap bank,
not the common timing coefficient's separate±10-second bound. Its total shift is
`tau + B[15] @ relative = 19.999999999982474s`, leaving
`1.752553657752287e-11s` slack. All other satellite timing shifts are interior
(approximately−4.560s to10.383s). The ephemeris coverage extends beyond±20s; this
is the explicit physical timing limit, rather than exhausted interpolation
coverage. Position is fixed and removed from the free coordinates. Receiver
affine slopes, static c and the common timing coefficient are interior.

## KKT projection is valid

[The physical problem](../../src/leo/analysis/hard60_bounded_fit.py) constructs
`h_upper(v)=20−M@v`, where `M[:,7]=1` and `M[:,8:]=B`. For constraints `h>=0`,
the minimization KKT equation is `g−A*lambda=0`, with inward constraint normals
`A=grad(h)` and nonnegative multipliers. The existing NNLS projection uses that
sign and the same scaled free coordinates. [projected_gradient](../2026_10_09_position_error_iter94/coordinate_polish.py)
matches the production problem's stationarity calculation.

At this state there is one active normal, `−M[15]`. Recomputing the projection
from the saved gradient yields multiplier**1214.95048069569**, residual maximum
**0.016400970241193136** at vector coordinate22, and normal/residual inner product
approximately`−2.97e-13`. The residual reproduces the stored stationarity exactly.
The large raw timing derivatives are mostly the active-face normal component;
they must not be mistaken for unconstrained failure or removed by changing the
qualification threshold. A real tangential derivative remains above0.001.

## Why scalar coordinate polish cannot follow that derivative

Coordinate22 is relative timing basis14 (zero-based), whose coefficient in the
active satellite shift is`−0.9682458365518541`. Decreasing this coefficient alone
increases the already-maximal satellite shift and becomes infeasible. Increasing
it moves inward but is uphill: its saved raw gradient is**1176.387145520517**.
The saved+1e-5 probe is feasible and raises the objective by approximately0.011777;
the−1e-5 probe and negative Newton proposals are infeasible. The scalar polish
correctly rejects those proposals, but that search cannot represent the coupled
descent direction indicated by the projected gradient.

For example, the exact affine tangent direction

```text
d[22] = −1
d[7]  = −0.9682458365518541
all other components = 0
```

keeps the active total shift unchanged: `M[15]@d=0`. From the saved raw gradient,
`g@d=−0.0317219975008811`, a strict first-order descent direction. A sufficiently
small step also remains within the other interior bounds. This is an algebraic
candidate direction, not a measured objective decrease or qualification result.
The physical common timing and relative timing must move together.

A more general prototype can use the negative scaled projected gradient or a
null-space basis of active positive-multiplier normals, then evaluate curvature
along the entire coupled direction. For other active faces with zero multiplier,
retain the tangent-cone inequality instead of requiring equality unnecessarily.
Check every original bound and disk after transformation back to physical
coordinates, retain the unchanged independent stationarity gate and fixed score
ceiling, and use feasible one-sided probes if a two-sided direction is unavailable.
Do not use a raw single-coordinate gradient to predict a projected-direction step.

## Scope and provenance

The timing basis is [zero_sum_basis](../../src/leo/analysis/regional_position_score.py);
the scalar curvature search is [iteration96](../2026_10_09_position_error_iter96/curvature_polish.py).
The saved vector and gradient are in [result.json](result.json). Bootstrap bank
indices are preserved in [iteration93 checkpoint receipt](../2026_10_09_position_error_iter93/verified-checkpoints.json);
their bank-number mapping is in its prefit-input-verification receipt. Selection
uses the existing ordinary score-ranked hypothesis; no reference error identifies
the active face or proposed direction.

This explains an algorithmic limitation of iteration97's scalar continuation.
It does not prove the objective's higher-order behavior, successful calibration,
a recovered operational region or better final localization. Iteration99 tests
the tangent correction; iteration98 remains a conditional downstream continuation.
Production and closed reserves remain unchanged.
