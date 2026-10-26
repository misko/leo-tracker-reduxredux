# Separate geographic evaluation release

2026-10-26 UTC. The position branch's RF seal and independent
`audit/position_terminal.json` pass before this release. The audit retains all
six declared slots: four final no-addition/hard endpoints and two mixture
timeouts with no final endpoint. The no-addition controls reproduce the saved
reference exactly. Original support, target residual and association-preservation
failures remain in effect.

The coordinator releases evaluation at 37.849061591561885,
-122.48574968092912 for the sealed final endpoints and exact reference fallback
only. Do not score the first-round mixture iterates as completed positions.
Do not alter candidate pools, observations, priors, integration, optimization,
source gates or fit budgets after seeing geography. All new geographic files
are derived evaluation products, separate from the frozen RF results. This
release does not authorize a scientific retry or operational source admission.
