# Causal TLE phase widths with fixed ownership

Replacing the light fitter's common 2.5 s prior with a width derived from two genuine causal element sets reduced forced horizontal error in all 16 calibration arms on eight matched physical recordings. The median paired decrease was **76 m with `c = 0`** and **42 m with fitted `c`**. Matched conditional Doppler RMS increased in 14 of 16 arms by a median of 0.066 / 0.067 Hz, respectively. All eight recordings share the same installation. [Protocol](PROTOCOL.md) · [Sealed predictions](predictions.jsonl.gz) · [Per-arm position and RF scores](scores.json)

The standard roof charts show the two methods separately under the same eight cases and both calibration settings. The plot rows retain withheld status and the authenticated common-support digest. Their plotted positions are the forced diagnostics. [Both-arm roof charts](charts/index.html) · [Figure evidence lock](figure-lock.json)

The disputed DS26-0197 case retained the same 2,607 points, owners and aliases as the original diagnostic. History improved fitted-`c` error from 1.905 to 1.747 km while conditional RMS rose from 117.156 to 117.243 Hz. Archived no-repair v5 reached 0.689 km. The history change closes about 13% of the original 1.216 km fitted-`c` gap to v5. The equal-width fit reproduced both coordinates and conditional RMS exactly in both arms on all four disputed common-support controls.

| Physical matched cohort | `c = 0` median horizontal error, km | Fitted-`c` median horizontal error, km | Median matched RMS change, `c = 0` / fitted `c`, Hz |
| --- | ---: | ---: | ---: |
| Four disputed | 1.443 → 1.367 | 1.424 → 1.340 | +0.104 / +0.076 |
| Four hash-selected | 2.457 → 2.331 | 2.070 → 1.946 | +0.028 / +0.037 |
| All eight | 1.867 → 1.843 | 1.688 → 1.566 | +0.066 / +0.067 |

The archived DS26-0036 omitted-offer stress test held the same observation mask and assignments across both methods. Its forced errors were 24.689 → 24.601 km with `c = 0` and 24.806 → 24.716 km with fitted `c`. Its conditional RMS increased by 0.461 / 0.450 Hz. The comparison is a privileged fixed-owner fit at a supplied region. It supplies forced geometry diagnostics and no receiver publication decisions.

## How the prior was formed

The current TLE is the exact element in the light fitter's geometrical catalogue. The previous TLE is the latest distinct earlier element epoch among authenticated snapshots acquired by the current catalogue collection time. The original request fixes each archive file's collection time and digest. Both element epochs are at or before their collection times. Both collections precede cutoff. No follow-on ephemeris, post-fit phase, RF residual or geographic reference is used to form the prior.

Both elements are propagated to the same scan time in TEME. Projecting their position difference onto current velocity gives a time displacement. The v5 width formula scales that displacement by the current element age divided by the epoch separation, adds a one-second floor in quadrature and caps the width at 15 s. The mean stays zero and the existing ±7.5 s phase search bound stays fixed. When a distinct valid historical element is missing or propagation fails, the width falls back to 2.5 s. This estimates the disagreement of orbital predictions as a proxy for uncertainty. The study fits no empirical calibration of that proxy. All 181 satellite occurrences on the eight matched masks had a historical pair, with widths from 1.000 to 15.000 s and a median of 3.012 s.

The trial changes the existing phase precision rows and uses the same widths in the exact backtracking score. Both methods use the same RF weights, clock basis, initialization, assignment set, aperture and optimization limits. The likelihood penalties differ by design. Conditional RMS measures the same physical frequency residual separately from those penalties and from horizontal error.

## History and fit resource use

The median paired fitting CPU time across the eight recordings was 0.155 s with the common width and 0.149 s with historical widths. These intervals share the already prepared causal bank and observations. A separate single-core history replay reauthenticated the exact candidate bytes and reproduced every width. For a record it used a median **0.301 s CPU**, **25 snapshots**, **44.56 MB history reads** and **46 SGP4 calls**. History reads ranged from 33.82 to 55.24 MB. The median largest snapshot was 1.78 MB. The chosen prior pairs added a median of only **3.22 kB of previous TLE text**, excluding the original current catalogue and provenance. The width vector needs one scalar per candidate. The isolated historical lookup is the main incremental measured cost. No prebuilt history index, board benchmark or raw replay is included. [Standalone history replay measurements](history-cost.json) · [Frozen code and source versions](source-lock.json)

## Two fresh synthetic sites

The two separately seeded tests draw fresh locations in different geographic boxes and use the genuine DS26-0197 orbit catalogue and the same sealed earlier TLE authority. The simulated observations use the established generator's RF noise and clocks. The equal and history methods share the blind simulated owners and alias lifts. Two containing offers use independent 8–10 km offsets. The `c = 0` errors were 1.002 → 0.681 km and 2.606 → 2.430 km. Fitted-`c` errors were 0.135 → 0.178 km and 0.342 → 0.341 km. The synthetic geometry is generated from the current catalogue itself. Its results exercise different look angles and radio nuisance terms. [Synthetic code lock and private-to-scoring labels](synthetic/prediction-lock.json) · [Synthetic position and RF scores](synthetic/scores.json)

The first sandbox attempt imported supervisor code that required a home directory. It produced nine unavailable rows before fitting. The rerun separated the solver worker from supervisor imports, preserving the source-locked prior formula and cohort. [Retained failed attempt](preflight/predictions.jsonl.gz)
