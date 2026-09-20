# Recording-clock corrections do not reproduce the historical gain on recent data

The historical independent wide search reached 937–941 m with separate
recording UTC corrections. Applying the same ±0.5 s correction model to the
recent 48-hour corpus's existing FoV-assisted candidate assignments does not
reproduce that result. Lower frequency residual RMS does not establish better
position accuracy.

This is a conditional local replay of existing assignments, not the currently
running independent wide search. No known position enters this refinement.
The inherited candidate identities were selected by the earlier known-site
FoV-assisted analysis; that limitation is preserved in the output.

| Cohort | Position error | Fitting RMS | Random evaluation RMS | Clocks at bounds |
|---|---:|---:|---:|---:|
| All 599 retained tracks | 4,930.2 m | 135.46 Hz | 135.06 Hz | 108 / 211 |
| Previously selected clean tracks | 4,463.7 m | 55.04 Hz | 70.73 Hz | 35 / 126 |

Both fits converge. The all-track shared-clock result was about 4,194.9 m
with 158.79 Hz evaluation RMS. The clean shared-clock result was about
4,469.1 m. Thus the more flexible recording-clock model worsens the all-track
position despite reducing its residuals, and barely changes the clean result.
The numerical errors are evaluated after inference against the user-confirmed
antenna coordinate, using spherical radius 6,371,008.8 m.

The clean selection is frozen from the previous information report: fitting
RMS ≤100 Hz and support ≥15 s. No new reference-distance filtering is used.
Each retained source has its own constant frequency offset; recording clocks
are shared across all that recording's retained sources. Altitude is fixed to
zero. The fitting partition remains the existing deterministic randomized
partition; evaluation observations do not refit parameters.

The large number of clocks on their bounds signals model pressure, not proof
that the hardware timestamps are wrong. These corrections may absorb orbit,
association, transmitter, or receiver-frequency errors. They should not be
applied to production timestamps.

## Reproduction

The [inference artifact](2026_09_20_track_position_information/recording-clock-inference.json)
contains the three input digests, positions, per-recording offsets, convergence,
and source-level training residuals. The existing replay tool now supports
`--grouping recording` as well as its unchanged default `sample-rate` grouping:

```bash
PYTHONPATH=src:tools python tools/replay_sample_rate_clocks.py \
  --states reports/2026_09_20_doppler_error_budget/states.npz \
  --inference reports/2026_09_20_matched_positioning/inference.json \
  --information reports/2026_09_20_track_position_information/information.json \
  --grouping recording --output NEW_OUTPUT.json
```

The command also computes the shared-clock comparison rows. The archived
artifact contains the recording-clock rows from the original direct invocation
of the same numerical fitter. Three tests pass, covering distinct grouping
dispatch and retained conditional provenance, synthetic clock/position
recovery, and evaluation-data isolation.

The ongoing 211-recording/684-track full wide search uses RF-only evidence,
causal TLE snapshots, and a horizon constraint rather than the known-site FoV.
Its identities and results must be evaluated separately. The historical
sub-kilometre observation is not a demonstrated accuracy guarantee for the
recent dataset.

## Candidate-pass weighting audit

The recent 599 source tracks represent 450 candidate satellite passes.
113 passes contribute multiple source tracks, with up to five tracks per pass.
Treating every source sample as equally informative can let a densely observed
pass dominate. An alternative gives each pass total fitting weight one:
each fitting residual is weighted by the inverse square root of the number of
fitting observations in its pass. Evaluation samples do not set these weights.
This is an equal-pass sensitivity test, not a full correlated-noise likelihood.

The current pass IDs are inherited from the earlier error-budget state bundle.
Historical groups are NORAD/recording pairs. All identities and cohort selections
remain frozen. Every variant below is reported; none is selected by distance to
the antenna reference. RMS columns remain unweighted observation RMS for
comparability, even though the fitting objective is pass-balanced and robust.

| Cohort | Shared clock fitted? | Candidate passes | Position error | Fitting RMS | Random evaluation RMS |
|---|---|---:|---:|---:|---:|
| Historical all | No | 269 | 2,128.6 m | 148.35 Hz | 173.13 Hz |
| Historical all | Yes | 269 | 1,349.5 m | 142.50 Hz | 168.33 Hz |
| Historical selected | No | 86 | 1,805.7 m | 80.17 Hz | 93.59 Hz |
| Historical selected | Yes | 86 | 1,111.8 m | 79.71 Hz | 92.89 Hz |
| Current all | No | 450 | 5,285.6 m | 158.94 Hz | 160.38 Hz |
| Current all | Yes | 450 | 4,121.6 m | 158.79 Hz | 158.70 Hz |
| Current selected | No | 173 | 4,880.1 m | 68.77 Hz | 84.41 Hz |
| Current selected | Yes | 173 | 4,220.7 m | 68.53 Hz | 83.82 Hz |

All fits converge. There is no per-recording clock in this experiment. Balancing
passes changes the result but does not remove the remaining displacement. It
does not explain the large historical/recent-corpus difference by itself.

The [inference artifact](2026_09_20_track_position_information/pass-balanced-inference.json)
contains input digests and all eight fits. Reproduce with:

```bash
PYTHONPATH=src:tools python tools/replay_pass_balanced_position.py \
  --historical-run /tmp/leo-wide-randomized-polish \
  --current-states reports/2026_09_20_doppler_error_budget/states.npz \
  --current-parent reports/2026_09_20_matched_positioning/inference.json \
  --current-information reports/2026_09_20_track_position_information/information.json \
  --output NEW_OUTPUT.json
```

Tests verify equal total pass weights, independence from evaluation sample count,
rejection of unknown weighting modes, and physical position recovery with the
pass-balanced fitter. Default observation and segment weighting remain available.
