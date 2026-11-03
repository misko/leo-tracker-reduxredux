# Equal budget optimizer scaling pilot

This pilot tests R100-02 original measurements, T1-AT scoring, cones off. Ordinary SLSQP and per-window loss-scaled SLSQP each receive 60 seconds from the same saved baseline solution in each RF arm. The objective and gradient are divided by the number of associated windows only inside the latter solver. This leaves the exact minimizer unchanged but changes numerical scaling and effective stopping behavior. All final convergence checks use the original unscaled loss.

Both arms retain their original observations, satellites, priors, timing limits, and 4 km boundary. Results are saved separately from the main experiment. This is a targeted difficult-case pilot, not evidence of a cohort-wide improvement.

4 of 4 planned trials saved.

| RF | Optimizer | Before error m | After error m | Loss change | Unscaled KKT | Converged | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fitted-c | ordinary | 4000.0 | 3995.3 | -393.724546 | 297.933 | False | False |
| fitted-c | per-window | 4000.0 | 4000.0 | -293.346323 | 0.000576725 | True | True |
| zero-c | ordinary | 4000.0 | 3996.6 | -356.047255 | 227.835 | False | False |
| zero-c | per-window | 4000.0 | 4000.0 | -356.026295 | 0.00159587 | False | True |

Run `scaled_optimizer_trial.py` using the scientific Python environment. Every receipt records input, baseline, and implementation hashes. Lower loss is not automatically lower position error, and unconverged points are not minima.
