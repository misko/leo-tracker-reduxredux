# Reusing the fractional-epoch center score

Reusing the completed integer GLRT score for the middle of the five-cell fractional-epoch lattice reduced **held median wall time from 23.29 to 22.49 ms**. The 20 ms median gate was unmet. In the primary cohort, fractional-stage CPU fell 12.4% and total detector CPU fell 3.2%. The control included reusable CI16 preparation and ordered fractional interpolation. [Protocol](PROTOCOL.md) · [Frozen source and cohort](source-holdout-lock.json)

| Warm x86 replay, 30 calls per build per cohort | Parent | Center score reuse |
| --- | ---: | ---: |
| Held median local authenticated CI16 to candidates | 23.29 ms | 22.49 ms |
| Held p90, same boundary | 27.35 ms | 26.48 ms |
| Held calls at or below 20 ms | 1 / 30 | 0 / 30 |
| Held detector CPU | 665.90 ms | 644.87 ms |
| Held fractional-epoch CPU | 242.02 ms | 212.12 ms |
| Companion median local authenticated CI16 to candidates | 23.73 ms | 21.80 ms |
| Companion calls at or below 20 ms | 9 / 30 | 11 / 30 |

The held cohort contains four DS26 and two DS29 visits selected by the prespecified input hash. Six other admitted visits form the companion cohort. Four original capture exclusions remain in the roster. Each admitted visit exercised both physical receivers on five alternating warm pairs. Warm local mmap and SHA-256 verification are included in wall time. Original archive decompression, hardware acquisition and downstream positioning fall outside that clock. [Qualification](qualification.json) · [DS26 per-call evidence](DS26-0036-host.json.gz) · [DS29 per-call evidence](DS29-0082-host.json.gz)

The final integer call already computes the middle lattice cell's exact and rolled-template scores at the same epoch, acquired CFO and support. The edit uses those stored fields only after final GLRT completion, with the ordinary 16-frame budget, acquisition starting at frame zero, and both experimental support modes disabled. The original scorer remains the fallback for other geometries. The four neighboring cells and continuous refinement still run. Every canonical receiver payload matched the parent, including candidate ranks, negative scores and gates. Empty and seeded Gaussian controls emitted zero positives. Weak and alias-planted controls matched exactly in both bands. [Native build receipt](build-receipt.json)

## Partial detector replay through position

The two fresh clock and offset fits substituted eight DS26 and four DS29 measured candidate visits and used the remaining authenticated ordinary factors. The scientific factors, Graph digest, causal catalogue and offered region matched the ordered-fractional parent. Both arms preserved all published and diagnostic fields.

| Recording | Fresh + archived valid visits | `c = 0` error | Fitted `c` error | `c = 0` / fitted Doppler RMS |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 + 6,757 | 0.654 km | 0.739 km | 232.44 / 209.30 Hz |
| DS29-0082 | 4 + 4,864 | Withheld | Withheld | 260.24 / 214.02 Hz, forced diagnostics |

DS29 withheld for weak held-track support. The stage and position charts preserve their separate timing and geographic boundaries. [Position receipts](position-receipts.json) · [Evidence seal](prediction-lock.json)

The detector qualification entry point is `tools.pipeline_eval.qualification.glrt_center_cell_eval`. Use `freeze`, `build`, and the two recording IDs with the same local `--work`, `--ordered-work` and `--prepared-work`. For each fresh position fit invoke `tools.pipeline_eval.qualification.glrt_center_cell_position` with that `--work` and `--case`, then use the same command without `--case` to package. Standard screening figure IDs are `glrt_center_cell` and `glrt_center_cell_position`.
