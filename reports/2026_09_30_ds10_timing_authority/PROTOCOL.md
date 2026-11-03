# DS10 capture timing authority

Read timing metadata for the frozen DS10 N24 height-zero population through the public read-only AdaptiveHopIqStore inspection port. Verify manifest digests against frozen observation exports and plan. Reuse the independent bracket reconstruction from the DS7–9 timing audit. Compare fixed fitted timing offsets with the reconstructed host brackets and test whether one constant host bias can cover them all. This is a metadata test, not a timing or location refit.

Retain missing timing explicitly. No substitution or population changes. A host call bracket does not establish absolute UTC without historical clock discipline evidence. Empty common-bias intersection only rejects an explanation of the existing fitted values; it does not reject a different joint location/time fit.

One process, 120-second metadata cap, no IQ reads or archive writes. Bind runtime reader and timing-contract source hashes.
