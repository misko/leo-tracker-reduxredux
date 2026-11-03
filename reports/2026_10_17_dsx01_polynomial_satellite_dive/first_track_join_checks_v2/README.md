# DSX01 scan 1: tracks 2 and 3, and a shared-curve test

This continues the [ordered track review](../scan1_track_review/README.md).
Receiver/channel/start time defines order; original fragment IDs are unchanged.
The supplied GPS is fixed. Hardware and per-satellite orbital phase come from
the completed shared-phase fit. These are conditional compatibility checks, not
independent satellite identification or position estimates.

## Track 2: RX1/CH1/T004

There are 25 points from 20.942 to 43.300 seconds. NORAD 67654 has 85.3 Hz RMS,
versus 74.0 Hz for the frozen cubic polynomial. Its residual mean is -0.53 Hz,
slope is +0.65 Hz/s and lag-one correlation is 0.078. It passes the current
noise screen and is the only candidate passing all gates. The next two scored
candidates have 2,054 and 2,524 Hz RMS. The fitted component constant is -591.4 Hz
and shared satellite phase is -2.701 seconds.

![Track T004](../scan1_track_review/S01-RX1-CH1-T004.png)

This is a cleaner residual than T008. It overlaps T008 for only 6.03 seconds;
that is insufficient for the existing common-mode comparison's minimum eight
seconds. Its identity remains provisional because the shared model was learned
using these curved tracks.

## Track 3: RX1/CH1/T011

There are 13 points from 44.366 to 53.236 seconds. This linear fragment is not
allowed to calibrate hardware or satellite phase. NORAD 47357 has 74.6 Hz RMS,
versus 75.0 Hz for its frozen line. On RMS alone, NORAD 63469 also looks plausible
at 84.5 Hz. Only 47357 passes the full current gates.

![Track T011](../scan1_track_review/S01-RX1-CH1-T011.png)

T008 proposes the same satellite, on the same receiver and channel, ending
17.39 seconds before T011. Their independently profiled constants differ by
24.68 Hz. The historical merge limit of ten seconds leaves these as two groups.

## Can one curve explain both T008 and T011?

We searched all 1,707 candidates again with a single constant shared by both
fragments, the original integer alias per fragment, frozen receiver/band
calibration and frozen per-satellite phase. No track slope or polynomial
coefficient is fitted. Every member and the pooled time-ordered residuals must
pass the existing noise tests, as well as visibility, calibrated hardware/phase,
450 Hz RMS and 3,000 Hz absolute constant bounds.

NORAD 47357 is the sole passing candidate. All 41 original points are retained.
Its shared constant is -1,920.74 Hz and joint residual RMS is 120.98 Hz. Removing
the second constant improves the integrated Gaussian comparison cost by 9.43
(positive favors the join; this is not a satellite identity probability).
NORAD 63469 rises to 1,236.7 Hz RMS when required to explain both fragments.

![One common satellite curve](fitted_c_same_channel_continuation.png)

The orange points require an integer alias lift of -1 native period,
227.273 kHz, to share the blue fragment's displayed frequency frame. This is
not an additional continuous frequency adjustment. The shaded gap has no
observations and does not prove continuity within the gap. T008's mild residual
trend is still present. This supports a provisional link, not a secure identity.

The c=0 control uses the same points, candidates, priors, gates and pair checks.
It also finds only NORAD 47357, at 120.97 Hz RMS. This is a frequency-fit ablation;
no localization accuracy is inferred.

## Controls: shared candidate identity alone is insufficient

| Pair | Points | Top scored joint candidate | RMS c=0 / fitted-c, Hz | Result in both arms |
|---|---:|---:|---:|---|
| RX1/CH1 T008 + T011 | 41 | 47357 | 121.0 / 121.0 | One passing candidate; favors one constant |
| RX1/CH1 T004 + RX2/CH1 T004 | 58 | 67654 | 147.3 / 148.5 | Reject shared constant; member residual means fail |
| RX1/CH1 T008 + RX1/CH6 T004 | 60 | 47357 | 328.6 / 253.7 | Reject; residual means and pooled structure fail |
| RX1/CH1 T008 + T004 | 53 | 67654 | 7,980.1 / 7,978.2 | No candidate passes; distinct-track control |

The cross-receiver example is particularly useful: a combined RMS of 148 Hz
looks good, but it hides receiver-specific nonzero residual means. A pooled-only
check also passes this case, so both member and pooled checks are required.
Failure to share one constant does not establish different satellite identities;
remaining calibration or transmitter differences could also explain it.

## Implemented merge check on scan 1

The merger now optionally checks the complete time-ordered residual sequence
in addition to every original member. Historical defaults are unchanged and
reproduce the frozen results exactly in both arms. A separate experiment extends
the maximum gap to 30 seconds while requiring both residual checks.

| Configuration | Groups c=0 | Groups fitted-c | Associated points, each arm | T008 + T011 linked? |
|---|---:|---:|---:|---|
| Historical ten-second gap, member checks | 69 | 68 | 1,975 | No |
| Ten-second gap, member and pooled checks | 74 | 71 | 1,975 | No |
| Thirty-second gap, member and pooled checks | 68 | 68 | 1,975 | Yes |

Each arm starts with the same 89 admitted fragments. Some previously permitted
merges fail the pooled check, so the stricter ten-second version has more groups.
The longer-gap experiment recovers compatible continuations without dropping
points or changing proposed identities. It is not established that thirty
seconds is the best general setting. There is no increase in association
coverage: 1,975 / 4,797 raw GLRT points, 41.2%, remain associated.

Machine-readable results are in this directory and
[the scan-wide merge experiment](../scan1_pooled_merge_check/summary.json).
Eighteen focused tests passed, including distinct offsets, ambiguity branches,
pooled trends, sample ordering and lossless rejection. The corrected plot
supersedes the original display in `../first_track_join_checks/`; numerical
results are unchanged.
