# Causal orbit-increment receiver-geometry experiment

## Purpose and population

Test whether short-horizon candidate-conditioned frequency prediction restores a
useful basis for receiver geometry. All panels have already been explored. Fit
only the original six calibration recordings' reception windows, physically
excluding held and evaluation observations before preparation. Score the original
four evaluation recordings and the fixed four DS8 recordings separately. This is
development/transfer evidence, not a fresh blind confirmation or identity truth.

## Fixed frequency mechanism

Preserve the existing joint count background and causal frequency reference.
For each receiver and nominee, use the most recent nonempty candidate set from
strictly earlier observations, at most 10 seconds old. Advance each of those
frequencies by the nominee's frozen predicted change mu(now)-mu(history).
Use an equal mixture of wrapped Gaussians with standard deviation
sqrt(2*500^2+(500*horizon_seconds)^2) Hz. The target density is 0.8 times that
mixture plus 0.2 uniform phase density. With no recent history, use the same
mixture weights around the frozen absolute forecast at 500 Hz standard deviation.

Score all current candidates before updating history. Preserve duplicate current
candidates in the likelihood; deduplicate wrapped phases only in stored history.
Empty windows do not overwrite the last nonempty set. History crosses the
reception/held boundary causally. Nominee-specific frequency changes retain the
orbital slope hypothesis; absolute fitted CFO cancels from those changes. No
nearest-candidate selection or observed-current residual fit is permitted.

This is a proper candidate-conditioned predictive density, not proof that the
stored history belongs to that candidate. Other emitters or clutter can enter
history. Report that limitation explicitly, alongside the existing one-present-
state and retained-shortlist assumptions.

## Geometry fitting and comparisons

Use the unchanged background, full-reception scaler, within-lane centering,
coefficient priors, neutral D seed, two-start optimizer and D/E/S/T dimensions.
Fit one new orbit-increment family. Compare it with the already-frozen
causal-trained static-forecast family; score both on identical complete windows
against the same causal reference. Do not choose a model using evaluation signs.
This static comparison changes history anchoring, target birth mixture and
horizon-dependent width together; it is not an isolated orbital-motion ablation.
Use the zero/reversed-increment comparisons for the specific motion contribution.

Frozen controls use T coefficients unchanged:

- receiver swap and within-role geometry reversal;
- cyclic permutation by one of nominee-specific geometry features (columns 3:8),
  leaving frequency, visibility, priors and nuisance features untouched;
- zero nominee frequency increment and negated nominee frequency increment;
- quarter-period shift of current target means only, leaving stored history
  unshifted so that the control cannot cancel itself.

Report equal-record reception and held predictive scores, T-D, T-S, T-reference,
all control contrasts, and orbit-versus-static family differences. Positive
frequency gains alone do not establish a tilt benefit. A geometry association
claim requires consistent incremental tilt and candidate-specific control gains,
with a subsequent disjoint evaluation before promotion.

## Execution and validation

Freeze source, tests, protocol, settings and input hashes before each numerical
stage. Each fit/score stage is bounded to 180 seconds, one numerical thread and
4 GiB; preserve incomplete/failed receipts. Validate phase-density normalization,
score-before-update, stale/empty history, actual time gaps, motion/shift controls,
training isolation and score accounting. No RF collection, IQ reprocessing,
catalogue re-ranking, new orbit propagation or QNAP mutation.
