# Next experiment: an explicit unassociated frequency-trend alternative

Design notes only: no implementation or geographic result is claimed here.
The frequency-contrast control must finish before this next experiment is frozen.
Its purpose is to let a poorly explained track contribute less geographic force,
which the soft cone's common 1% floor cannot do by itself.

## A compatible density

Use the same training anchor and contrast coordinates as the signal branch.
For the alternative, let frequency be an unknown constant plus a linear trend
and measurement noise. Eliminate the constant exactly. Conditional on a shared
inverse-gamma scale, use a zero-mean Gaussian slope with a declared scale and
Gaussian measurement noise. Marginalizing gives Student-t4 on contrasts with
scale D (sigma^2 I + slope_scale^2 t t^T) D^T. A rank-one update permits exact
quadratic forms and determinants without fitting a held-data slope. Full minus
training log density gives a normalized held prediction on the same coordinates.
This is an unassociated trend hypothesis, not proof of clutter or non-satellite
origin. No per-track free polynomial chosen from reference residuals is allowed.

For a normalized signal/background mixture, the geographic derivative equals
the signal branch derivative multiplied by its training responsibility when
the alternative is position independent. Unlike multiplying all satellite
candidates by the same cone floor, this can reduce a track's location influence.
It can also discard informative tracks or create weakly identified solutions;
better held scores alone will not establish better geography.

## Resolve catalogue mass before choosing mixture weights

The present control retains the old full-catalogue divisor while summing only
stored candidates. Its signal score must not be inserted unchanged beside a
normalized trend density and interpreted as a calibrated class probability.
Most omitted catalogue mass would otherwise alter the effective mixture weight.

A defensible bounded research comparison can explicitly condition on the stored
candidate bank and normalize signal prior weights within that bank, with a
precisely stated visibility rule and behavior when no candidate is visible.
That requires its own signal-only control before attributing changes to the
trend branch. The bank was selected using data, so even this conditional model
does not establish full-catalogue association probabilities or recover omitted
satellites. A full generative alternative instead needs a defensible normalized
model for those omitted hypotheses; none has been validated yet.

Do not freeze background probabilities or slope scales until the measure,
visibility conditioning, omitted-bank interpretation and numerical tests are
explicit. Do not tune them to exposed geographic errors. Report any declared
sensitivity arms separately, retaining every planned panel.

## Gates before location fits

- Independent matrix and rank-one density agreement; invariance to anchor and
  constant frequency shifts; density normalization and conditional normalization.
- Zero background weight reproduces the declared signal-only control, including
  gradients and held scores. Unit background weight has no geographic force.
- Analytic mixture gradients match finite differences, including a synthetic
  unsupported track whose influence falls as the alternative becomes likely.
- Changing held values or held candidate geometry cannot change training scores,
  mixture responsibilities, anchor selection or fitted parameters.
- Keep the same consecutive panels, starts, selection rules and numerical audit
  gates. Record effective signal responsibility and identifiability alongside
  location and held prediction; never silently remove low-responsibility tracks.

Only after these controls should receiver cones enter the mixture. Then require
one common receiver pose and cone pair throughout each scan, a continuous
trajectory per association, and an explicit unexplained alternative for cone
violations. Paired RX identity and reception/non-reception still need separate
validation before interpreting RX order as satellite travel direction.
