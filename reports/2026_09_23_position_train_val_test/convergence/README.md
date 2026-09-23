# Original-16 optimizer convergence diagnostic

This changes only the Nelder-Mead evaluation cap at the three frozen basins. The observations, conditional candidate pools, integer ±5 s timing grid, seeds, objective, simplex, and tolerances are identical. Geographic truth was appended only after `inference.json` was sealed.

All basins converged within 53–67 evaluations, so a 150-evaluation cap removes the numerical stopping issue and 400 adds no change. The objective changes do not move every basin consistently: basin 1 0.314→0.275 km, basin 2 1.149→1.127 km, basin 3 6.215→6.710 km. This is a development-set numerical diagnostic, not validation of sub-300 m accuracy.

At the converged basin-1 point, the separate nuisance ablation changes legacy RMS from 202.596 Hz at 1 s to 199.644 Hz at 0.25 s, while timing-bound tracks fall only from 57 to 49. Fractional timing improves the development objective but leaves substantial nuisance-bound pressure.
