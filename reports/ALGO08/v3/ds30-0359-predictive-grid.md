# Predictive bias marginalization on the saved DS30-0359 grid

The bias-marginalized predictor saved **0.286 CPU s (19.2%)**
across 356 matched posterior calls in the current combined DS30-0359
worker. The alternate grid changed 12 scores by at most
**7.276 × 10⁻¹²**, kept both sampled minima and published all eight
PNGs byte for byte. The terminal, both calibration fits, assignments
and position path matched the previous completed publication.
[Frozen protocol](ds30-0359-predictive-grid-protocol.md) ·
[Same-input control](ds30-0359-combined.md)

The original current route scored all 179 positions and used the
ordinary predictive factor inside its native exact geometry and
design-template grid. Its receipt recorded **1.542 CPU s** in the
predictor. Each paired arm evaluates **1,133 predictive points in
63 tracks**. The curved posterior widths are **188** at fixed zero
and **189** with fitted `c`. No whitening column qualified for
zero-prefix elimination. The active reduction analytically integrates
all 63 Gaussian track biases while retaining all rows, the same
posterior support and the same normalization. The earlier 0138 study
measured separate predictor pairs while continuing to publish the
ordinary scalar. The earlier 0008 publication used a different dense
route. [Existing reduced kernel](grid_predictive_reduction.py) ·
[0138 diagnostic](exact-grid-0138.md) · [0008 reduction](grid-predictive-reduction.md)

| Boundary | Wall s | CPU s |
| --- | ---: | ---: |
| Ordinary predictor on the same posteriors | 1.490001 | 1.489644 |
| Reduced predictor, including its residual | 1.204842 | 1.203927 |
| **Paired saving** | **0.285159** | **0.285716** |
| Common grid work including observer | 2.201149 | 2.201417 |
| Ordinary grid estimate within the paired worker | 3.691150 | 3.691061 |
| Reduced grid estimate within the paired worker | 3.405991 | 3.405345 |
| Actual two-kernel grid | 4.895992 | 4.894988 |
| Actual two-kernel worker through exit | 17.847101 | 17.844020 |
| Local admission and isolated import smoke | 0.606000 | 0.557448 |

The 356 direct calls alternate which predictor runs first and share
one checked exported posterior per arm-location. The reduced result
flows through the actual likelihood and regular publisher. The two
grid estimates subtract the other predictor's measured interval and
each retain the observer costs. This yields a **7.74%** same-grid
CPU estimate. Transferring the measured wall saving to the prior
17.171 s worker would leave **16.885 s**, about **0.912 s** above
half the installed 31.947 s clock. The dual-clock worker is a
diagnostic measurement.

| Calibration | Horizontal error | Conditional RF RMS | Ordered owners | Changed grid scores | Sampled minimizing index |
| --- | ---: | ---: | ---: | ---: | ---: |
| `c = 0` | 592.489 m | 115.604323 Hz | 3,640 | 7 | 0 |
| Fitted `c` | 666.751 m | 115.588647 Hz | 3,640 | 5 | 1 |

Both arm endpoints and RF summaries are exact relative to the
ordinary comparison. Fitting `c` still lowers conditional RF RMS
by **0.0157 Hz** while increasing horizontal error by **74.262 m**.
The reconstructed ordinary numerical grid matches the archived
digest. The candidate retains exact coordinates, order, failure
maps, endpoint replay and sampled minima, with every score inside
the frozen `1e-5` absolute tolerance. The official readback matches
the actually paired alternate grid. The graph, path and all eight
encoded and independently decoded PNG hashes match the prior worker.
The 356 candidate calculations used 708 native projections and the
original 356 design assemblies.

The fully resident job retained the original full-20 ms detector
packet, 25 km offer, causal cutoff and 47 local snapshots. The worker
ran once with CPU 2 nice 15, best-effort I/O 7 and one numerical
thread. No waveform, backing catalogue or new collection ran. The
recording was used in the prior combined cohort. This transfer is
separate from the three blind results.

Timed commit `ba35889323ad262c3f0416c0dfbd70cf8e92c13b`.
Prediction seal SHA-256
`ee53df0698607d8101bbf7bdded1425bf2b2e443727cc6f3fdf0e4d598492d4d`.
[Driver](ds30_0359_predictive_grid.py) · [Scorer](ds30_0359_predictive_score.py) ·
[Machine receipt](measurements/ds30-0359-predictive-grid.json.gz),
uncompressed SHA-256 `4404ceb1d587afee549978f09411c7a90810311384a873865ea1cab5b2a4c85c`.
