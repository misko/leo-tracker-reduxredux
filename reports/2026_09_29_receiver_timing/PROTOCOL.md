# Target timing refit at frozen source-receiver positions

Use all 36 selected source-receiver fits from 2026_09_29_receiver_panels,
covering RX0->RX1 and RX1->RX0 on every consecutive four/eight-scan panel.
Hold each source position fixed. Optimize only the other receiver's recording
timings on its training observations, with the same shared-scale zero-decay
likelihood, candidate banks, partitions and profiled frequency offsets.

Three predetermined timing starts: transferred source timings, the target's
own previous fitted timings, and all zero. Target-own geographic coordinates
are not used. Bounds +/-5 s and L-BFGS-B settings remain maxiter140/maxfun200,
ftol1e-14, gtol1e-8, maxls30. Highest training score among successful interior
fits with timing-gradient infinity norm <=0.01 selects the refit. Retain every
failure; no retries, boundary relaxation or unqualified fallback.

Verify the position never changes, exact target partition/held identities,
training replay within 1e-7 and timing-gradient centered differences at
0.001/0.0005 s within 0.002. Compare target held score after timing refit with
the frozen transferred-timing result and with the original both-receiver fit.
Report whether the previous cross-receiver predictive loss persists; preserve
all 36 denominators and failures. No reference error or new location is scored.

One scientific worker, BLAS1/nice19, 4 GiB address-space cap, 180 s/process,
>=5 GiB available memory before launch. Prior receiver runs peaked below
0.7 GiB RSS. No other scientific worker overlap, new RF, waveform reads,
propagation, provider fetch, likelihood/helper changes or fixture changes.
These fitted timings are phenomenological nuisance parameters, not measured
hardware clock offsets, physical travel delays or antenna-tilt calibration.
