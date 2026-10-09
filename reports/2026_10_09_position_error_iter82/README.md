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

## Retrospective endpoint audit

`slope_audit.py` compares the stored 0.25 and 0.5 endpoints under each fixed prior,
using the exact Gaussian penalty difference and the orthonormal satellite basis.
This separates changed regularization preferences from solver qualification failures.
It generates a regression table and scatter plot, retaining unqualified raw pairs
in JSON while excluding them from claims about qualified endpoints. No new fit or
operational selection occurs. Reference errors are evaluation-only.

For example, DS16-051's two qualified endpoints reverse score preference when the
prior widens. Error increases 2.389 to3.205km; the full satellite-slope vector norm
increases1.311 to4.914Hz/s. These norms are not individual receiver slopes or the
hard60 limit. A regression here does not establish a gradient bug or a wrong
optimizer stopping event. The audit does not establish global optimality either.

The next modeling question is whether slope corrections absorb motion information
needed to constrain position. A future experiment could regularize the correction
modes most confounded with the position derivative, computed at hypothesis positions
without reference coordinates. That is a hypothesis to test under a frozen uniform
rule, not an implemented or validated improvement. Ordinary-region clock recovery
still needs its own full-cohort generalization; it is not included in this sensitivity.
