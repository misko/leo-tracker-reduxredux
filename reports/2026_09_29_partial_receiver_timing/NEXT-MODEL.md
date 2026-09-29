# Next modeling question: frequency contrasts and an unassociated-track branch

Status: design proposal only. No implementation, fit, or new accuracy result is
claimed. Finish the frozen timing sensitivity study before launching another
scientific batch. This proposal does not change its settings or outcomes.

The cone study identified a structural limitation: multiplying every candidate
of an unexplained track by the same constant factor does not reduce that track's
frequency-based position gradient. Receiver timing flexibility addresses a
different mismatch and has not established reliable short-window sub-km accuracy.
An explicit unassociated-track alternative is therefore worth testing, without
dropping detections or selecting tracks from geographic errors.

First isolate stationary frequency-offset treatment. For each track choose its
first training observation as anchor, and let D subtract that observation from
every other observation. Candidate predictions become D f(x), and observations
become D y. A shared-scale Student-t4 error with scale matrix S transforms to
Student-t4 with scale D S D^T. This removes an arbitrary constant offset exactly.
Training uses only training contrasts; held prediction is the full contrast
log density minus the training-contrast log density. The anchor must belong to
training, and held observations must never select it.

For the current zero-decay S = 100^2 I and n total observations, the anchored
contrast scale is 100^2 (I + 11^T), has dimension n-1, and determinant
100^(2(n-1)) n. These identities allow independent arithmetic checks. Compared
with profiling the offset, this changes the likelihood dimension and predictive
treatment of the offset; it is a new model, not a neutral replay of the old one.
It also removes the old weak absolute-offset penalty, which must be disclosed.

Required checks before a frozen geographic experiment:

- Invariance to constant frequency translations and to choosing another training
  anchor; no dependence of training scores/gradients on held observations.
- Independent matrix and closed-form contrast densities, plus a small numerical
  integration check over a flat stationary offset. Any measure/Jacobian constants
  must be explicit before comparing densities.
- Analytic geographic/timing gradients against finite differences and a normalized
  conditional held density with training-only candidate weights.
- Same records, candidate bank, position/timing bounds, starts and failure policy
  as the one-timing consecutive-panel baseline. Retain late DS9 eight and every
  planned panel. No geographic selection of initialization or hyperparameters.

Only after that control is established should an unassociated branch be added.
A possible background is a frequency trend with analytically marginalized,
regularized slope on the same contrast space. It must have a normalized density
and training-only conditioning; a constant score or a background centered using
held frequencies is not sufficient. Signal and background must use compatible
offset treatment so one does not gain merely from an extra profiled parameter.

Resolve retained-bank versus full-catalogue prior mass explicitly before freezing
that mixture. A nominal background weight is misleading if most signal prior
mass belongs to omitted candidates. Visibility and omitted hypotheses must not
silently destroy normalization or turn a training-selected shortlist into verified
satellite identity. Candidate weights remain model-dependent evidence.

The first geographic comparison should separate the contrast-only change from
the added background branch; do not simultaneously add cones, RX-specific timing,
or tune a spatial prior around the exposed reference. Report location and held
prediction separately. Positive scores alone have repeatedly failed to establish
better geography in the preceding studies.
