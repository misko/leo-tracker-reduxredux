# DS7 wave-three residual audit

This is a reference-free, unscored audit of the frozen first-eight independent
and joint predictions. It reads the frozen candidate banks and qualified sealed
responses; it does not read pose, reference coordinates, raw IQ, or scores, and
it does not fit a geographic model.

For every eligible track, candidate responsibilities and the stationary offset
are fitted on training observations only. Held predictive density is then
computed at those fixed offsets and weights as
`logsumexp(train + held) - logsumexp(train)`. Training-MAP candidates are used
for both training and held RMS, so held samples never select a candidate or an
offset. Joint and independent predictions use identical masks and banks.

## Main evidence

The shared-position joint fit is worse than the independent fits on both sides
of the partition. Across 486 tracks, its total training score is 713.85 nats
lower and its fixed-parameter held predictive density is 432.55 nats lower.
Pooled RMS rises from 426.05 to 434.91 Hz on training observations and from
418.18 to 427.78 Hz on held observations. Seven of eight recordings lose held
predictive density; only the 5 MHz sixth recording improves, by 2.16 nats.

The eighth recording contributes 342.13 nats of the training loss and 183.29
nats of the held loss. Its most influential track alone contributes 134.03 and
120.72 nats respectively, with held RMS worsening by 600.08 Hz. The next four
largest training influences are also confirmed by held losses, which argues
against a training-only fluctuation.

Candidate ambiguity is not the dominant aggregate failure. Median training-MAP
probability is 1.0 and median effective candidate count is 1.0 for both models;
only 31 joint tracks have MAP probability below 0.9. This does not prove every
candidate identity, but the joint degradation persists where the training
posterior is highly concentrated.

Residual structure varies materially by receiver, channel, and RF. Under the
joint prediction, receiver/channel RMS ranges from 331.78 to 579.53 Hz. Slopes
range from +88.27 to -193.19 Hz per normalized recording. The 11.210 GHz group
has 1153.76 Hz RMS and a -826.71 Hz normalized-time slope; 11.460 GHz has
751.98 Hz RMS, -305.17 Hz mean, and a -589.60 Hz slope. The 10.960 GHz group
also has a -624.19 Hz slope. Time is normalized as `time_s / recording_duration`
within each recording before the slope regression.

## Scientifically justified next correction

The next bounded model test should add a training-fitted, shrinkage-controlled
linear time-slope nuisance for each recording and receiver/channel group, while
retaining the per-track stationary offset. The slope basis must use the declared
normalized recording time, be constrained to prevent a common slope from
absorbing geographic Doppler, and be evaluated with the same fixed-parameter
held likelihood before any position comparison. A frequency-group formulation
is also defensible, but the receiver/channel grouping is the narrower first
test because it follows the acquisition structure directly.

This recommendation comes from repeatable residual slope and held-likelihood
patterns. It is not selected from position scores. A useful gate is improvement
in held predictive density across recordings rather than improvement driven by
the single worst track or the eighth recording alone.

The complete per-track evidence, group summaries, and source hashes are in
`audit-v1.json`. The final analysis completed in 9.03 seconds under CPU1/BLAS1.
