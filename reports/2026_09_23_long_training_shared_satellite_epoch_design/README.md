# First-16 TRAIN satellite recurrence and epoch-nuisance design

The fixed 16-TRAIN Sacramento assignments contain 1,130 matched tracks with
17,358 duration weights across 312 candidate IDs. Only one candidate occurs in
two distinct scans: four tracks and 43 weights (0.2477%). No candidate occurs
in three scans. These assignments are training-selected labels, not satellite
truth.

That recurrence provides little leverage for separating persistent satellite
effects from effects common to a scan. A future model could use a satellite-side epoch term `eta_k` and one
combined scan timing term `u_s`, predicting at `t + u_s + eta_k`. It must not
separately estimate a receiver clock and scan epoch because they have the same
propagation-time direction. Within a scan containing multiple satellites,
relative satellite epoch contrasts can still be measurable. Sparse recurrence
does not by itself prove all such terms are unidentifiable. Their precision
also depends on the Doppler-shape Jacobian after profiling per-track CFOs.

The scan--satellite bipartite graph must be checked per connected component.
The exact additive gauge is `u_s -> u_s + c`, `eta_k -> eta_k - c` for every
node in one component. Fix one scan timing term per component, or impose one
weighted zero-sum constraint on its satellite terms, and verify rank. Imposing
zero means on both families adds another assumption; it is not merely fixing
that one gauge. Hold location
fixed in an initial nuisance fit, or apply a predeclared location prior, since
location Doppler gradients also confound time shifts. Retain only a per-track
constant CFO; short tracks should not receive timing terms. Candidate selection,
bounds, support thresholds, and any epoch regularization must be frozen from TRAIN data
before a reserved-row score.

`recurrence.json` contains every candidate's distinct-scan support and weighted
evidence thresholds. `design.json` records the precise model, gauges,
confounding constraints, consulted prior orbit work, and source bindings. This
is a design/recurrence report only: it fits nothing and uses no location truth,
validation, or test data.

For the two-satellite/one-scan linear example, rows of the design matrix are
`[1,1,0]` and `[1,0,1]` for parameters `(u, eta_1, eta_2)`. Its one gauge is
`(1,-1,-1)`, while `eta_1 - eta_2` is observable in the difference of the two
rows. A regularized within-scan satellite-effects experiment remains possible;
it would be prior-conditional and must be tested for location confounding.
