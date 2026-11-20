# Independent Doppler anchors

Starting from anonymous prepared GLRT tracks, the anchor receiver published all eight correct-tile fixes within 5 km in both calibration arms. Full joint published seven and exact orbit fit six. Every receiver withheld the three omitted offers. The anchor fit used a median of 1,389 observations, compared with 3,663 for full joint, and took 0.611 s median worker CPU versus 1.076 s. On the second cohort's three common fixes, median anchor minus joint position error was +0.158/+0.036 km. [Predictions](predictions.jsonl.gz) · [Per-case scores](scores.json)

| Cohort | Receiver | Published within 5 km / attempts | Median error, zero / fitted (km) | Max error, zero / fitted (km) |
|---|---|---:|---:|---:|
| First | Independent anchors | 4/4 | 1.235 / 0.743 | 2.005 / 2.545 |
| First | Full joint | 4/4 | 1.030 / 0.770 | 4.364 / 4.611 |
| First | Exact orbit | 3/4 | 0.672 / 0.798 | 1.404 / 0.824 |
| Second | Independent anchors | 4/4 | 2.913 / 2.421 | 4.725 / 3.573 |
| Second | Full joint | 3/4 | 1.931 / 1.765 | 3.876 / 3.986 |
| Second | Exact orbit | 3/4 | 1.959 / 1.687 | 3.242 / 3.448 |

The extra anchor publications were DS26-0247 relative to exact orbit and DS26-0313 relative to both controls. The anchor withheld two omitted offers at the tile edge and one for weak position geometry. The benchmark uses two groups selected with different fixed hashes before scoring. All recordings come from the same measured roof. [First cohort chart](first/figures.json) · [Second cohort chart](second/figures.json) · [Omitted control chart](omitted/figures.json)

## What the receiver uses

The solver shortlists causal orbits using curved prefixes, fits one bounded phase and independent level on each prefix, and seeds the four receiver/band offsets from circular modes of the resulting CFO levels. The reserved suffixes play no part in those nominations. The leave-one-family calibration fits position and radio terms from other nominated prefixes. A held family's candidate and runner-up each get one integer branch and a bounded phase from their own prefix, then predict the late measurements. Both final calibration arms share the winning tracks, branches, and orbit candidates. The common exact range-rate fitter uses one phase per orbit and four lane bias/drift terms. [Frozen protocol](PROTOCOL.md) · [Source lock](source-lock.json)

## RF results on shared measurements

We replayed every measured correct tile with read-only tracing and verified the exact sealed published and forced endpoints before accepting residuals. Keys combine receiver/band lane, exact RF, time rounded to a microsecond and folded CFO rounded to a millihertz. Duplicate keys are excluded. These figures describe conditional residuals under each receiver's fitted model on identical observations.

| Cohort and selected overlap | Points per arm | Anchors RMS, zero / fitted (Hz) | Full joint RMS (Hz) | Exact orbit RMS (Hz) |
|---|---:|---:|---:|---:|
| First, all shared | 6,807 | 134.6 / 101.9 | 149.3 / 108.0 | 174.8 / 143.6 |
| First, common owner and alias | 6,764 | 135.0 / 102.2 | 149.8 / 108.4 | 173.2 / 141.4 |
| Second, all shared | 5,125 | 226.6 / 213.0 | 153.8 / 133.4 | 163.8 / 137.7 |
| Second, common owner and alias | 4,709 | 146.4 / 159.0 | 153.4 / 131.4 | 152.7 / 129.9 |

Anchor suffix RMS across the eight accepted correct offers ranged from 148.6 to 376.5 Hz. It uses the candidate's leave-one-family state and prefix-phase estimate, a separate statistic from the shared-point fitted RMS. A smaller anchor inventory improved the first cohort's fitted CFO and coverage. The second cohort shows calibration and position regressions on shared outcomes. [Shared-point RF seal and summary](matched-rf.json) · [Matched residuals](matched-rf.jsonl.gz)

The same frozen fitter also has a complete native GLRT to streaming Graph qualification. [Full native replay](../anchor-full/README.md)
