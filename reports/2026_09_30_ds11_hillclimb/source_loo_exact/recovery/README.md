# SLSQP recovers solver status at the same numerical endpoint

The separately declared diagnostic passes. One SLSQP continuation returns
successful termination and passes the original finite, interior, gradient and
finite-difference qualification checks. It changes the saved failed endpoint
by 2.05e-12 metres horizontally and 3.55e-15 seconds. Retained score changes
by -8.19e-11 nats (within the prospectively allowed 1e-7 tolerance); common
held score changes by +4.71e-11. This is solver recovery, not a geographic gain.

The prerequisite [precision diagnostic](../precision/README.md) found stable
positive-definite local loss curvature and a predicted Newton displacement
of 0.0004666m and 2.82e-8s. Its measured objective fluctuations exceeded the
predicted quadratic improvement. The original L-BFGS-B failure and failed
same-solver restart remain preserved.

The new fit has maximum gradient3.5714e-5 and finite-difference discrepancy
3.9401e-6. It uses12 evaluations and one SLSQP iteration; the process exits0
in7.42seconds under a90-second single-thread cap. Fourteen component tests
cover eligibility, precision gating, unchanged qualification, nonworsening,
exactly one continuation and a real smooth quadratic solve. Independent
source/receipt and result review passes.

See [protocol](PROTOCOL.md), [result](result.json), [receipt](receipt.json).
A separate uniform screen revision may use this rule; the original screen
remains failed and no reference-position errors have been evaluated here.
