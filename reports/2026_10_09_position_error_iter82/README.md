# Iteration82: preserve and retry DS17 input failures

Iteration78's 51 DS17 members failed before fitting: the historical DS17 loader
imports `digest` from an unqualified module named `freeze`. Later research imports
change the search path, resolving that name to iteration28's different module.
This is an input-loading defect, not evidence of failed localization.

The retry replaces only that metadata lookup with the same SHA256-prefixed digest
verification and JSON decoding, explicitly bound to the DS17 protocol directory.
It calls the unchanged iteration78 numerical evaluator, with a separate output
directory. Original failures remain immutable and are pinned by the retry protocol.
Tests exercise the conflicting module and reject protocol tampering.

All three satellite-slope priors, observations, seeds, candidate banks, matched
c=0/fitted-c arms, convergence gate, budgets and fallback policy remain unchanged.
No additional numerical workers start until the original two terminate. Results
will be combined by explicit receipt provenance, preserving all 148 cohort members
and reporting the 51 original input failures separately from numerical convergence.

This is consumed-data development. Production, reserve outcomes, and RF collection
remain unchanged. No new accuracy claim is made before completion.
