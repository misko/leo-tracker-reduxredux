# DS1 causal per-NORAD orbit-phase-rate: bounded feasibility report

The historical orbit-phase nuisance is now reproduced on DS1 with the required
physical convention: each NORAD receives one causal rate in seconds/hour,
multiplied by the TLE epoch age, while Earth rotation stays fixed at the
chosen receive-time plus global tau. This is neither a global clock correction
nor a per-scan epoch parameter.

The direct causal-SGP4 implementation is numerically sound. All four bounded
runs converged under L-BFGS-B and passed the predeclared 0.2 Hz exact replay
gate by more than four orders of magnitude. The machine-readable rows are in
summary.json and their complete per-pair inputs/results are the four
case/prior JSON files in this directory.

| DS1 case / prior | frozen pairs | final position error | ordinary TRAIN loss | causal-rate TRAIN loss | held capped RMS |
|---|---:|---:|---:|---:|---:|
| train_20260921_00_1 / Sacramento | 4 | 40.407 km | 0.143560 | 0.084338 | 286.32 Hz |
| train_20260921_00_1 / Reno | 1 | 39.999 km | 0.143314 | 0.083966 | 285.68 Hz |
| validation_20260922_08_1 / Sacramento | 4 | 0.961 km | 0.033702 | 0.021644 | 129.18 Hz |
| validation_20260922_08_1 / Reno | 1 | 1.412 km | 0.033704 | 0.021927 | 129.68 Hz |

The rate nuisance consistently improves its local TRAIN criterion and has
reasonable within-track held frequency prediction. It has not, in these
bounded subsets, recovered a new position: the selected point remains the
ordinary shared-time point. The TRAIN singleton is about 40 km wrong; the
validation singleton begins near the reference point. Therefore these results
do not support a sub-kilometre DS1 claim.

The evaluation was kept deliberately narrow. Each run evaluates the
deterministic best ordinary-TRAIN pairs from an already sealed DS1 shared-time
pair trace; it is not a full geographic-pair traversal. Reference position was
introduced only after inference. Randomized held rows remain from the same
tracklets and NORADs as TRAIN, so they measure within-track prediction rather
than future-satellite generalization.

A direct full evaluation is feasible but costly: observed exact-node
L-BFGS-B runtime is approximately 20–25 seconds per typical pair, with one
four-pair TRAIN run taking 91 seconds. A 165-pair singleton arm is therefore
on the order of an hour. A DS1-wide result requires a predeclared parallel
per-arm launch that completes both priors and all frozen cases, retains
failures, and uses no reference/error result for model selection.

The earlier blind fixed-assignment transfer remains a negative control. Its
sealed report in ../2026_09_23_train_orbit_uncertainty_design/FINDINGS.md
recorded 12.025/12.029 km first-six and 4.764 km second-six position errors
despite held frequency improvement. It should not be substituted for this
matched DS1 arm.
