# DS1 iteration-4 exact-winner residual diagnostic

This report holds the completed iteration-4 exact winners fixed and rebuilds
their all-qualified exact SGP4 supports from receipt-bound causal artifacts.
No reference coordinate, post-seal error, mask, or alternate position was read.

## Exact residual structure

Per-track CFO is reprofiled after the exact rate fit, so each track's mean
residual is zero. The remaining RMS describes within-track shape.

| Group | Observations / tracks / NORADs | RMS | Capped loss | Bounds | Solver |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260921_00` | 8,285 / 476 / 109 | 168.7 Hz | 0.03919 | 1 | stopped at 120 iterations |
| `20260921_16` | 9,686 / 298 / 129 | 312.3 Hz | 0.07735 | 4 | stopped at 110 iterations |

00 is quieter but scan-dependent: its six session RMS values range from 104
to 225 Hz. 16 is more heterogeneous (114 to 542 Hz), with
`scan-hop-e1422297a1ff6598` at 542 Hz. Thus 00's stable basin is not caused by
one exceptional scan, while 16 is visibly concentrated in a few sessions.

| Equal-count RF-only slice | 00 RMS range | 16 RMS range |
| --- | ---: | ---: |
| causal TLE age | 108–236 Hz | 119–542 Hz |
| scan time | 137–201 Hz | 149–531 Hz |
| elevation | 117–207 Hz | 188–409 Hz |
| azimuth | 123–208 Hz | 152–484 Hz |
| track duration | 133–226 Hz | 114–512 Hz |

16 peaks at 18.9–25.7 h TLE age, 62–146 s scan time, elevation above 76
degrees, and azimuth 272–360 degrees. 00 has broad variation instead of a
single monotone geometry slice.  The highest-RMS NORADs are 67463 (748 Hz, 66
observations) and 45183 (667 Hz, 18) for 00, versus 68739 (1,562 Hz, 228),
68674 (862 Hz), and 68740 (848 Hz) for 16.

The public receipt has session IDs and hashed observation IDs but no
receiver/channel field. Session is therefore the available scan/receiver
proxy; this diagnostic does not infer a channel.

## Matched ablation

The predeclared cheap ablation adds one bounded common fractional Doppler scale
after the existing per-track CFO:

`measured = CFO(track) + (1 + epsilon) * exact_doppler + residual`.

It initializes at zero, bounds epsilon to ±0.002, and is fit only on the fixed
winners. It does not select a position, tau, association, or candidate.

| Group | epsilon | centered-Doppler correlation | capped loss before -> after |
| --- | ---: | ---: | ---: |
| 00 | +620.5 ppm | +0.0926 | 0.039190 -> 0.039034 |
| 16 | -1194.2 ppm | -0.1133 | 0.077349 -> 0.079035 |

A common scale does not explain the shared 00 approximately-4.2 km basin: its
0.40% 00 improvement is small and it worsens the 16 capped objective.

The supported low-dimensional follow-up is a hierarchical per-session
fractional Doppler scale: one common scale and six zero-mean, shrinkage-regularized
session deviations, retaining per-track CFO and the existing per-NORAD
phase-rate guard. It is seven parameters for 8,285 00 observations and its
regressors are track-centered exact Doppler values, so it is estimable from RF
alone. The exploratory unregularized six-session calculation reduces 00
capped loss from 0.039190 to 0.038050 (2.9%), much more than the common arm.
Its estimates span -975 to +2,000 ppm and one reaches the provisional guard,
so it is only evidence for a predeclared regularized test, not a production
fit or a basis to change the winner.

This nuisance can plausibly create a stable location bias: CFO removes a
track intercept, while a scan timebase error leaves residual proportional to
the Doppler trajectory. Geographic optimization can compensate with biased
predicted slopes. The evidence is falsifiable and reference-free; it does not
establish causation.

## Predeclared next ablation

Keep the iteration-4 union candidates unchanged. Add the seven-parameter
hierarchical scale term with fixed common/deviation standard deviations,
zero initialization, the ±0.002 guard, all qualified observations, and exact
SGP4 re-ranking of the same candidates. Report null and nuisance exact losses
for both groups. Reject it as nonportable if it fails to improve capped loss in
both groups or reaches a guard. This reuses prepared supports and runs in
minutes; it requires no RF collection.

## Artifacts

- `iteration4_exact_residual_diagnostic.py` reproduces the slices and ablation.
- `iteration4-residual-diagnostic.json` records machine-readable results,
  input binding, and the explicit reference-free contract.
