# DS6 training-calibrated track noise

Four completed development scans show that a fixed 100 Hz residual scale is
poorly calibrated. Track-specific scales improve held prediction on every scan,
but do not achieve DS6-wide sub-kilometre positioning.

| Scan suffix | MS/s | Fixed scale error (m) | Calibrated scale error (m) | Held log-score gain |
|---|---:|---:|---:|---:|
| 3221795d82a1c7ec | 10 | 6284 | 6202 | 472.94 |
| 5eaaa2a8f8c995b3 | 2.5 | 3670 | 3779 | 400.39 |
| c78fb2dba2465361 | 5 | 8485 | 7291 | 486.01 |
| c7e37f65ae9e08b0 | 7.5 | 504 | 489 | 1212.38 |

The frozen protocol uses the preceding no-drift training winner as a calibration
point. Each track's candidate is selected by training likelihood and visibility;
training residual MAD is converted to Student-t4 scale, bounded to 20–1000 Hz.
Scales are then frozen. Both arms optimize position and shared scan timing with
the same random whole-visit partitions, candidate banks, three starts, and
training-only decision rule. No receiver drift is included. The fit script does
not load the operator coordinate; geographic evaluation occurs only after all
four outputs are complete.

Median calibrated scale is about 101–109 Hz across scans, but individual tracks
span 20–1000 Hz. The held log-score comparison includes the density normalization
and consequently rewards both calibration and prediction; it must not be read
as a pure geometric improvement. Scales can absorb mismodelled trajectories or
incorrect candidate identities as well as measurement noise. This procedure is
a plug-in development estimator and does not integrate calibration uncertainty.

All four calibrated-arm winners report convergence and remain inside the local
bounds. The 5 MS/s fixed-scale repeat reports an abnormal line-search termination
at the unchanged preceding converged winner. That status is preserved, not
relabeled as convergence. Its training score exactly reproduces the preceding
baseline; other control differences are below 0.01 log-score units.

This is a local experiment on four of the 43 DS6 scans. Inherited approximate
catalogue shortlists and an operator coordinate without surveyed uncertainty
remain limitations. The remaining kilometres of error call for receiver/channel
consistency diagnostics and a check of track-level systematic bias; optimizing
predictive likelihood alone has not solved those biases.

Tests cover Student-t scale recovery, training/held isolation, equivalence with
the baseline objective, frozen source/input/candidate provenance, complete
outputs, training-only winner selection, and exact propagation at each winner.
No RF collection or production deployment occurred.
