# Direct coarse-CFO GLRT experiment

This report-only experiment retains the full original coarse search and all
eight retained hypotheses in each 20-ms window. For each supported refined
epoch it calls the final GLRT directly at that candidate's coarse CFO. It skips
fine acquisition, conditioned CFO search, and normalized verification.

Final GLRT retains its own residual-CFO maximization. This is approximate CFO
conditioning, not an exact refinement replacement. Candidate JSON marks
`refinement_skipped: true` and serializes uncomputed fine, conditioned, and
verification fields as `null`; final GLRT fields remain computed. No production
or sealed-report source is changed.
