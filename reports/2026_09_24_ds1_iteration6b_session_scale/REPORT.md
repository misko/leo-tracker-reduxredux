# DS1 iteration 6B: hierarchical session-scale ablation

Iteration 6B re-ranked the unchanged iteration-4 exact candidate union using
reference-free exact supports. It jointly fit bounded per-NORAD causal phase
rates, per-track CFO, a common fractional Doppler scale, and six
zero-mean shrinkage-regularized session deviations. Both scale priors were
fixed at 500 ppm and every scale was guarded at ±2000 ppm.

Iteration 6B is rejected and nonportable. All 17 candidate fits stopped with
`TOTAL NO. OF F,G EVALUATIONS EXCEEDS LIMIT`; therefore no provisional loss or
coordinate is accepted, despite no scale reaching its guard.

| Group | provisional exact loss | matched rate-only exact loss | delta | converged | guard |
| --- | ---: | ---: | ---: | --- | ---: |
| 20260921_00 | 0.037982 | 0.039190 | -0.001208 | no | clear |
| 20260921_16 | 0.077177 | 0.077507 | -0.000329 | no | clear |

The displayed coordinates and post-seal values are descriptive artifacts of a
rejected run. The next work is analytic gradients or a block-coordinate solve
for rates and session scales; simply increasing the evaluation budget would
not resolve the optimizer failure mode.

`evaluate_postseal.py` introduces the reference only after contract and
portability validation and writes JSON, CSV, and PNG outputs.
