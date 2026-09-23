# Shared CFO v2: training-only optimizer qualification and development replay

Freeze this protocol, optimizer, runner, and synthetic tests before replay.
Preserve the v1 Powell attempt. This remains development on previously inspected
random groups, not fresh validation or a statistical common-oscillator test.

Use the same nominees, six snippets, physical random masks, raw hashes, two
fixed-alias abstentions, and model definitions as the v1 comparison. All four
effective CFO residuals and optimizer coordinates remain bounded by ±2500 Hz.
Independent frequencies use four coordinates. Shared frequencies use two RX0
source corrections plus a common total receiver offset. Channel coefficients
are still separate per tone, source, and receiver and constant over 20 ms.

Replace broad Powell minimization with two coordinate-grid sweeps at 50 Hz,
always retaining the incumbent training SSE. For shared initialization, first
make one independent four-coordinate training grid sweep, then evaluate shared
starts at the mean and each individual receiver offset inferred from those
training peaks. Skip infeasible candidates. Choose starts using training SSE
only. This was added after a guarded synthetic shared-signal case exposed a
wrong-peak solution from a zero initializer; the regression test remains.

Refine the retained grid point using SLSQP with analytic variable-projection
gradient, exact linear constraints on all effective residuals, 50 Hz coordinate
scaling, at most 100 iterations, and ftol 1e-12 on energy-normalized training
SSE. Reject infeasible/nonfinite or worse local candidates. These are numerical
tolerances, not physical frequency uncertainties. Designs must have full rank
and singular-value condition ≤1e6. Preserve the common snippet phase reference.

Before replay, test analytic gradients against finite differences, nonzero
shared-signal recovery over a 20 ms span with random guarded physical groups,
independent-source recovery, source-specific mismatch, held-response
independence, and degenerate-column abstention. Synthetic tone coefficients
vary per tone/source/receiver. Passing this finite suite does not prove global
optimization on arbitrary real data. Record objective histories, boundary and
local-solver diagnostics for every executed arm.

Replay uses the original verified read-only store and at most the four feasible
20 ms snippets, with a five-minute total execution cap. Report each receiver's
held SSE change and all abstentions without a chosen pass threshold. A good
shared waveform fit would support further common-state study, not establish
calibrated phase geometry, satellite identity, speed, or receiver position.
