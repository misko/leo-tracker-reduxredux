# Chronological historical test of symmetric orbit-revision uncertainty

Use existing causal older-minus-current Doppler curves and conditional residual
exports. No new orbit retrieval or propagation. Fit only DS7/DS8 training
values; evaluate DS9 held values. Verify DS7/DS8 capture times precede DS9.
These historical residuals use their original fitted geometry/associations and
are not an independent single-scan positioning benchmark.

Remove each track's training mean from residual and revision direction, as in
the earlier revision-transfer diagnostic. Hold those centers fixed on held
rows. This is a plug-in residual prediction experiment, not a fully integrated
position/CFO likelihood. Group tracks by dataset/session/conditional NORAD,
sharing one revision coefficient across receivers and RF bands. Keep all rows.

The coefficient has discrete support0,+/-0.01,+/-0.03,+/-0.1,+/-0.3,+/-1.
Within each nonzero magnitude, sign probabilities are equal. Learn six magnitude
weights by maximum likelihood on donor training source groups, starting uniform,
using EM with maximum10000 iterations and max weight change<1e-10. This prior
is explicitly discrete and symmetric, not a Gaussian quadrature or a calibrated
orbit covariance. Errors retain independent Student-t4/100Hz densities.

Matched control: replace each direction with its training-fitted linear trend,
rescaled to match the full direction's training RMS. If the fitted slope is
zero, use the positive centered-time direction with the same RMS. Fit the
control's weights independently on exactly the same donor training groups.
This tests whether the actual orbit-revision shape helps beyond linear drift
with identical scale and coefficient support. The third arm is beta=0.

Seal weights and convergence before scoring DS9. For each DS9 source, update
coefficient probabilities with its own training observations; evaluate held
prediction by the joint/training mixture-normalizer ratio. Report total gains
and per-source gains per held row. Numerical ties within1e-10 nats/held-row count
as ties. Keep unchanged-direction sources as explicit no-ops. Advancement
requires positive mean and median and a majority of wins over BOTH controls
among sources having nonzero training revision RMS, plus nonnegative total gains
over all DS9 sources. A failure stops this discrete prior before DS11 fitting.
No reference position/error, DS11 positions, new IQ or RF collection. One
single-thread process under90seconds. Retain engineering failures explicitly.
