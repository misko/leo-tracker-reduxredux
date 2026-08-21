# Preliminary TLE–Doppler alignment for 5 completed Standard dwells

Status: candidate-only retrospective research evidence; no satellite identity is claimed.

## Method

The analysis validates each sealed `standard.glrt64-final-trajectory-table.v3` artifact, propagates the verified local Space-Track snapshot over the capture interval, retains a conservative horizon-visible candidate set, removes one constant CFO intercept, and ranks slope/acceleration/jerk agreement. 4 shifted-time prediction sets (-600 s, -300 s, 300 s, 600 s) provide a chance-alignment control.

## Cohort summary

| Session | Release | Heard tracks | Possible TLE tracks | Median best score | Better than every null |
|---|---|---:|---:|---:|---:|
| `cap-20260821T201522-841b2a20e151` | `4f0b17e5f` | 15 | 577 | 10377.36 | 5/15 |
| `cap-20260821T193701-87f96f47e73f` | `d9dfe1bf3` | 17 | 575 | 2414.67 | 13/17 |
| `cap-20260821T193440-17c2e0ebef6a` | `d9dfe1bf3` | 11 | 565 | 9350.40 | 0/11 |
| `cap-20260821T190912-ffd441556880` | `6bbc4c616` | 10 | 591 | 8749.38 | 8/10 |
| `cap-20260821T190701-7a5d980ec1c6` | `6bbc4c616` | 8 | 576 | 10975.22 | 0/8 |

## Aggregate observations

- 61 replay-retained Standard trajectories were compared.
- The median nearest-candidate shape score is 8616.80.
- 26/61 tracks beat all shifted-time null candidates.
- 35/61 tracks have a runner-up within 5% of the best score, so nearest-candidate specificity is often weak.
- Most frequent nearest candidates: STARLINK-11083 (10), STARLINK-11412 (9), STARLINK-11182 (9), STARLINK-31239 (7), STARLINK-35808 (4), STARLINK-4209 (4), STARLINK-6218 (3), STARLINK-6135 (3).

## Interpretation limits

The receiver products use `uncalibrated_prior`, so absolute CFO intercepts are excluded. The GPS position is an explicitly labelled input rather than capture-bound authority. A large visible-satellite inventory creates a substantial chance-match floor; the shifted-time controls and top-two margins must accompany every candidate. These results should guide the next calibration and beam-pointing step, not yet populate the production TLE-association field.
