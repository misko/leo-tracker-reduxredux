# Gaussian sum single scan prototype protocol

Frozen before real scientific scoring. Execution authorized on 2026-09-30.
Source checkout starts at a887eec1560606dc7f4ffcbc5bbded1bd798f1c8 with unrelated
dirty work; receipts hash the exact participating source files.

Selection contains eight DS9, the historical eight DS10, and the historical
32 DS11 recordings, bound in selection.json. Each scan resets all fitted states.
Numerical gates are frozen in oracle-results.json. This evaluates completed-track
retrospective evidence, not a causal streaming detector or untouched data. Roof
coordinates are evaluator-only and operator-supplied rather than surveyed.

## Frozen first model

- State: east/north/height km relative to inherited configuration center
  (37.85625, -122.484375), UTC offset seconds, two RX drifts Hz/s, and a shared
  epoch-error state per geometrically admitted satellite.
- Regional prior: four equal components at east/north combinations (+/-5,+/-5)
  km with horizontal SD 5 km. Height 0 +/-0.1 km, UTC offset 0 +/-1 s, RX drifts
  0 +/-0.5 Hz/s and satellite epoch errors 0 +/-0.5 s. The center has historical
  development exposure; this is not an independently supplied GNSS-free prior.
- Stress prior: four equal centers (+/-60,+/-40) km, horizontal SD 15 km, same
  other states. Initially synthetic cases and first DS9 only; no truth tuning.
- Use a response-free archived TLE catalogue predating capture, with a conservative
  geometric union over 250 km around the prior center and the recording support.
  Record all propagation failures and catalogue gaps; check nonlinear/support
  approximation flags. Finite regional support is not global acquisition.
  Check each retained component's five-sigma horizontal radius and height against
  the declared 250 km disk and +/-1 km height support. Gaussian tails beyond
  finite support and linearized visibility remain explicit approximations.
- Up to eight deterministic time-spread original points per retained track,
  requiring at least three. Retain complete tracks chronologically by support
  end, start and ID; exclude later tracks conflicting on RX/channel/visit.
  This conservative fixed selection may discard real independent signals.
- Helmert contrasts remove arbitrary constant frequency levels. Signal and
  background score identical projected observations. Report information discarded
  by contrast projection and subsampling.
- Frequency convention verified before fitting: exported CFO is normalized to
  11.2 GHz by the public trajectory projection. Use -11.2e9/c times receding
  range rate; actual track RF remains provenance. Physical RX drift is scaled
  by 11.2e9/actual_rf_hz when predicting canonical CFO. An earlier working
  assumption of raw CFO or an 11.325 GHz reference was rejected by source tracing.
- Assumed sample covariance: 100^2 Hz^2 independent floor plus 100^2 Hz^2
  exponential correlation with 0.5 s time constant, before projection. These
  are declared engineering priors, not calibrated measurement uncertainty.
- Background: zero-mean contrast Gaussian with that covariance and marginalized
  slope SD 100 Hz/s and curvature SD 5 Hz/s^2 (quadratic term t^2/2). Signal
  prior 0.8 is uniform across the geometric union; background prior 0.2 plus
  physically invisible candidate mass. Flag local opportunity approximations.
- Preserve RX drift and candidate-specific epoch covariance across factors.
  Other spatial/orbit/clock errors remain unmodelled; real posterior regions
  are conditional diagnostics, not calibrated navigation integrity claims.
  No antenna roll or unmeasured gain pattern is fitted.

## Arms and limits

Primary arms: Gaussian sum with at most 16 components, greedy with one retained
child but identical likelihood and initial prior, and prior-only. Weight floor
zero; at most 65536 candidate children per factor. Retain all mass accounting.
No scientific settings are selected using roof error.

One numerical thread, 6 GiB virtual-address limit and 90-second fit wall limit
including load per process. Exports have a 180-second limit. At most two numerical
processes and one bulk archive reader. Each batch contains at most eight scans
and lasts at most 15 minutes including prerequisites. Preserve timeouts, failures
and pending work; no automatic budget expansion or replacement scans. Use the
installed interpreter rather than a dependency resolver.

Gate the first DS9 scan on verified sources, response-free candidate coverage,
synthetic physics derivative/interpolation checks and shared-state covariance.
More than 1% discarded posterior mass on any Gaussian-sum update, a support-boundary
violation, or a numerical defect fails the promotion gate. Preserve its diagnostic
replay, but do not expand the panel until resolved without reference-score tuning.
Greedy discarded mass is an intentional baseline property and is reported.

A scientific stop at this gate completes the first planned experiment: publish
the blocker and qualified prototype rather than promoting a truncated posterior.
Engineering repairs require recorded amendments; changing scientific priors or
budgets defines a new experiment and retains the original result.

## Replay and evaluation

Score each completed factor before assimilation. Retrospective detector/trajectory
construction may use later support, so these are descriptive next-factor scores,
not prospective RF forecasts. Save every update's location marginals, association
and background probabilities, predictive density, retained mass and consumed
support. A future-support test requires prefix-only feature construction and is
not claimed by this completed-track smoke.

Seal predictions before reference evaluation. Point error uses the highest-weight
component mean, never the mode closest to truth. Report prior-only performance,
all failures and abstentions, and separate datasets. Full-mixture reference
regions cannot be replaced by a component ellipse. Synthetic known truth supplies
coverage and identity checks; real data has no verified NORAD truth.

After the DS9 gate passes, expand to eight DS9 scans, DS10 validation and frozen
DS11 replay, with a recorded gate decision between bounded batches. Preserve
inputs, config/source hashes and commands. No RF, raw-IQ reprocessing, golden
changes, source mutation or remote publication is included.
