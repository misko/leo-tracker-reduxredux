# RF-center convention has a small, mixed residual effect

**The tuned-center versus nominal pilot-center denominator does not produce a
useful consistent residual improvement in this assay.** It changes the canonical
frequency scale by at most 29.18 ppm. After removing the existing track constant,
the median training-shape change is 0.488 Hz RMS and the largest centered point
change is 3.374 Hz. No position fit or geographic gain is established.

| Dataset | Cases | Different normalization centers | Better / worse held median | Mean paired held-error reduction | Median training-shape change RMS |
|---|---:|---:|---:|---:|---:|
| DS7 | 1,346 | 1,103 | 533 / 548 | −0.00497 Hz | 0.467 Hz |
| DS8 | 1,311 | 1,140 | 588 / 543 | +0.03862 Hz | 0.503 Hz |
| DS9 | 1,326 | 1,244 | 588 / 628 | −0.00618 Hz | 0.493 Hz |
| Total | 3,983 | 3,487 | 1,709 / 1,719 | +0.00898 Hz | 0.488 Hz |

Positive reduction means better. Wins/losses use 1e-6-Hz reporting tolerance;
remaining cases tie. Full-population median paired reduction is zero in every
dataset. On changed-center cases alone the pooled median is −1.19e-7 Hz and mean
+0.01025 Hz. Small center differences include 2–4-Hz tuner rounding as well as
the 312.5-kHz tuned-center displacement; changed-center counts do not all represent
the larger displacement. Both populations remain available in `results.json`.

## Measurement convention traced

The checked tracking projection supplies `fractional_tracking_cfo_hz` with RF
`target.rf_center_hz - actual_if_offset_hz`. Persistent trajectories normalize
this CFO and alias spacing by `11.2 GHz / actual_rf_hz`; numerical observation
exports preserve that canonical frequency. The same-source provenance was
recorded in the [earlier normalization audit](../2026_09_29_rf_residual_excess/source-audit.json).

The installed public `starlink_edge_rf_center_frequency_hz` contract supplies
nominal centers of the eight-tone pilot bands. Many captured tuned centers are
312.5 kHz from those nominal centers. Other cases match apart from small tuner
rounding. The channel comes from the pinned observation export; choosing the
nearer lower/upper edge is unambiguous for every case and within the frozen
1-MHz maximum separation. No case needed an inferred distant channel.

The hypothesis compares `y_new = y * actual_RF / nominal_pilot_RF`, leaving
canonical satellite Doppler, candidate assignment, location and recording time
fixed. The new residual is `old_residual + y_new - y`; each arm removes its own
training mean before held scoring. Consequently, large stationary CFO offsets
do not become spurious accuracy gains. The unchanged 100-Hz model scale is
retained; this is a conditional frequency-shape comparison, not a detector or
full likelihood refit.

The nominal center is a documented waveform convention, not an independently
measured transmitter oscillator or the exact frequency weighting of a real
eight-tone estimator. This assay does not prove which effective center best
describes every measurement. It also does not prove that a few Hz could never
matter geographically; no such downstream bound was evaluated. It provides no
evidence that this convention explains the dominant residual/time-shift problem.

## Verification and reproduction

The [protocol](PROTOCOL.md) preceded execution. All 3,983 cases and nine panels
are retained. Observation bytes match declared hashes, training masks join
exactly, and every RF maps to one nominal edge center. `centers.json` binds the
installed public contract source; `results.json` binds protocol, estimator,
input residuals, observation exports and center metadata and records every case.
Two tests pass for algebraic normalization/zero-change identity and constant
offset removal. Ruff lint/format pass. No RF collection, production mutation,
geographic fitting or reference-coordinate selection occurred.

```bash
sudo -n /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_rf_center_convention/centers.py > reports/2026_09_29_rf_center_convention/centers.json
.venv/bin/python -m unittest discover -s reports/2026_09_29_rf_center_convention -p 'test_*.py'
.venv/bin/python reports/2026_09_29_rf_center_convention/study.py
```

Retain this convention distinction in future measurement-model work, but do not
promote the diagnostic as an accuracy fix. The larger unresolved question remains
which physical signal each tracked frequency curve represents and whether its
shape matches the assumed satellite carrier model. Reliable short-window sub-km
accuracy is still unresolved.
