# Cold temporal protocol: fixed zero band contrasts

The saved temporal runs isolate held measured CFO from fitting, but they do
not reconstruct the original band-calibration learning stage. They permanently
fix both receiver high-minus-low offsets to zero. Their approximately 12% held
association is therefore a restricted zero-contrast stress result. It cannot
by itself measure the temporal generalization of the original production
calibration procedure or explain the full-recording versus cold performance
gap entirely as overfitting.

This audit is read-only. It reads the immutable source-stage receipts through
`SharedFastScanStore.plot_evidence`, checks the tracking-input hashes, and
constructs calibration design matrices from frozen original observation
metadata. No orbital prediction, scientific fit, held-score tuning, or RF
collection occurs. Bank identity metadata is sufficient for the constructor
dimension audit; synthetic ephemerides are not substituted for real predictions.

## What the source code does

`2026_10_16_dsx01_models/common.py::temporal_context` creates the ordinary
two-receiver group-calibration objective, then constructs a `SequentialShift`
whose offsets are both zero. It calls
`fixed_shift_objective(joint.base, shift)` and wraps the returned raw model in
`SharedScanObjective`.

The live `sequential_group_calibration.fixed_shift_objective` adds the supplied
shift to the receiver baseline, then returns
`GroupCalibrationObjective(..., enabled=False)`. It removes the free physical
band-offset columns. `SharedScanObjective.__init__` explicitly requires
`original.group_count == 0`. Its extra nuisance parameters come from the
detectability arm: one zero-sum q coefficient per candidate minus one. They
adjust detection probabilities, not CFO corrections. The generic optimizer's
`group_count`/`group_limits` labels for this q tail must not be mistaken for
free band-frequency offsets.

The original full-recording path, in contrast, selects a saved A high-stage
offset or a B donor's group correction, then freezes that learned value in
the final shared objective's baseline. Both final models have no free physical
band offsets, but the cold pipeline omits the training-only learning stage
needed to supply comparable frozen offsets. Initializing offsets at zero is
different from learning them from training data.

## Actual original versus cold offsets

Receiver labels below are the UI's RX1/RX2, corresponding to internal 0/1.
These are physical high-band-minus-low-band offsets in Hz, not intercept
differences or surveyed hardware calibration truths.

| Source | Selected original donor | Original RX1 offset Hz | Original RX2 offset Hz | Cold RX1 / RX2 offsets Hz |
| --- | --- | ---: | ---: | --- |
| S01 | A-3 high stage | -14,402.883811 | +43,519.165729 | 0 / 0 |
| S02 | A-5 high stage | -15,328.130134 | +37,126.070686 | 0 / 0 |
| S03 | B-all donor | -15,388.416996 | +41,406.123765 | 0 / 0 |
| S04 | A-4 high stage | -16,368.124393 | +40,465.128913 | 0 / 0 |
| S05 | B-all donor | -16,757.747869 | +41,634.821485 | 0 / 0 |

For A donors the values are the selected high stage's `group_offsets_hz`.
For B donors they are obtained by splitting the saved original joint nuisance
vector at its 18 common-clock coefficients, as the live `donor_state` does.
They remain the same full-data-derived offsets throughout the primary fitted-c
and c=0 warm-start comparisons; the confound described here applies to the
cold temporal protocol.

## Constructor dimensions and independent span check

For every source and both temporal directions:

- Raw physical band-offset count is zero and `raw.group_design` has shape
  `(full_observation_count, 0)`.
- Cold raw baseline is exactly zero before the free common calibration and
  clocks are applied.
- The common CFO design has five columns: two receiver intercepts, two
  receiver slopes and the single actual-RF coefficient c.
- There are 18 common-clock nuisance coefficients. Remaining nuisance
  coefficients are q-only and do not add frequency columns.

| Source | Candidates | Clock nuisance | q-only nuisance | Total cold nuisance |
| --- | ---: | ---: | ---: | ---: |
| S01 | 46 | 18 | 45 | 63 |
| S02 | 51 | 18 | 50 | 68 |
| S03 | 40 | 18 | 39 | 57 |
| S04 | 46 | 18 | 45 | 63 |
| S05 | 32 | 18 | 31 | 49 |

The span check stacks the five CFO columns and 18 clock columns on training
rows, then appends the two physical columns
`(receiver == r) * (channel >= 5)`. Adding these band columns increases matrix
rank by two in all ten source/direction combinations. Thus the missing band
steps cannot be represented exactly by the retained common CFO/clock design.

| Source | Forward training rows | Existing rank → with band steps | Reverse training rows | Existing rank → with band steps |
| --- | ---: | --- | ---: | --- |
| S01 | 2,399 | 15 → 17 | 2,398 | 13 → 15 |
| S02 | 1,762 | 13 → 15 | 1,762 | 15 → 17 |
| S03 | 1,994 | 13 → 15 | 1,994 | 15 → 17 |
| S04 | 1,860 | 15 → 17 | 1,859 | 13 → 15 |
| S05 | 2,028 | 15 → 17 | 2,028 | 13 → 15 |

As a second numerical check, least-squares projection of each unit band-step
column onto the existing training design leaves dimensionless RMS residuals
between 0.1948 and 0.2931. Changing q cannot eliminate those frequency residual
columns. Timing and geometry can compensate some observed signals, but do
not restore the omitted receiver/band calibration stage.

## Interpretation and corrected future control

The existing temporal profile-versus-continuation comparison is internally
matched under the same zero-contrast restriction. Its held-CFO isolation and
observed counts remain valid. It shows how those two methods behave in that
restricted stress class; it does not validate the complete production
inference procedure, and low coverage must not be attributed entirely to
generalization failure.

A corrected future comparison must learn the receiver band contrasts from
the declared training half only, then freeze those learned shifts for held
prediction. One route is a masked `SmoothVisibilityModel` on the free joint
group-calibration objective, followed by the existing physical donor rebase
and `SharedScanObjective` freeze. The original sequential low/high stages can
also be rebuilt strictly on training observations. Either choice needs the
same training-only candidate population policy, priors, search allowances and
calibration-stage budget accounting for profile and continuation, plus fitted-c
versus c=0 controls. No original full-data offset may be used as a training
seed or prior. That corrected experiment has not been run in this audit.
