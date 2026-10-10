# Actual-model clock-uncertainty preflight

This experiment checks the existing likelihood at the original selected endpoints
of the twelve consumed development recordings used in iteration154, in both final
c arms. It does not fit positions, integrate a likelihood, or evaluate position
errors. The goal is to establish derivative/factorization parity and measure the
cost of exact likelihood calls before deciding whether nuisance integration is
worth implementing.

[PLAN.md](PLAN.md) defines six maximum joint calls per endpoint, with a 30-second
soft callback budget. Reconstruction costs are separate. All twelve members and
both arms remain in coverage, including failures. Source, input and runtime
identities must be frozen and published before the two serial shards launch.

The source review verified the B7 seed authority: one joint-stage chain is run
after selecting the regional winner. Each of the 24 saved endpoints matches its
corresponding B7 attempt, and each member's two arms share the same region and
ordered satellite bank. The runtime check will additionally compare the complete
reconstructed model and local constraint identities. Shared labels alone are not
a controlled c ablation, and this preflight makes no c-effect or accuracy claim.

Initial component tests passed (35 tests, 0.19 seconds, pinned47e interpreter and
single-thread numerical libraries). A subsequent metadata-only preparation check
correctly detected that iteration154's README had been updated after completion
to report its results. The successor records only that exact published narrative
change as preparation provenance; it is not an inference input. Every inherited
scientific source and other input remains strictly bound. The final test receipt,
protocol and execution results will supersede this preparation status.

No production change or new RF collection is part of this work. Iteration154's
negative result and the official 193-recording position metric remain unchanged.
