# Which parts of the Doppler curves disagreed?

Across 19 shared fixes outside the DS30-0049 development case, the median recording had **13.0% of candidate-owned observations** that the installed receiver did not corroborate. Removing those observations eliminated **20.4% of the support for a slope** and **24.6% of the support for curvature** in time. The lost observations tended to carry more information about a curve’s shape than a point count suggests. [Protocol](owner-time-support-protocol.md) · [Sealed per-recording features](measurements/owner-time-support-first24.json.gz)

Greater loss of curve support did not rank recordings by worsening position error. On DS30-0049, 41.3% of quadratic support disappeared and fitted error rose by 2.620 km. DS30-0170 lost 30.4% and its fitted error **fell by 0.620 km**. DS30-0189 lost 33.3% and its fitted error **rose by 1.016 km**. The error changes compare both complete pipelines. An earlier receiver–solver crossover isolates the receiver’s contribution on DS30-0049. [Crossover](ds30-0049-saved-crossover.md) · [Scored recordings](measurements/owner-time-support-score.json)

| Loss predictor vs. candidate-minus-ALGO08v3 position error | Fixed-zero Kendall tau-b | Fitted Kendall tau-b |
|---|---:|---:|
| Fraction of owners missing signed detector agreement | −0.018 | +0.018 |
| Fraction of slope support missing agreement | −0.193 | −0.135 |
| Fraction of quadratic support missing agreement | −0.228 | −0.216 |
| Fraction of quadratic support outside full-length anchors | −0.415 | −0.404 |

Positive values would support retrying recordings that lost more of the time information. The candidate-only anchor measure ranked in the opposite direction on these 19 recordings. The current measurements give no basis for choosing a new receiver schedule or reversing its retry threshold. A prospective test uses DS30-0010, DS30-0444 and DS30-0073 in the frozen enrollment order. [Reducer](owner_time_support.py)

The calculation uses hardware sample counters and published candidate satellite associations. It splits by satellite, radio and tuning, and at gaps longer than eight seconds. It fits an intercept and slope afresh when estimating the remaining quadratic support. The 250 Hz and two-sample comparison checks agreement between detector winners. A real signal can fail that check. The recording supplies no ground truth for each individual Doppler observation. Of the 24 recordings, 20 had positions from both builds, one had only a candidate fix, and three were withheld by both. The reporting cohort preserves all 24 outcomes.
