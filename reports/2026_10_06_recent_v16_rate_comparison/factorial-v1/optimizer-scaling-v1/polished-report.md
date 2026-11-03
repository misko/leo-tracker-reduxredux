# Matched Fisher polish after optimizer scaling

This is a post-hoc extension of the equal-budget scaling pilot, motivated by the scaled c = 0 solution narrowly missing the original KKT tolerance. All four optimizer/RF combinations are offered up to 10 additional seconds of Fisher polishing, stopping immediately if already converged. The original 60-second pilot remains unchanged. No tolerance, objective, observation, prior, satellite set, or search-boundary change is made.

| RF | SLSQP scaling | KKT before | KKT after | Loss change | Position error m | Converged | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fitted-c | ordinary | 297.933 | 4.17555 | -6.787916 | 4000.0 | False | True |
| fitted-c | per-window | 0.000576725 | 0.000576725 | +0.000000 | 4000.0 | True | True |
| zero-c | ordinary | 227.835 | 17.5364 | -38.202353 | 4000.0 | False | True |
| zero-c | per-window | 0.00159587 | 0.00122081 | -0.000000 | 4000.0 | False | True |

This targeted single-scan optimizer study cannot establish a general localization improvement. Boundary solutions are constrained results, not unconstrained minima. Run `polish_scaled_trial.py` after the four `scaled_optimizer_trial.py` outputs exist. Receipts preserve both before and after diagnostics and source hashes.
