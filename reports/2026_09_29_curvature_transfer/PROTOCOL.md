# Cross-receiver curvature beyond a target's own linear residual

Use all nine existing eight-scan residual exports (3,983 inherited eligible
tracks), not the twenty loss-selected diagnostic tracks. Freeze source bytes
before scoring. Residuals inherit fitted geography, timing and training-model
candidate assignments. No new geographic fit or independent calibration claim.

Target baseline: ordinary least-squares intercept and slope using its training
mask only. For x=(time−target training mean)/target training span, orthogonalize
x² against [1,x] on the target training samples. Add donor quadratic coefficient
times this residualized x² to the baseline. This leaves target training linear
normal equations unchanged. Own-quadratic is a comparator, not calibration.

Donors: same scan and exact RF, opposite RX, distinct track; train-span overlap
at least 50% of the target span. Use only donor training samples inside that
target training span, requiring at least eight points, at least ten seconds
span, and rank-three quadratic design. Target requires at least eight training
points, ten-second span, and held samples. No held values choose support,
coefficients, donors or thresholds. Fit donor quadratic on the target's scaled
time basis. Median coefficients within candidate, then across candidates for
the other-candidate control. Same-candidate support needs one donor.

Compare target-linear, transferred same-candidate curvature, other-candidate
curvature, and target-own curvature using median absolute held residual per
track. Unsupported target predictions equal the linear baseline. Report all
tracks, exclusions, supported and matched populations; positive paired gain
means improved held prediction. Reciprocal transfers are not independent trials.
Masks are interleaved, not causal forecasts. Run bounded to 120 seconds, no RF.
