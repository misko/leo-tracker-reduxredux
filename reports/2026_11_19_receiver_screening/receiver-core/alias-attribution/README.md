# Raw CFO aliases and the wide detector's position gap

Raw whole-alias discrepancies are uncommon on confidently matched winners. Across six complete recordings, only 90 of 19,948 matched capture-era and wide winners differ by a whole alias period. All 90 differences are one period, about 227.273 kHz. Median absolute remaining CFO differences are 14.95–20.55 Hz. The Graph stage changes track ownership and branch choices even when the two raw winners agree on the branch. [Frozen protocol](PROTOCOL.md) · [Winner-pair census](match-audit.json) · [Matched CFO and epoch measurements](winner-pairs.jsonl.gz)

## What matches before Graph

Both sources must choose the same strict physical family as gated winner. Each family must have a sole eligible partner in the other list and the two individual winners must independently satisfy the strict 2 sample and 1 kHz folded tolerances. This leaves fewer matches than the reciprocal-family census, which compares all candidate members. The sign of the integer changes below is capture-era minus wide. [Physical matching rules](../../acquisition-support/peak-support/README.md)

The detectors were positive together on 21,008 receiver probes. Of those, 734 selected different winning families and 326 agreed on a winner family but had competing eligible families. The remaining 19,948 passed the strict direct winner test. Wide was positive alone on another 2,829 probes and capture-era alone on 1,747. For DS29-0082 those counts were 429 and 234, respectively. This time support discrepancy is much larger than the 13 whole-alias differences among its confidently paired winners.

The eligible set covers 87.7% of capture-era positives and 83.7% of wide positives. Absolute wrapped CFO differences have per-recording 95th percentiles of 69.69–109.85 Hz. On DS29-0082 the 95th and 99th percentiles were 93.17 and 260.97 Hz. These are differences between two estimates of the same saved waveform. Independent true CFO is unavailable on these recordings. [Exact measurement distributions](cfo-distributions.json)

| Recording | Matched winners | Alias −1 / +1 | Median absolute wrapped CFO difference (Hz) | Median absolute fractional epoch difference (ns) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 3,004 | 1 / 6 | 20.55 | 0.105 |
| DS29-0082 | 1,506 | 13 / 0 | 17.82 | 0.078 |
| DS26-0237 | 3,279 | 4 / 8 | 18.99 | 0.102 |
| DS29-0174 | 3,539 | 11 / 3 | 16.83 | 0.080 |
| DS26-0122 | 3,966 | 23 / 8 | 20.28 | 0.098 |
| DS29-0247 | 4,654 | 2 / 11 | 14.95 | 0.082 |

## What Graph changes

DS29-0082 had 1,526 Graph-owned observations and 61 tracks on capture-era input, compared with 1,789 observations and 71 tracks on wide input. Wide Graph added 428 observation IDs and lost 165 relative to capture-era. Those counts describe receiver sample identities irrespective of the winning peak at each sample. Within the 1,307 strict matched winners owned by both Graphs, ten had a raw whole-alias discrepancy. Graph placed all ten on the same branch. The 19 remaining differences in Graph-resolved branches came from observations whose raw branch agreed. The longest same-sign consecutive difference on the wide tracks spanned 12.05 s. These resolved values are Graph's own track coordinates and can differ by a track's constant alias branch. They do not assign a true absolute branch without separate evidence.

DS26-0036 showed the same separation. Graph aligned all five raw alias disagreements on the 2,519 matched observations owned by both Graphs, and its independent track reconstruction yielded 98 branch differences on previously agreeing observations. The longest same-sign sequence lasted 30.14 s. Its wide Graph gained 564 sample IDs and lost 291 against capture-era. The archived RF output therefore does not point to a widespread coherent raw alias mistake. Changes in input time support and graph assignments remain important.

Every Graph branch difference on these two recordings is constant within the pair of overlapping Graph tracks. Removing one integer offset for each track pair leaves zero inconsistent observations over 96 DS26-0036 and 60 DS29-0082 pairs. Wide DS29-0082 has more Graph tracks, but its median span falls from 24.10 to 16.30 s and its maximum span from 75.15 to 58.50 s. The track-pair alignment measures a coordinate difference between Graph fits. A true absolute CFO branch requires independent evidence.

The held Graph controls show the same pattern. Over all four recordings, 33 of 34 raw whole-alias differences on jointly owned matched winners became zero and one changed from −1 to +1. None of the raw discrepancies formed two consecutive same-sign differences on a Graph track. All 295 nonzero Graph-resolved differences are constant within their capture-era/wide track pair, across 396 overlapping pairs. [Graph support and track receipts](graph-attribution.json)

| Recording | Capture-era / wide Graph points | Capture-era only / wide only | Capture-era / wide tracks | Capture-era / wide median track span (s) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 2,867 / 3,140 | 291 / 564 | 94 / 103 | 28.36 / 25.89 |
| DS29-0082 | 1,526 / 1,789 | 165 / 428 | 61 / 71 | 24.10 / 16.30 |
| DS26-0237 | 3,293 / 3,626 | 286 / 619 | 103 / 110 | 28.39 / 26.78 |
| DS29-0174 | 3,587 / 3,762 | 266 / 441 | 128 / 126 | 22.67 / 21.79 |

