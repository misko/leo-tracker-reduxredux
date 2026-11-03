# Joint candidate and causal orbit-revision uncertainty

The frozen DS7/DS8 finite symmetric coefficient priors now enter a DS11
position-dependent objective. Each conditional same-source group shares both
physical satellite identity and one revision coefficient across tracks. Each
track retains its own profiled CFO. Singletons retain their complete candidate
banks; groups use the previously frozen physical candidate intersections.

Scans 0 and 16 pass numerical gates. The zero-revision model exactly reproduces
the existing joint-identity score; gradient parity errors are below 1.2e-12.
Finite-difference discrepancies across zero, orbit and linear arms are below
4.87e-6. Full orbit gradient evaluations took 1.29 and 1.68 seconds; full audits
took 22.8 and 26.4 seconds. Three synthetic tests cover gradients, held isolation,
zero parity and matched linear-direction scaling.

All orbit records are causal. The older-minus-original direction is centered
on training observations at each position. The linear control has the same
training RMS. Finite coefficient states are marginalized, while CFOs are
profiled: this is not full CFO marginalization or calibrated orbit covariance.
Grouping itself is conditional and restricts candidate combinations; the zero
arm separates this assumption from revision uncertainty. No position improvement
follows from these numerical checks alone.

See [protocol](PROTOCOL.md), [scan 0 audit](00.json), [scan 16 audit](16.json),
and the subsequent [held-prediction bridge](../joint_orbit_prediction/README.md).
