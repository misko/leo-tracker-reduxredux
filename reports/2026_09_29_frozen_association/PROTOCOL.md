# Frozen pooled-association diagnostic

Evaluate all 18 eight-scan panels, without selecting panels by their previous error. Freeze the posterior component probabilities at the selected N24 training fit, using that donor's position and each scan's timing. Optimize the expected complete-component training log likelihood plus the fixed donor entropy. This is a tangent lower bound on the original mixture likelihood, not a new normalized observation model.

Use two starts per panel: the existing selected panel point/timings and the pooled donor point/timings. Retain original bounds and qualification gates. Select the largest qualified surrogate training score; preserve failed starts. No fallback promotion if neither new fit qualifies. Require identical visible support at every evaluated point; a support change is a recorded failed start, never silent renormalization.

Audit donor score and gradient equality with the original mixture and lower-bound validity at the panel endpoint and selected new endpoint. Assess reference distance only after selection. Evaluate held contrasts through the **original mixture model** at the new parameters, using its normal training-conditioned predictive score, and compare against the original panel and pooled donor. This is not held evaluation of a standalone frozen-probability observation density. It assesses parameter changes under the unchanged observation model.

The donor uses all 24 scans, including the panel: this is an association-mechanism diagnostic and cannot establish an eight-scan acquisition improvement or source-independent transfer. Exposed reference and data, retained-bank conditioning and unknown reference uncertainty remain. Two starts do not establish global optimality.

Each dataset process is capped at 300 seconds with BLAS1, with no retries or RF collection. No production changes.
