# Frozen diagnostic gate for eight-scan fits

Evaluate all 18 qualified `grid_` fits: three contiguous and three interleaved balanced sets per DS7/DS8/DS9. Reuse their selected locations and timings; do not refit or select panels using outcomes.

At each selected training fit, evaluate per-scan score gradients and observed negative Hessians. Profile each scan's timing with the Schur complement, using the established half-step derivative audit. Sum profiled Hessians. Require positive-definite pooled curvature, successful original source qualification, additive score/gradient replay below 1e-7, and all derivative relative/asymmetry audits below 0.01.

Use the established centered sandwich formula `H^-1 [K/(K-1) sum (g-mean(g))(g-mean(g))'] H^-1`. Compute it with eight scan clusters and separately with four chronological adjacent-pair clusters. Pairing is by the source fit's chronological scan order. Freeze the acceptance rule before evaluation: **accept only if both radial scales sqrt(trace(covariance)) are strictly below 1 km**. Numerical failure means abstention, never exclusion from coverage denominators.

These are local disagreement scales, not calibrated confidence bounds. Four pairs cannot establish asymptotic calibration, and shared bias can be invisible. The 1 km cutoff is a diagnostic heuristic matching the objective; no confidence level is claimed. Report acceptance/18, accepted reference-distance failures >=1 km, and rejected successes, by panel family and dataset. Examine every panel; do not tune the cutoff after outcomes.

Reference distances are evaluated only after the gate. Data and reference were exposed in previous research; this is exploratory assessment, not blind validation. No RF collection, production changes, or new geographic fitting. Limit each dataset process to 300 seconds with BLAS1.
