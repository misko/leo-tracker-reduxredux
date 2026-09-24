# DS1 one-hour full-observation method comparison

## Result

The bounded benchmark completed all **64/64** inference tasks with no failures.
It used only DS1 TRAIN recordings, every qualified observation in each selected
scan, and no within-track holdout. The Sausalito reference
(`37.84903264307456, -122.4856541910174`) was added only after each inference
artifact and SHA-256 seal had been validated.

The original 3,084-task design was computationally unsuitable: baseline was
unnecessarily scoring 41 timing offsets and then retaining only tau zero. The
zero-only baseline correction reduced a representative 121-cell Reno run from
more than two minutes to 6.3 seconds. The replacement protocol fixes four
views before inference: the first complete scan and first six scans from each
of the two TRAIN groups, evaluated from both the Sacramento 250 km and Reno
500 km priors. Timing methods use a predeclared +/-2 s grid at 0.5 s spacing.

| Method | 1-scan median error (km) | 6-scan median error (km) | 6-scan range (km) |
|---|---:|---:|---:|
| Baseline | 24.386 | 13.109 | 10.422-13.682 |
| Causal per-NORAD orbit rate | 24.386 | 13.109 | 10.422-13.682 |
| Shared global time | 18.262 | **6.009** | **4.999-8.913** |
| Global time + per-NORAD orbit rate | 18.262 | **6.009** | **4.999-8.913** |
| Regularized per-scan time | 18.262 | **6.009** | **4.999-8.913** |
| Independent per-track time | 12.052 | 11.598 | 6.525-13.444 |
| Soft association | 11.598 | 11.598 | 6.525-13.444 |
| Soft association + global time | **10.145** | **6.009** | 4.999-17.553 |

Six scans materially improve the stable methods. Shared global timing lowers
the median error from 13.109 km for baseline to 6.009 km, a 54% reduction. Its
best arm is 4.999 km. Regularized per-scan timing selects the same grid cells
in this small comparison, so the added scan corrections do not improve the
position. Soft association plus global time reaches the same median but has a
17.553 km worst arm, making it less stable across the two recording groups.

Per-NORAD rate fitting substantially lowers its own full-observation RF loss,
but it is applied only to RF-selected geographic finalists in this bounded
runner. It therefore does not move the selected cell: orbit-rate-only matches
baseline positions, and global-time-plus-rate matches shared-global-time
positions. This experiment supports the nuisance fit as an RF refinement,
not yet as a positioning improvement. Runner objective scales differ between
hard and soft methods and must not be ranked as one universal score.

## Limits

This is a **12.5 km final geographic grid screen**, so the 4.999-6.009 km
errors are cell-centre outcomes rather than sub-grid accuracy claims. The
one-scan and six-scan views overlap and are paired development examples, not
independent validation samples. Validation and test partitions remain
untouched. The result identifies shared timing as the most useful next arm; a
finer local grid around its RF-selected basin is required before assessing
sub-kilometre performance.

## Reproducible artifacts

- `one-hour-inference-manifest.json` and its SHA-256 seal define all 64 tasks.
- `artifacts/one-hour/` contains the sealed inference outputs.
- `post-seal-evaluation/one-hour-post-seal-evaluation.json` is the complete
  machine-readable evaluation.
- `post-seal-evaluation/one-hour-post-seal-evaluation.csv` is the flat table.
- `post-seal-evaluation/one-hour-post-seal-evaluation.png` is the comparison
  figure.