## Position counterfactual

All wide native probes, gate flags, winner identities, fractional epochs, candidate ordering and request settings remain fixed. On the matched winners, the alias-only arm changes the raw CFO by the donor's measured integer multiple of the period, and the wrapped-only arm adds the small residual without changing the raw branch convention. A joint arm uses the exact donor CFO. The circular control applies those joint differences to other existing matched winners in the same receiver, physical lane and 30 second block. This preserves the perturbation distribution while breaking the physical pairing. The separate unchanged-wide fit repeats the authentic full recorded wide factors. All donor-dependent arms are retrospective diagnostics.

The original package build failed before an input was prepared or a worker started. Building the same sealed release in a dedicated ext4 compiler temporary directory succeeded. The measurement also copied each authenticated factor, tracking configuration and causal TLE archive into ext4 before launching the workers.

## Development position results

The fresh unchanged fits reproduced the original archived wide endpoints and conditional RMS exactly. The table gives changes from those fresh controls for each calibration arm. [Checked position and RF scores](scores.csv)

| Recording | Intervention | Position error change, zero / fitted (m) | Conditional RMS change, zero / fitted (Hz) | Graph tracks |
| --- | --- | ---: | ---: | ---: |
| DS26-0036 | Alias only | <0.001 / <0.001 | <0.001 / <0.001 | 103 |
| DS26-0036 | Wrapped CFO only | −189 / −186 | −2.159 / −2.266 | 106 |
| DS26-0036 | Joint | −189 / −186 | −2.159 / −2.266 | 106 |
| DS26-0036 | Circular null | +336 / +328 | +12.323 / +12.287 | 105 |
| DS29-0082 | Alias only | +21 / +27 | +0.014 / +0.012 | 71 |
| DS29-0082 | Wrapped CFO only | +3 / +66 | −1.036 / −1.005 | 69 |
| DS29-0082 | Joint | +3 / +66 | −1.036 / −1.005 | 69 |
| DS29-0082 | Circular null | +833 / +897 | +6.931 / +6.867 | 70 |

DS29-0082 started at 2.489/2.346 km. Neither donor field recovered the original capture-era compact endpoint errors of 0.568/0.516 km. Changing wrapped CFO alone lost 54 Graph-owned IDs and added seven, even though the detector winners and probe support stayed fixed. On DS26-0036, the same intervention lost 55 and added 168 Graph-owned IDs while improving position. The chronological pairing matters. Circular exchange of the same donor deltas worsened both development positions. [Graph support and track receipts](graph-attribution.json) · [Capture-era comparison](../../next/input-factor-comparison/README.md)

## Held position results

The fresh unchanged holds reproduced archived wide endpoints and RMS exactly. Stock position error was 0.382/0.323 km on DS26-0237 and 0.793/0.806 km on DS29-0174. [Checked position and RF scores](scores.csv)

| Recording | Intervention | Position error change, zero / fitted (m) | Conditional RMS change, zero / fitted (Hz) | Graph tracks |
| --- | --- | ---: | ---: | ---: |
| DS26-0237 | Alias only | <0.001 / <0.001 | <0.001 / <0.001 | 110 |
| DS26-0237 | Wrapped CFO only | −99 / −99 | −5.390 / −5.387 | 109 |
| DS26-0237 | Joint | −99 / −99 | −5.390 / −5.387 | 109 |
| DS26-0237 | Circular null | +275 / +246 | +10.414 / +10.408 | 110 |
| DS29-0174 | Alias only | <0.001 / <0.001 | <0.001 / <0.001 | 126 |
| DS29-0174 | Wrapped CFO only | −258 / −254 | −8.893 / −8.928 | 129 |
| DS29-0174 | Joint | −258 / −254 | −8.893 / −8.928 | 129 |
| DS29-0174 | Circular null | Withheld / withheld | — | 127 |

Alias-only moved the error by fractions of a millimetre on three recordings and raised it by 21/27 m on DS29-0082. The joint arm agreed with the wrapped-only arm within 1 mm on all four recordings. The wrapped donor measurements improved three paired position outcomes and lowered conditional RMS in all four. The wide position gap on DS29-0082 persists under every direct CFO substitution. The measured evidence points to differences in admitted/time support and Graph reconstruction, with wrapped CFO also influencing track membership and accuracy. The contribution of unmatched peaks and time support to this position gap remains unisolated. The donor substitutions need archived capture-era measurements from the same recording. All four position recordings share one roof. [Both-arm figures for each intervention](plots/index.html) · [Graph comparisons](graph-attribution.json)

All 20 phase-release services completed under the enforced 512 MiB cgroup with zero swap. Nineteen published both arms. DS29-0174's circular control reached the compact cavity decision and withheld both arms, with a clean service exit and 67.009 s unit lifetime. Actual unit lifetimes ranged from 37.994 to 105.563 s and peak cgroup charge ranged from 282,411,008 to 404,762,624 bytes. Four additional capped services recorded the capture-era Graph controls. [Position worker receipts](results.jsonl.gz) · [Graph traces](graph-traces.jsonl.gz) · [Prediction lock](prediction-lock.json)
