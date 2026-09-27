# DS6 continuous position, timing, and receiver drift

This completed four-scan development experiment does **not** establish DS6-wide
sub-kilometre accuracy. The 7.5 MS/s scan has a sub-kilometre estimate in both
matched arms. All other scans remain several kilometres away.

| Scan suffix | MS/s | No drift error (m) | Receiver drift error (m) | Held log-score gain with drift |
|---|---:|---:|---:|---:|
| 3221795d82a1c7ec | 10 | 6284 | 6992 | 2.36 |
| 5eaaa2a8f8c995b3 | 2.5 | 3669 | 4665 | 25.95 |
| c78fb2dba2465361 | 5 | 8485 | 8560 | 19.47 |
| c7e37f65ae9e08b0 | 7.5 | 504 | 893 | 9.97 |

The protocol was frozen before fitting. Both arms fit continuous position and
one scan timing offset, marginalize inherited candidate identities, and use a
Student-t4 observation model with 100 Hz scale and training-profiled per-track
CFO offsets. The drift arm adds one linear normalized-CFO drift per receiver,
with a predeclared 5 Hz/s Gaussian prior. Three starts per arm use training scores
only. The original reproducible random whole-visit assignments are retained.
The 10 MS/s input has only RX1 positioning tracks; it remains in the comparison.

All 24 optimization runs report convergence; selected estimates are inside the
declared position, timing, and drift bounds. Propagation during optimization uses
quarter-second interpolation; exact propagation at each winner differs by at
most 0.021 Hz. This is negligible beside the 100 Hz likelihood scale.
Continuous optimization here profiles timing, whereas the previous grid study
marginalized timing. Consequently only the two arms in this report are matched
comparisons; changes from the prior grid report cannot be attributed solely to
grid resolution.

Drift improves held prediction in all four cases but increases position error
in all four. Predictive improvement alone therefore does not justify treating
the effective drift as a hardware calibration or accepting these positions.
The result motivates investigating systematic timing/track-model bias and
cross-track consistency rather than adopting receiver drift as the solution.

Limitations: inherited approximate catalogue shortlists, local search bounds,
four development scans out of 43, profiled nuisance parameters, and an
operator-supplied coordinate without surveyed uncertainty. The fit script never
loads that coordinate; `summarize.py` reads it only after all estimates are
frozen. These are development results, not a blinded validation claim.

Artifacts: `protocol.json`, `run_joint.py`, the four scan JSON outputs,
`summary.json`, `summarize.py`, and `test_joint.py`. Tests check held-data
isolation, zero-drift equivalence, interpolation endpoints on synthetic banks,
source/input binding, training-only selection, and real exact-propagation audits.
No RF was collected and no production service was changed.
