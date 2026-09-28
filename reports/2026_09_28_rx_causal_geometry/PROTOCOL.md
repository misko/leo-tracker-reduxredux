# Causal frequency reference and frozen receiver geometry

The residual study found changing candidate sequences and receiver-specific loss
of support. This experiment tests whether satellite forecasts and receiver geometry
add predictive evidence beyond a generic causal frequency-continuity reference.
It is a frozen-parameter transfer diagnostic, not a refitted model leaderboard.

## Population and isolation

Use the same six calibration recordings, 12 lanes and 2,719 paired windows as the
completed temporal-transfer study. Each omitted recording uses its saved fit from
the other five recordings: joint count distribution, scaler, within-geometry
centering convention, coefficients, occupancy and persistence remain fixed.
No original evaluation/confirmation recording participates. Verify completed
evidence and source/input hashes before execution.

The frequency reference processes each receiver separately in timestamp order.
For each window, form its predictive density from strictly earlier observations,
score all current candidates, then update history. Reception and held roles do
not reset history. It receives no satellite frequency, geometry, nomination prior,
current outcome or future observation when constructing a prediction.

## Fixed causal density

Track all combinations of the last two nonempty candidate sets, not one nearest
candidate. Collapse exact duplicate phases in history only; keep every original
candidate in the scored set and count likelihood. Frequencies live on the lane's
saved alias circle. Empty windows advance time but do not replace nonempty history.

The following settings are engineering defaults frozen before the first run,
not selected by their performance on these recordings:

- Uniform birth fraction: 0.2.
- Base measurement standard deviation: 500 Hz.
- Maximum history age: 10 seconds.
- Prior standard deviation of minimal wrapped frequency velocity: 5,000 Hz/s.
- Forecast uncertainty from changing velocity: 500 Hz/s times forecast horizon.

With no recent history the density is uniform. With one recent nonempty window,
use an equal mixture centered on its candidate frequencies, with variance
`500^2 + (5000 * horizon)^2`. With two recent windows separated by positive gap,
retain every candidate pair. Its velocity is the minimal circular increment
divided by gap; pair weights are proportional to a zero-mean Gaussian velocity
prior. Extrapolate each pair to the current time. Its variance is
`500^2 * (1 + (horizon/gap)^2 + (1 + horizon/gap)^2)
 + (500 * horizon)^2`.

Use normalized wrapped Gaussian components, mixed with the uniform birth fraction.
This is a two-window predictive baseline, not a persistent satellite tracker.
Minimal-wrap velocity is a modeling assumption; no physical branch or identity is
assigned. All predictions and pre-update history metadata must be inspectable.

## Likelihood and comparisons

Keep the frozen joint count probability and factorial set-density terms. Replace
the uniform per-candidate phase density with the causal density `f`, adding
`sum(log(f))` to the original reference log score. For a satellite density `g`,
replace the old uniform signal ratio with `sum_j g(x_j)/f(x_j)` and use the existing
paired signal/background kernel, geometry features and presence filter.

Evaluate frozen within-family D, S and T models, plus T with swapped geometry,
reversed geometry and quarter-period-shifted satellite frequencies. Each uses the
same causal reference, generated independently of model/control predictions. Each
control filters its own observation history as in the previous experiment.
Uniform-reference D/S/T scores must reproduce the completed temporal-transfer
results before interpreting new scores. No fitting or hyperparameter selection.

Report equal-record mean scores for reception and held roles, including:
causal reference minus uniform reference; causal D/S/T minus causal reference;
T minus D/S/swapped/reversed/shifted; and each causal model's full score minus its
uniform-reference counterpart. Export per-record and per-window values, not only
means. More latent presence is not proof of better association.

## Validation and interpretation

Tests must verify density normalization, circular behavior, duplicate-history
invariance, empty/stale history, constant-velocity forecasts, score-before-update
and future/prefix invariance. Verify reference and signal-ratio arithmetic and
uniform replay independently. Run bounded to 120 seconds, one numerical thread,
4 GiB; no RF collection, raw-IQ campaign or QNAP writes.

The causal reference is an observational predictor, not verified clutter. A gain
over it measures incremental prediction under these models, not satellite identity,
travel direction or location accuracy. Frozen parameters were optimized with a
different reference; unfavorable transfer is not a proof that a refitted geometry
model cannot help. These reused recordings are development evidence only.
