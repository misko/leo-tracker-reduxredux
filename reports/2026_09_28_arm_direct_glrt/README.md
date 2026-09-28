# Direct coarse/fine-CFO GLRT experiment

This report-only experiment retains the full original coarse search and all
eight retained hypotheses in each 20-ms window. For each supported refined
epoch it calls the final GLRT directly at that candidate's coarse CFO. It skips
fine acquisition, conditioned CFO search, and normalized verification.

Final GLRT retains its own residual-CFO maximization. This is approximate CFO
conditioning, not an exact refinement replacement. Candidate JSON marks
`refinement_skipped: true` and serializes uncomputed fine, conditioned, and
verification fields as `null`; final GLRT fields remain computed. No production
or sealed-report source is changed.

Mode 2 retains the original fine FFT range search and parabolic interpolation,
then passes the interpolated CFO directly to GLRT. It serializes `fine_cfo_hz`
but keeps conditioned and verification fields `null`.

See REPORT.md for measured recovery and ARM timing. Mode 2 takes 24.454528
CPU seconds per 120 ms dual-RX dwell on CPU0 (1.37922x versus the full
verification-fusion baseline), recovering 100/119 original hits in 88 ARM
windows. Equal positive totals do not imply recovery: tracking-CFO branch
changes are counted as unmatched under the original <=8 kHz association gate.
