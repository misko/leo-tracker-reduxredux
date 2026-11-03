# Fine timing profiles for ambiguous DS8 scans

Select scans whose timings differ by more than 0.1 seconds between the two original qualified N40 endpoints. This training-parameter rule selects three scans. Hold geography fixed at (a) the latest qualified timing-reselected joint fit and (b) the original qualified rank-start N40 fit. The failed rank refit is not used.

Evaluate training likelihood on 401 equally spaced timing points from −5 to +5 seconds (0.025-second spacing). Identify every strict local maximum, including one-sided boundary maxima; refine each with the unchanged fixed-position timing optimizer. Also refine the inherited timing. Keep every attempt, select highest qualified training score only, and report held scores afterward. Scalar-replay the inherited and best-grid scores. Report peak spacing and score margins, preserving unqualified attempts. This grid and its local refinements do not prove a global optimum between sampled points.

Cap the full diagnostic at 180 seconds. No joint geographic refit is part of this experiment. No model, threshold, observation, RF collection, or production change. Data are exposed DS8 observations; this is diagnosis rather than independent accuracy validation.
