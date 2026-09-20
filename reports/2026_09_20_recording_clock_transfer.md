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
