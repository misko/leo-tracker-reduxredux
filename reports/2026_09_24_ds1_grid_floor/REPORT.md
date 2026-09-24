# DS1 one-hour grid-floor analysis

This review reads 64 sealed inference artifacts from the DS1 one-hour matrix. The Sausalito reference is used only to identify the two reported error values below; the grid and basin findings use the inference artifacts' coordinates, traces, and RF objectives.

## Finding

All 32 artifacts that expose a geographic trace select a point from the nested 12.5 km lattice. Every selected coordinate matches a traced geographic candidate, and every selected east/north coordinate is an integer multiple of the lattice step (largest numerical residual 0). 25 selections are directly at the final level; 7 retain a coarser candidate because the score did not monotonically improve with subdivision. This establishes a resolution ceiling for those outputs, not a measured localization floor.

The 4.999 km value occurs 5 times at (37.81168388, -122.51733708). It is a repeated selected lattice point, so it is consistent with grid quantization. It does not show that the RF optimum is exactly that far from the reference.
The 6.009 km value occurs 12 times at (37.90285995, -122.49167359). It is a repeated selected lattice point, so it is consistent with grid quantization. It does not show that the RF optimum is exactly that far from the reference.

Across all methods, the 64 runs collapse to 16 exact coordinates. None of the 32 matched prior pairs selects the identical coordinate; their method-level median separations range from 3.54 to 12.81 km. Prior changes therefore select different basins. Raw RF objectives are not compared across methods because their losses use different definitions and scales.

## Basin evidence

The final lattice contains a median of 13 distinct sampled cells per traced run. The median best-versus-second sampled-cell relative gap is 0.0862; the range is 0.00654 to 0.275. In 7/32 traces, the final-level winner is not the selected global trace winner. No final winner has all four cardinal neighbours sampled (26 have two and 6 have three). The traces therefore do not prove even an interior local minimum, much less a global optimum.

## Recommended reference-free refinement and gate

Retain all coarse basins within a measured within-method RF score margin. Re-profile dynamic associations and nuisance parameters on a symmetric 5×5 stencil at 3.125 km, then 0.78125 km around each surviving minimum. Start from both prior-seeded locations whenever they disagree. Emit a single coordinate only when it is an interior local minimum, wins resampled independent observation groups at least 90% of the time, and beats every retained basin by more than the resampling-derived objective noise. Otherwise emit the modes and their spread as an ambiguity result.

The complete per-artifact lattice checks, basin margins, coordinate clusters, and pairwise prior/method distances are in `analysis.json`.
