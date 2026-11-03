# Remaining-24 drift confirmation

Apply the exact cross_band_rx_drift model and pairing rules to original indices
not divisible by four. Preserve all support rules, native units, source exclusion,
donor medoids, slope bound, interpolation-only application and constant fallback.
No parameter tuning, alternate arm or new geographic fit is included.

Require all24 evaluation scans, positive mean and median source-averaged scan
gain, and at least15/24 positive scans, preserving the screen's5/8 fraction.
This is additional same-site measurement evidence, not an independent deployment
or a position-error result. A failed gate stops this model from advancing to
geographic fitting. A pass still requires a separate allocation/position protocol.

The runner is a copy of the frozen screen with only selected indices, gate size,
description and source bindings changed. Tests must establish exact Python AST
equality after reversing these changes, as well as model behavior parity.
Run once with one numerical thread under90seconds. Verify source hashes and
aggregate held errors independently, without retuning or replacing scans.
