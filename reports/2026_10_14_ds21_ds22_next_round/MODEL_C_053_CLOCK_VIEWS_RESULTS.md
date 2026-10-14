# C053 matched clock-enabled channel views converge on the closer region

All six fits passed the unchanged stationarity checks. Each likelihood view received the same two saved full-band clock endpoints, original candidate bank, calibration frame, clock prior, original local disks, and 20-second/600-iteration budget per start. Each selected the earlier/closer region by its own training objective.

| Likelihood view | Selected error km | Selected objective | Selected NLL | Distant-start error km |
|---|---:|---:|---:|---:|
| CH1–8 | 10.055802 | 23693.894241 | 23351.163301 | 253.805010 |
| CH1–4 | 10.213730 | 16156.313863 | 15841.587435 | 253.283691 |
| CH5–8 | 9.600813 | 7168.150119 | 6906.543935 | 256.906138 |

The full-band result is slightly better than low-only but 0.454989 km worse than high-only. It does not meet the requirement to beat both halves or achieve sub-kilometer accuracy. Objectives from different likelihood views are not ranked against one another. The candidate bank, frame and starting states used all channels, so this is a conditional ablation, not an independent-discovery half-band benchmark.

The preceding fixed-endpoint audit found high-band likelihood preferred the distant full-fit endpoint. Here, allowing each high-only fit to adjust its own parameters reverses that preference: the closer high-only endpoint has objective 7168.150119 versus 7491.019368 for the distant endpoint. Thus the high-band disagreement at the full fits is not evidence that the high band intrinsically favors the distant location. The shared fitted parameters create a compromise that must be considered alongside association and starting-region search.

V1 stopped before any optimizer call because its no-projection check detected the original fitter's timing-boundary rescale. V2 explicitly records and applies that same rescale once per starting state. The distant state's largest timing-coordinate change is 8.6644e-10; its objective changes by 2.2948e-8 and NLL by 6.3017e-8, below the preset 1e-7 score gate. The closer state is unchanged. Geographic and calibration coordinates and all nuisance values are unchanged. The resulting identical seeds are supplied to every view, and the original convergence and feasibility thresholds remain unchanged. V1 is preserved.

Qualification uses 12 objective evaluations, including original/canonical checks. Full-view objectives and gradients reproduce the original receiver-clock model exactly at the canonical seeds, half likelihoods partition the full likelihood, and all final seeds pass the original no-further-projection gate. The run used six new optimizer calls and completed in 70.601 seconds. Three component tests and Ruff passed; tests include a timing-boundary case, significant score-change rejection, six matched calls, failure retention, no retry and blocked premature reference evaluation. Source commit `caf5211ca`.

Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-views-053-v2/`. Terminal SHA256 `6e8bdb33a7e040c1ea6e6df5d50ade5b3d7c810194cfad511c6ad6be4c53064c`; seal SHA256 `dd95395d31ba5c0118afad9dcae71316c8d4c616232528f908d657c190decbff`. Reference coordinates were joined only after all six outcomes and selections were sealed. No full-cohort promotion is made.

Next: expand the fixed-union clock model to the genuine original starting states from both source runs, retaining these accepted solutions as fallbacks. This tests whether the residual approximately 10 km error is a starting-basin limitation before adding more calibration parameters.
