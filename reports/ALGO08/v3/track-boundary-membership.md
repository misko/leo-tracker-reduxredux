# Does first-8-ms detection favor one end of a Doppler track?

The opposite-radio boundary test did not reproduce the predicted directional advantage. The held equal-recording estimate for **end minus start, mixed minus installed, after the full/full control** was **−3.34 percentage points**, with a recording-bootstrap interval of **−15.85 to +10.74 points**. Two of six eligible held recordings were positive. The test conditions on contemporaneous opposite-radio Graph support, so the result describes the signed output packets at observed track boundaries. [Frozen protocol](track-boundary-membership-protocol.md) · [Sealed readout](measurements/track-boundary-membership.json.gz).

An earlier aperture would favor the end, if its earlier samples still caught departing signals and missed arrivals that appeared later in the visit. This test asks about membership at the two boundaries. The earlier owner study measured unordered loss of time leverage, the centroid work measured frequency values and timestamp effects, and the late-pilot experiment ranked empty short visits using intra-visit coherence. None contained this signed start/end comparison. [Owner-time support](owner-time-support.md) · [Aperture centroids](sparse8-cfo-epoch.md) · [Late-pilot retries](late-pilot-rescue.md).

## Matched exposure

The original installed Graph runs independently by receiver and RF lane. A donor was one of its uninterrupted ordered pieces, split at gaps over eight seconds. It nominated the opposite antenna on the very same signed visit. The target's relative CFO and epoch offset came solely from at least two identical full/full positives in the middle of the donor piece. The three-way match used the same ±250 signed Hz and ±2 samples at both boundaries, with no alias or frame wrap. We then paired start and end opportunities by distance from the boundary, separately for the 8/20 and 20/20 comparisons. Interior alignment rows never entered the scored edges. [Read-only reducer](track_boundary_membership.py).

| Held recording in order | Pieces with both apertures | Equal-piece controlled contrast |
| --- | ---: | ---: |
| DS30-0178 | 2 | +25.00 pp |
| DS30-0019 | 2 | −12.50 pp |
| DS30-0274 | 3 | −13.33 pp |
| DS30-0330 | 3 | −2.78 pp |
| DS30-0397 | 0 | Unavailable |
| DS30-0124 | 7 | −26.43 pp |
| DS30-0452 | 2 | +10.00 pp |
| DS30-0086 | 0 | Unavailable |

DS30-0049 supplied a development control, with one piece at both apertures and a zero contrast. Of 1,419 held donor segments, 142 were too short, 1,215 lacked qualifying interior alignment, 42 had balanced short edges only, one had balanced full edges only, and 19 had both. The primary pieces use target radio 0 in ten pieces and radio 1 in nine. They supply 78 short and 19 full control lanes at each boundary.

| Held primary-piece aperture and edge | Both methods match | Installed only | Mixed only | Neither matches |
| --- | ---: | ---: | ---: | ---: |
| 8/20, start | 39 | 10 | 4 | 25 |
| 8/20, end | 50 | 14 | 2 | 12 |
| 20/20, start | 12 | 0 | 0 | 7 |
| 20/20, end | 16 | 0 | 0 | 3 |

On these matched short lanes, installed membership rose from 49 to 64 as the donor approached its last observation. Mixed membership rose from 43 to 52. The count-weighted contrast is −7.69 points. The primary statistic instead gives each piece equal weight within its recording. Including the short-only pieces gives 235 short lanes per boundary and a descriptive count-weighted contrast of −9.36 points. All 38 primary full/full target lanes agree between packet selectors on whether the nominated peak is present, though they are too few to rule out selection effects elsewhere. The installed receiver uses historical continuation, and the mixed packet uses the strongest verified factor on full anchors. [Original full/full selection audit](first30-native-agreement.md).

## Interpretive boundary

The short observations are a median 1.77 seconds inside either donor boundary. Full controls are a median 0.709 and 1.772 seconds inside the start and end. Those are observed Graph ends, with the donor selected by the installed receiver. The physical on-air transition inside a 20 ms visit is unobserved. The periodic control schedule and the requirement for shared interior anchors make this a narrow conditional comparison. It can miss effects outside stable, jointly visible pieces. The negative point estimate and uncertain sign fail the frozen advancement gate. No alternative decoder or replay schedule was evaluated.

The readout ran at `674b65b74` following freeze `f741d17f8`. Both native packets and their clock, signed RF opportunity, aperture count and original Graph source bindings were checked for each enrolled case. The analysis used the retained metadata on CPU 3 with one numerical thread. No solver, waveform, survey, catalogue or timing lease was used. Four focused tests passed. Uncompressed readout SHA-256 `a01bb8aa278834fb64b9c761c0f1f2665e7da74289084144458c59d9232261fd`.
