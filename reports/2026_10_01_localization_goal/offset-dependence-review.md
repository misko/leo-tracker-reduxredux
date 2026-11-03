# Shared offsets do not consistently outperform calibrated marginal uncertainty

The shared-offset model wins only4/12excluded-dataset scan comparisons against
a separately calibrated independent-offset control. It loses allfour DS10
comparisons. Do not promote a common-offset dependence model into geographic
fitting on this evidence.

There is a more consistent marginal-model result: the independently integrated
offset model improves over the preceding calibrated wrapped-Cauchy candidate
model on12/12scans, by an equal-scan average0.16490nats per candidate group.
That motivates investigating per-track uncertainty weighting, not a claim of
improved location accuracy.

## Models and controls

Let B_g(delta) be the existing normalized candidate-set likelihood ratio when
all predictions in a track are shifted by delta. Use the conditional Student
offset distribution from the training-only fit, centered at the GLS offset.

    shared track likelihood ratio = E_delta [ product_g B_g(delta) ]
    independent control           = product_g E_delta [ B_g(delta) ]

The first control uses exactly the shared model's intrinsic noise and signal
probability, isolating the dependence assumption while preserving single-group
marginals. A second control calibrates those parameters independently on the
same donor scans. This avoids rewarding the shared model solely because a
control's parameters are poorly chosen.

Calibration uses a fixed grid of intrinsic Cauchy scales10,20,35,50,75,100,150Hz
and probabilities .7,.85,.94,.98,.995. Maximize donor mean log density per group,
weighting each scan equally. Each target dataset is excluded from its parameter
selection: eight donor scans and four target scans per fold. States, identities
and conditional offset distributions are fixed; no GPS or geographic refit.

| Target excluded from calibration | Shared scale / probability | Independent scale / probability | Shared minus separately calibrated control (nats/group) |
|---|---|---|---:|
| DS9 | 35Hz / .94 | 10Hz / .94 | +0.02182 |
| DS10 | 35Hz / .94 | 20Hz / .94 | −0.03772 |
| DS11 | 35Hz / .94 | 20Hz / .94 | +0.03814 |

Across12scans, shared offsets gain on8/12against the identical-parameter control
(mean+0.02938nats/group), but only4/12against the separately calibrated control
(mean+0.00741). The latter mean is dominated by a favorable DS11-F018 result.
The DS9-target independent control reaches the10Hz lower grid edge. Its optimum
is unresolved; the comparison is not against a fully optimized control.

![Excluded-dataset predictive comparisons](offset-dependence-transfer-v2.png)

## Numerical verification

All526tracks and7933single-prediction candidate groups were joined from sealed
inputs, checking per-track counts and median residuals. Integrals operate on
the frequency-alias circle, with the Student offset density wrapped onto it.
An analytic power-law bound controls omitted wrapped-prior copies. Piecewise
Gauss-Legendre quadrature splits at every candidate peak and near its intrinsic
width, as well as across the prior's scale. Log-domain evaluation prevents
underflow when multiplying many group likelihood ratios.

Three tests verify normalization/single-group identity, coherent versus
incoherent residuals with equal marginal predictions, and refinement of a
narrow distant mode. Nine checks establish parity between the grid evaluator
and the original integrator. The initial fixed-parameter numerical audit passes
526/526tracks in7.01seconds.

The first calibration attempt stopped before producing rankings because one
10Hz case differed by1.48e-6log units after32-point refinement, above the1e-6
gate. The preserved v2 adds64-point refinement with unchanged parameter grid
and tolerance. All3682track-scale checks then pass; largest final difference
is8.95e-7. This is numerical agreement, not a formal quadrature error theorem.
The successful full grid takes49.07seconds offline. No localization runtime
claim follows from that duration.

## Next step

Resolve the independent control's lower noise boundary using donor-only
calibration, then verify a differentiable per-track marginal predictive model
before a bounded geographic pilot. Both the GLS offset and its uncertainty
depend on state and identity; their derivatives must be retained. Do not just
add offset variance to the old calibrated Cauchy scale, which already described
total residual error. The raw common-mode covariance is still an explicit
assumption not identifiable from contrasts alone.

These are previously exposed development recordings. This result establishes
neither independent-recording generalization nor geographic or uncertainty
target achievement. The original64scan baseline remains unchanged. NoRF,
new localization fits or production changes were performed.

Evidence: `offset-candidate-groups-v1.json`,
`shared-offset-integral-audit-v1.json`, `offset-dependence-transfer-v2.json`,
source bindings and SHA256 sidecars. The stopped v1 runner is retained.
