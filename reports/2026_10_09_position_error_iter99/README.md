# Active-face scalar curvature polish: synthetic preparation

Iteration97's saved postfit lies on a coupled satellite-timing constraint.
Its large raw coordinate gradient mostly balances the constraint normal.
The coordinate Newton step leaves the feasible set even though the independent
projected stationarity residual is much smaller. Scalar coordinate curvature
alone does not describe a feasible improving direction on that face.

This prototype forms the same scaled free-variable active normals as the
existing KKT check and uses rank-aware SVD to project the gradient into their
nullspace. One normalized negative tangent-gradient direction is chosen
deterministically per round. Central directional gradient differences at the
existing1e-5 probe estimate scalar curvature; a feasible one-sided probe is
permitted. Test the same Newton dampings1,1/2,1/4. Every trial retains exact
physical feasibility checks, full independent KKT and the fixed initial128ULP
objective ceiling. At most10rounds/100evaluations; threshold remains0.001.

No dense Hessian, alternate region, reference coordinate or learned parameter.
This stays on the active face and cannot release a wrongly active constraint.
A tangent plane is not a curved constraint surface: every probe/trial is checked
for physical feasibility. Reduced-gradient stationarity alone never qualifies a
fit. Ill conditioning, nonpositive curvature or a blocked face can still stop it.

The driver reconstructs the exact corrected objective and saved failed97 state,
verifies its objective, and retains all trials. Execution requires parent review,
source/input freeze and publication first. No accuracy or localization benefit is established.
Iteration98 remains a separate conditional downstream continuation; it cannot
execute without an independently qualified postfit in its frozen input inventory.
