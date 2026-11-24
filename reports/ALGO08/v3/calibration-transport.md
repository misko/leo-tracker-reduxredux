# Does the installed calibration update rescue candidate positions?

**The fixed-zero position is the larger gap.** Across 36 shared fixes in the 41-pair field panel, the candidate's excess error was **326 m mean / 276 m median** at `c = 0` and **317 m / 210 m** with fitted `c`. Giving the candidate the installed same-recording calibration update increased its error by **37 m mean / 25 m median** relative to its actual fitted position. It nonetheless moved two results inside 1 km, from **18/41 to 20/41**, compared with **24/41** for installed. At 2 km it stayed at **33/41**, compared with **36/41** for installed. [Frozen protocol](calibration-transport-protocol.md) · [First-30 receipt](measurements/calibration-transport-first30.json) · [Later cohort and cumulative receipt](measurements/calibration-transport-first41.json).

## Typical error and coverage answer different questions

A negative change means the position moved closer to the survey. The table describes paired distances on shared fixes and counts all observed threshold crossings. All-attempt coverage keeps withheld and failed recordings in the denominator. Threshold tuples show `before → after (gained / lost)`.

| Cohort | Calibration change | Shared fixes | Mean / median change, m | Median absolute change, m | Improved / worsened | All attempts within 1 km | All attempts within 2 km |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1–30 | Installed fixed → fitted | 26 | −29 / −20 | 54 | 14 / 12 | 16→19 (3 / 0) | 26→26 (0 / 0) |
| 1–30 | Candidate fixed → fitted | 26 | −40 / −28 | 63 | 14 / 12 | 13→14 (1 / 0) | 23→23 (0 / 0) |
| 1–30 | Candidate fitted → installed update | 26 | +35 / +16 | 46 | 11 / 15 | 14→15 (1 / 0) | 23→23 (0 / 0) |
| 31–41 | Installed fixed → fitted | 10 | −44 / −25 | 56 | 6 / 4 | 3→5 (2 / 0) | 10→10 (0 / 0) |
| 31–41 | Candidate fixed → fitted | 10 | −47 / +6 | 96 | 5 / 5 | 5→4 (0 / 1) | 10→10 (0 / 0) |
| 31–41 | Candidate fitted → installed update | 10 | +41 / +43 | 53 | 3 / 7 | 4→5 (1 / 0) | 10→10 (0 / 0) |
| 1–41 | Installed fixed → fitted | 36 | −33 / −22 | 54 | 20 / 16 | 19→24 (5 / 0) | 36→36 (0 / 0) |
| 1–41 | Candidate fixed → fitted | 36 | −42 / −9 | 63 | 19 / 17 | 18→18 (1 / 1) | 33→33 (0 / 0) |
| 1–41 | Candidate fitted → installed update | 36 | +37 / +25 | 48 | 14 / 22 | 18→20 (2 / 0) | 33→33 (0 / 0) |

DS30-0397 is the only candidate-only fix. On all **37** candidate fixes, its own fitted update changed error by **−37 m mean / −1 m median**. With the same-recording installed vector substituted wherever available, the change relative to candidate fitted is **+36 m mean / +21 m median**. The transport leaves DS30-0397's original fitted position intact. Excluding that case, candidate 1 km coverage is **17→17** under its own calibration and **17→19** with the installed vector replacing it, while 2 km stays at **32**. On first30 alone those shared-fix counts are **12→13**, then **13→14** at 1 km and **22→22** in both comparisons at 2 km. The held cohort had only one no-fix case, DS30-0326, withheld by both. Its shared and all-attempt threshold counts coincide.

Installed crossed 1 km on DS30-0330, 0354, 0185, 0413 and 0439. Candidate crossed inward on 0354 and outward on 0439. The transported vector improved coverage on 0330 (**1,017→971 m**) and 0439 (**1,034→956 m**) relative to the actual fitted candidate. None of the observed candidate, installed, or transported calibration changes crossed 2 km. The actual candidate lost four installed 2 km cases and gained one. Transport retained those exact gains and losses.

## Anchors versus correction vectors

| Cohort | Candidate minus installed at fixed zero, mean / median | Candidate minus installed fitted | Candidate with installed update minus installed fitted | Installed with candidate update minus installed fitted |
| --- | ---: | ---: | ---: | ---: |
| 1–30, 26 shared | +420 / +452 m | +409 / +442 m | +444 / +449 m | −27 / 0 m |
| 31–41, 10 shared | +81 / +112 m | +78 / +80 m | +119 / +132 m | −58 / −50 m |
| 1–41, 36 shared | +326 / +276 m | +317 / +210 m | +354 / +252 m | −36 / −10 m |

The five remaining shared fixes with at least 1 km of excess fitted error in the original comparison, DS30-0049, 0189, 0220, 0240 and 0452, each still exceeded installed fitted error by more than 1 km after transport. The reciprocal comparison carries the candidate's fitted update to the installed fixed-zero anchor. It reaches **25/41** within 1 km, gaining two and losing one relative to installed fitted, with **36/41** unchanged at 2 km. These comparisons locate the large error gap in the fixed-zero solution under the tested substitutions. They do not identify which receiver, association, geographic inference or search decision made that solution different. This evidence favors examining changes before the `c`-dependent update over changing how the fitted endpoint is chosen.

## What was transported and what was measured

The shortest-arc tangent from installed fixed zero to installed fitted was parallel transported along the shortest arc connecting the two fixed-zero endpoints and applied with the spherical exponential map. Its length is unchanged. The construction uses only the published endpoints on the same scoring sphere. The survey enters the distance score only. The earlier calibration-blend study allowed an oracle to choose a position on the candidate's own calibration arc. The transferred endpoint can lie outside that arc, and its direction uses the installed output. It represents a hypothetical geometric position, with no solver acceptance, new localization, or RF residual. [Earlier blend bound](calibration-blend-field.md) · [Study implementation](calibration_transport.py).

On the 36 shared fixes, median motion from fixed to fitted was **104 m** for installed and **129 m** for the candidate. These are movements of the returned positions. The actual per-recording RF RMS change had mean / median **−0.057 / −0.032 Hz** installed and **−0.066 / −0.058 Hz** candidate. For the later ten alone, those values were **−0.078 / −0.060 Hz** and **−0.154 / −0.100 Hz**. The RF statistics describe the published supports, independently of survey error.

The frozen common-offer output snapshots were checked against the paired result digests, decision, raw authority, published arm coordinates and RF RMS. The signed campaign manifest fixes the order, including the two operational checks. First30 was sealed at `0e489d171` before the later readout. No new waveforms, orbit data, solver execution or benchmark lease were used. Component tests cover identity, dateline wrap, antipodal refusal, rotation invariance and missing-fix scoring.
