# Iterating the exact Gaussian profile with fixed owners

Repeated exact site reprojection did not recover localization accuracy. All four fits reached the original 20 m convergence threshold after **two or three accepted steps**. The converged points lay just **17–214 m** from the earlier one-step proposals, and all four remained outside the allowed 250 m of added error relative to installed v3. This isolates the one-step geographic linearization on these saved inputs. The frozen uncertainty and phase model remains a possible source of the kilometre-scale discrepancy. [Frozen follow-up](centre-oracle-iterative-protocol.md) · [One-step controls](centre-oracle-step.md) · [Summary](measurements/centre-oracle-iterative-summary.json) · [Full traces](measurements/centre-oracle-iterative.json.gz)

The repeated saved captures reproduced every original curved and predictive ID, satellite, role, signed alias, each causal phase mean, the prior model and both archived arm readouts. The optimizer received no endpoint or geographic reference. For each site coordinate, the original causal orbital projection and all nuisance columns were recomputed. The optimizer analytically refit the Gaussian receiver, phase, shape and track-bias terms with the original fixed Graph noise and priors. Its objective was one consistent profiled sum of whitened innovations and unit-normal nuisance penalties. Both arms started at the supplied centre. The trial recomputed the residual Jacobian at every iterate, used the original bounded trust region and convergence threshold, and accepted only a reduction in that exact surrogate objective. The causal phase expansion stayed fixed while every phase coefficient was refit. [Numerical implementation](centre_oracle_iterative.py) · [Input verification](centre_oracle_iterative_trial.py)

## Geographic errors after sealing

All paired entries are fixed-zero / fitted \(c\).

| Saved case | Installed v3 error km | Same-packet published error km | One-step error km | First damped step error km | Converged error km |
|---|---:|---:|---:|---:|---:|
| Weak DS30-0016 | 1.644 / 1.661 | 1.311 / 1.694 | 2.871 / 3.603 | 2.890 / 3.594 | **2.864 / 3.603** |
| North | 0.106 / 0.141 | 0.390 / 0.121 | 2.073 / 2.151 | 8.188 / 8.289 | **2.226 / 2.327** |

Weak moved 17 / 91 m from the frozen one-step proposal to its local optimum. North's first damped step used the full 5 km west trust allowance. Two further steps brought it within 214 / 176 m of the one-step proposal. The remaining tested full steps were 3.3 / 4.0 m on weak and 6.1 / 3.1 m on North. The failure was observed after the convergence check, with all points inside the original squares and none of the searches hitting the six-iteration cap. [Geographic scorer](centre_oracle_iterative_score.py)

## Objective and calibration

The exact original robust check evaluated the centre, first accepted point and final point at the same causal expansion, with unit family powers. The centre readouts matched the first study exactly. These scores were recorded after optimization and had no effect on the path. The more complete archived position also uses its own refreshed phase and robust family state.

| Case and arm | Gaussian profile, centre → first → final | Released robust check, centre → first → final | One-step robust readout |
|---|---|---|---:|
| Weak, fixed-zero | 100.665 → 97.747 → 97.746 | 510.629 → 506.823 → 506.830 | 506.828 |
| Weak, fitted | 99.288 → 96.792 → 96.792 | 518.584 → 516.016 → 516.022 | 516.017 |
| North, fixed-zero | 539.529 → 433.868 → 418.555 | 682.627 → 589.388 → 561.956 | 559.614 |
| North, fitted | 513.155 → 433.563 → 415.874 | 644.892 → 600.645 → 582.160 | 578.966 |

The converged fitted coefficients were **−1,468 Hz/GHz** on weak and **−890 Hz/GHz** on North. Across both calibration arms the absolute fitted phases covered **−2.083 to −0.193 s** on weak and **−2.061 to +0.385 s** on North. Every accepted phase coefficient and RF calibration value is in the traces. Reducing the Gaussian objective slightly beyond the first step on weak raised the released robust objective, and every converged robust score was slightly higher than the corresponding one-step endpoint's. Iterating the site update therefore tests the local optimum of the frozen surrogate. It does not test refreshed phase expansion or another treatment of nuisance uncertainty. [Profile and exact score traces](measurements/centre-oracle-iterative.json.gz)

## Cost

Weak paid **9** exact Gaussian profile evaluations per arm and North paid **12**, including centre, derivative probes and accepted trials. There were zero rejected trials on the saved inputs. Paired profiling, preparation, and the six charged exact robust checks took **15.62 ms** on weak and **29.36 ms** on North, versus **6.45 ms** and **10.68 ms** for the earlier complete paired one-step diagnostic. The independently charged original solver replays needed **3.185 s** and **3.920 s** to provide the owner oracle. No waveform was read and no grid, figure, or new publication was produced. Eight focused tests passed, including a nonlinear control that exercises rejected trials and a stationary-centre control. [Tests](../../../tests/pipeline_eval/test_centre_oracle_iterative.py)

Reproduce with the one-step environment and pinned saved requests. Run `centre_oracle_iterative_trial.py CASE NEW_OUTPUT` once on each case, then `centre_oracle_iterative_score.py DIRECTORY NEW_SUMMARY NEW_FULL` after both blind outputs seal. [One-step environment](centre-oracle-step.md) · [Follow-up bindings](centre_oracle_iterative_trial.py)
