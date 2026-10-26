# Independent scientific audit

All 16 frozen-Gamma conditional-Gaussian fits complete, with unchanged packets
and fixed likelihood IDs. The CFO effect dominates DS24-0010; the full precision
packet dominates DS24-0011. Both c arms agree qualitatively. This separates
mechanisms within the declared conditional model, not physical causes or a
deployable choice of precision. Operational references remain unchanged.

| Scan / arm | Symmetric CFO displacement (m) | Symmetric packet displacement (m) | Interaction (m) |
|---|---:|---:|---:|
| 0010 / c=0 | 131.63 | 18.08 | 14.08 |
| 0010 / fitted c | 129.79 | 13.92 | 13.92 |
| 0011 / c=0 | 21.92 | 82.49 | 24.98 |
| 0011 / fitted c | 21.67 | 86.71 | 22.77 |

These are norms of signed vectors. The two symmetric vectors sum to the total
endpoint change; their norms do not add. Interaction is comparable to the CFO
effect in 0011, so attribution depends on the other factor's level. The packet
includes all fragment noise and coefficient-prior precisions, including phase
prior precision. It does not isolate one owner's noise weight. Both target and
control owners change together.

## Mathematical and actual-input checks

The existing log-volume-one helper matches an independent dense observation-
covariance oracle, including fractional-power normalization. All eight actual
diagonal preparations reproduce the preceding same-arm coefficients, frequency
residuals and predictive factors at the saved final **input** reference.
The full physical-coordinate packet, constant-prior scaling, fitted-c slot 8,
inactive noise zeros and native-delta/alias mapping remain exact.

All gates and coverage use the same conditional posterior as the objective.
There is no VI reconstruction in membership, no frozen nuisance mean, no lost
predictive covariance and no Gamma-convergence claim. The complete old curved
and predictive IDs remain fixed. Independent checks cover all 80 optimizer
histories and phase updates; accepted scores decrease. Fifty-four epochs stop
on the original small-step rule and 26 on no accepted damped step. Completion
does not establish a global optimum.

The conditional objective differs from the VI bound. Diagonal optimized
endpoints need not reproduce VI endpoints; their observed differences are
1.15–5.52 m in 0010 and below 8 mm in 0011. No VI-objective equality or packet
selection by geographic error is imposed.

## Geographic and qualification readback

Independent unit-vector distances reproduce all 16 released geographic rows.
At a fixed original/refined packet, CFO changes improve raw error by roughly
126–133 m in 0010 and 18–26 m in 0011. These within-packet comparisons are
distinct from the preceding VI original/refined comparison.

All 16 active residual/owner/phase checks pass. In 0010 every cell retains all
original accepted IDs. In 0011 c=0, cells 00/10/01/11 lose 0/36/21/57 postfit-only
IDs; fitted-c loses none. The changed cells therefore fail paired retention.
No likelihood observation is removed, no threshold is waived and no cell is
adopted operationally.

The posthoc saved-H comparison now has the appropriate comparator: the CFO-only
effect at the original fixed packet. H differs from it by 0.354/2.323 m in 0010
and 0.710/0.467 m in 0011. This explains why the earlier approximately 90 m
0011 discrepancy against the *full* refit was not a failure of isolated CFO
linearization. Precision feedback and interaction account for most of that
extra movement within this model. These exposed-vector checks do not calibrate
general linear-response accuracy or identify physical measurement-noise truth.

## Next decision and evidence

Prepare the four fixed later recordings before further same-scan variants.
The metadata inventory verifies a chronological selection rule and 22 eligible
remaining rows within its 32-row scope. It establishes neither complete raw
authority nor ready research parents. The bounded exposure search is
incomplete; its empty result cannot establish an untouched holdout. Full input,
site authority, causal-parent preparation and capped whole-owner feasibility
remain prerequisites. Preserve unavailable members and original gates.

The packets are empirical quantities learned at different endpoints using the
same observations. A future uncertainty test should use independent pilot/frame
evidence and distinguish estimator bias, measurement variability and orbital
error. Repeating geographically favorable packet choices on these two scans
would not validate an operating policy.

Receipts: [dense control](gaussian_fixture.json), [preflight](preflight.json),
[terminal RF audit](terminal.json), [optimizer histories](optimizer_readback.json),
[geographic/RF arithmetic](evaluation_readback.json),
[saved linearization](linearization_readback.json) and
[metadata selection](metadata_readback.json). Audit [source](check.py) makes no
detector, geometry or optimizer calls. A relative reporting-path assertion
failed once and was repaired in the audit only; the
[preserved attempt](linearization_attempt01.json) carries a conservative one-
second charge. No scientific artifact or criterion changed. Total numerical
audit work remains below 120 seconds.
