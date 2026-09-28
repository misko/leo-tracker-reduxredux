# Receiver-drift synthetic recovery prerequisite

This bounded experiment tests whether two receiver-specific linear frequency
slopes can be recovered jointly with east, north, and timing inside the full
first-session frozen candidate mixture. It is not a fit to an actual DS7 clock
effect and does not use a reference position, score, pose, source read, or IQ.

Synthetic observations use the sealed baseline estimate as the generating
position and timing. For each track, the candidate with maximum training
mixture component score at that estimate supplies the Doppler curve, and its
stationary Student-t training offset is retained. A physical receiver slope in
native Hz/s is multiplied by `11.2 GHz / actual RF` and time centered within
the track. The fit profiles independent stationary offsets for every track and
optimizes the complete candidate mixture over east, north, timing, and two
free receiver slopes. Starts remain the baseline prior center with timing
starts 0, -2, and +2 seconds; no generating parameter is used as an initial
guess and no slope prior is claimed.

The nuisance-projected training Jacobian has rank 5/5 across 1,473 rows, with
singular values `[6525.86, 982.47, 901.83, 203.96, 169.24]` and condition number
38.56. All cases converged without hitting a bound:

| injected native slopes RX0/RX1 (Hz/s) | position error | timing error | slope errors RX0/RX1 | runtime |
| --- | ---: | ---: | ---: | ---: |
| 0 / 0 | 3.12 m | 0.000208 s | 0.00230 / 0.00758 Hz/s | 45.95 s |
| +1 / -1 | 3.11 m | 0.000208 s | 0.00232 / 0.00757 Hz/s | 46.61 s |
| -1 / +1 | 3.11 m | 0.000208 s | 0.00231 / 0.00756 Hz/s | 50.37 s |

Every case meets the frozen thresholds of 100 m, 0.05 seconds, and 0.05 Hz/s.
Each case stayed below 60 seconds and total analyzer time was 142.93 seconds,
below the 180-second cap.

This qualifies only the synthetic nonlinear recovery prerequisite on one
candidate bank. It does not admit a receiver-drift term into the real DS7 fit,
calibrate a prior, establish cross-capture receiver identity, or relax any
clock, scoring, or geographic gate.

Frozen identities:

- Spec SHA-256: `c7c9132a125238d219ddd581addb651e644571b17aaf25b14fd50d7b2bc5fbe3`
- Analyzer SHA-256: `6189882c086911468c313130a7be99b5e3a1721d0b63d814370cc8b8d0d5643d`
- Result SHA-256: `114a84eadb45085f786922e9efc2906c2527ac7ee51078a79a27825d8eaab6a5`
- Reference audit: `reference_excluded`

Two component tests verify zero-drift observation equivalence and the analytic
profiled-slope envelope gradient against a finite difference.
