# DS1 causal per-NORAD orbit-phase-rate arm

This directory is a matched DS1 adapter for the strongest historical sub-km
method. It preserves frozen DS1 membership, randomized masks, the geographic
and time pair union, and ordinary full-catalogue candidate selection. At a
given frozen pair it selects each track's ordinary candidate from TRAIN only,
then fits one causal correction per NORAD:

    orbit phase (seconds) = causal TLE age (hours) * NORAD rate (seconds/hour)

The rate has the frozen historical Normal(0, 0.0917661591 seconds/hour) prior
and a +/-0.25 seconds/hour bound, with one TRAIN-only CFO per track. This is
an orbital phase/rate correction, not a per-scan epoch or global receive-time
shift.

## Exact-state requirement

The original DS1 cache is suitable for global receive-time tau but not for
this phase nuisance by itself: indexing cache state at receive+tau+phase
advances both satellite orbit and Earth rotation. The historical formal model
advances only orbit propagation while holding Earth rotation at receive+tau.

run.py therefore reads the receipt-bound causal archive read-only and builds
five exact SGP4 nodes at orbital phases -2,-1,0,+1,+2 seconds, at fixed
receive-time Earth rotation. It fits the historical five-node phase surrogate,
then replays the selected winner with exact SGP4. A result is qualified only if
the exact replay maximum Doppler discrepancy is at most 0.2 Hz.

An earlier cache-indexed prototype was rejected before publication: its exact
discrepancy was 413.13 Hz RMS and 1,019.40 Hz maximum because it advanced
Earth rotation with orbital phase. That failed artifact is deliberately not
retained in this report directory.

## Bounded DS1 results

Every row below converged and passed the 0.2 Hz exact replay gate.  The
reference coordinate was introduced only after the rate, identity, and point
selection had completed.  Each is a TRAIN-ranked subset of the frozen DS1
pair union, so these are feasibility results, not full-arm DS1 outcomes.

| DS1 case / prior | frozen pairs evaluated | reference error | ordinary TRAIN loss | rate TRAIN loss | rate held capped RMS | exact max error |
|---|---:|---:|---:|---:|---:|---:|
| train_20260921_00_1 / Sacramento | 4 | 40.407 km | 0.143560 | 0.084338 | 286.32 Hz | 0.0000078 Hz |
| train_20260921_00_1 / Reno | 1 | 39.999 km | 0.143314 | 0.083966 | 285.68 Hz | 0.0000079 Hz |
| validation_20260922_08_1 / Sacramento | 4 | 0.961 km | 0.033702 | 0.021644 | 129.18 Hz | 0.0000018 Hz |
| validation_20260922_08_1 / Reno | 1 | 1.412 km | 0.033704 | 0.021927 | 129.68 Hz | 0.0000021 Hz |

The phase-rate nuisance lowers the local TRAIN score in all four bounded
replays.  It does not yet move the selected location or establish a
sub-kilometre DS1 positioning result: the independent TRAIN group remains
about 40 km away, and the validation singleton already begins near the site.
The held frequency improvements are within-track checks, not independent
future-satellite validation.

The selected TRAIN/Sacramento fit required 106 L-BFGS-B iterations, has
232.33 Hz TRAIN capped RMS and 286.32 Hz held capped RMS, and differs from
its direct exact replay by at most 0.0000078 Hz. Nonconverged and failed
prototype artifacts were discarded.

## Historical transfer control

The prior blind fixed-assignment causal-rate pilot is a useful negative
control, not a DS1 result.  Its sealed inference
`35564ccd5873abbdb9cf890f829903303b8258398075f91431319b3ee12424e6`
is documented in `../2026_09_23_train_orbit_uncertainty_design/FINDINGS.md`.
It passed its direct SGP4 check but produced 12.025 km / 12.029 km position
error on the first six scans (Sacramento/Reno) and 4.764 km on the second six.
It reduced held frequency RMS but did not reproduce sub-kilometre position.

A full singleton case keeps every frozen DS1 pair when --pair-limit is
omitted, but is expected to take roughly an hour for 165 pairs at the observed
L-BFGS-B exact-node cost. Full DS1
needs parallel per-arm execution and a predeclared exact candidate-pair
budget. No result should be called DS1-wide until all cases and both priors
complete.
