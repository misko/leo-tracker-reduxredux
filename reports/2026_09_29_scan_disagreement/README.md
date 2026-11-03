# Training-score disagreement predicts subset location shifts

The source-only local diagnostic predicts the direction of the measured
location shift for all 12 examined eight-scan subsets. Direction cosines range
from 0.9828 to 0.99999. In particular, DS7's geometry-selected subset already
has a strong training-score pull away from the pooled solution. A high geometry
information score therefore does not imply agreement with the other scans.

| Dataset | Selected scans: early / middle / late | Predicted shift from N24 | Actual shift from N24 | Direction cosine | Vector prediction error |
|---|---:|---:|---:|---:|---:|
| DS7 | 1 / 1 / 6 | 3,395 m | 1,469 m | 0.9997 | 1,927 m |
| DS8 | 7 / 0 / 1 | 487 m | 638 m | 0.9939 | 163 m |
| DS9 | 1 / 6 / 1 | 480 m | 471 m | 0.9997 | 15 m |

These are displacements from each dataset's N24 fitted location in the model's
east/north coordinates, not geographic errors. The diagnosis compares against
already observed subset fits and is retrospective. No geographic reference or
target score enters the derivatives or the local prediction. It does not prove
that the pooled location is true or identify which individual scan is biased.

## Balanced controls and magnitude limitations

| Dataset / subset | Predicted shift | Actual shift | Direction cosine | Vector prediction error |
|---|---:|---:|---:|---:|
| DS7 balanced0 | 2,140 m | 1,782 m | 0.9925 | 430 m |
| DS7 balanced1 | 1,017 m | 855 m | 0.9979 | 173 m |
| DS7 balanced2 | 1,166 m | 1,089 m | 0.9955 | 132 m |
| DS8 balanced0 | 751 m | 755 m | 0.9997 | 19 m |
| DS8 balanced1 | 1,006 m | 1,091 m | 0.9997 | 88 m |
| DS8 balanced2 | 1,629 m | 2,568 m | 0.9828 | 1,012 m |
| DS9 balanced0 | 2,140 m | 1,954 m | 0.9989 | 210 m |
| DS9 balanced1 | 1,013 m | 970 m | 1.0000 | 44 m |
| DS9 balanced2 | 818 m | 666 m | 0.9997 | 153 m |

Large magnitude errors for DS7 information selection and DS8 balanced2 show
that the local approximation cannot replace fitting. The last table value
rounded to 1.0000 is 0.9999856, not exact directional agreement. These subsets
overlap within a dataset and are not independent replication trials.

## Calculation and checks

The [protocol](PROTOCOL.md) fixes the existing 24-scan source fit as expansion
point. Each scan's original q020 training likelihood supplies its score gradient
g and negative Hessian H. H is obtained by differencing analytic gradients and
audited at half steps. Locally profile the scan's timing parameter:

```
profiled H = H_position − H_position,time × inverse(H_time,time) × H_time,position
profiled g = g_position − H_position,time × inverse(H_time,time) × g_time
predicted subset shift = inverse(sum profiled H) × sum profiled g
```

Unlike the preceding expected-information proxy, this uses the observed local
curvature of the full training mixture, including its nonlinear weights. A
positive summed curvature permits the stated local Newton prediction; it is
not a calibrated uncertainty matrix or proof of a global optimum.

All 72 per-scan derivative checks qualify, and all 12 subset curvature matrices
are positive definite. Maximum relative half-step Hessian discrepancy is
0.000103, maximum asymmetry 1.08e−6. Summed single-scan scores replay the pooled
model within 7.57e−10 log units and gradients within 2.81e−13. No failed cases
are omitted. Three processes exit zero in 20.6–21.1 seconds, under 180-second
caps. Two synthetic tests verify the profiled step against an exact quadratic
solution and abstention for negative timing curvature. Ruff passes.

## Next method to test

The evidence supports a bounded **score-balanced subset** prototype: select
informative scans whose aggregate source score gradient is near zero at the
pooled fit, then refit and evaluate excluded scans. Freeze the selection rule
before execution and retain the original information-only and timestamp-balanced
controls. Matching source derivatives is a data-reduction objective; it does
not establish truth or justify deleting disagreeing scans as corrupt.

The full 24-scan pool is required for the scouting fit and these derivatives.
An eight-scan subset selected this way is not an eight-scan acquisition method.
No new geographic fit or accuracy improvement is claimed here. The prior
[selection experiment](../2026_09_29_information_selection/README.md) remains
mixed, and robust independently validated sub-km accuracy is unresolved.

Raw per-scan matrices, gradients, qualifications and all subset comparisons
are in DS7.json, DS8.json and DS9.json. Source bindings are frozen in
[manifest](manifest.json); [study.py](study.py) and process receipts preserve
execution details. No new RF, production changes or publication occurred.
Artifacts are local. Reproduction uses `study.py prepare`, then `study.py batch`
under a NumPy/SciPy interpreter in a fresh output context.
