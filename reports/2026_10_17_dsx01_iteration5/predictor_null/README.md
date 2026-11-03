# Frozen-predictor conditional controls

The blocked interpolation predictor has substantially more held temporal
alignment than these frequency-permutation controls. The requested-window
half-forecast result does not. This is a bounded diagnostic on two already
fitted-c production predictors, not a fitted-c/c=0 comparison or a new model.

| Frozen predictor / held scope | Actual assigned | 32-control mean | Control range |
|---|---:|---:|---:|
| First-half discovery, whole held half | 165/1982 | 134.16 | 117–156 |
| First-half discovery, requested held windows | 2/84 | 4.28 | 0–9 |
| Alternating blocks, whole held set | 795/1909 | 201.00 | 181–238 |
| Alternating blocks, requested held windows | 66/80 | 6.88 | 3–12 |

![Frozen prediction controls](conditional-controls.png)

Method: preserve each frozen predictor's exact bank, geometry, calibration,
visibility, q and 125 Hz frequency width. First replay every original full-array
assignment exactly. Then shuffle only held CFO values within receiver/channel
groups, using 32 declared-seed permutations. This preserves each lane's held
marginal CFO distribution but destroys temporal alignment. Training rows and
their assignments remain unchanged in every control. No fitting, candidate
discovery, model selection, new orbit propagation or station-coordinate use.

The cohorts, training spans and learned banks differ between the two predictors.
This is not an isolated causal comparison of interpolation versus extrapolation,
and it is not a calibrated discovery false-positive rate or proof of satellite
identity. Full-data original labels are not used to select these controls.
Requested held denominators differ (84 versus 80) and must not be substituted
for all 693 DSX01 observations or all 15 windows.

`run.py` writes source hashes, actual density replay checks, per-replicate counts
and full-held NLL. The per-scope actual NLL is in `receipt.json`; only full-held
NLL is retained for each shuffled replicate. Two component tests check lane
distribution preservation, unchanged training, reproducibility and shape/mask
validation. `plot.py` renders saved results without repeating scientific scoring.
These controls support proceeding to matched training-only model comparisons;
they do not complete the generalization or localization objective.
