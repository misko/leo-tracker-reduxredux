# Sampling-grid bridge revision

The first frozen worker returned `a sampling grid needs at least three instants` on the four target cases before any new state could be generated. Its source and all eight outcomes are preserved under `sampling-grid-attempt/`. No endpoint or RF scores were evaluated before this revision.

This revision retains the original orbit support bounds and trial roster. The frozen propagator receives enough original seam knots to satisfy its three-instant input contract. It must reproduce all supplied original seam states exactly. Only the newly added causal knots are inserted and the original interpolation and derivative pathways still run. The fresh replay uses CPUs 0–3 after CPU0 was released from an independent validation. The original worker deadline remains 195 seconds. The original 12-minute numerical limit includes the first attempt and diagnostic runs.
