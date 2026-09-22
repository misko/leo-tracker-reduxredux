# Paired-receiver transition audit

This bounded audit rechecks the frozen eight-hour exact-pair export used by
`tools/summarize_dual_lnb_transitions.py`. It is descriptive and uses no new RF.

## Finding

The 174 RX1-to-RX0 proxy crossovers and zero reverse crossovers are not explained
by timestamp reversal, duplicated pair references, or a sign error in the
transition summarizer. They are consistent with a strongly one-sided angular-motion
sample and the previously measured east-west detector-response relation. They are
therefore real structure in this selected corpus, but not a symmetric receiver
handoff law, an independently calibrated antenna transition, or independent
satellite-identity evidence.

The exporter defines the proxy as
`10 log10(RX0 GLRT margin / RX1 GLRT margin)`. Increasing values therefore mean
increasing RX0 proxy dominance. The summarizer labels a group RX1-to-RX0 only when
the early-third median is below -1 dB and the late-third median is above +1 dB.

## Integrity checks

- The export contains 18,364 track-local pair references and 9,182 unique
  `(session, RX0 track, RX1 track, visit, UTC)` observations. The factor of two is
  intentional: every pair is attached to both participating tracks. The two copies
  agree exactly; no conflicting duplicate was found.
- The 9,182 unique observations form 731 receiver-track pairs, matching the published
  inventory. Within every group, visit index increases strictly with UTC. No group
  repeats a visit and no timestamp/visit reversal was found.
- Pair construction is receiver-explicit: the left member is RX0 and the right member
  is RX1. Alias representatives are collapsed by margin, then timing and the fitted
  RX1-minus-RX0 CFO offset leave a mutually unique match. Thus the receiver labels
  and proxy sign do not depend on sort order.
- The fitted global receiver LO offset and drift gate associations in frequency; it
  is not subtracted from, or otherwise used to construct, the GLRT-margin ratio.
  It can still induce selection through the 1 kHz matching gate, so the transition
  sample remains conditional on successful timing/CFO association.

## Direction and selection diagnostics

Across all 731 groups, the late-minus-early proxy-change median is +2.35 dB; its
10th, 25th, 75th, and 90th percentiles are +0.16, +1.18, +3.61, and +5.10 dB.
The positive trend is present in every session: median within-group slopes range
from +0.057 to +0.390 dB/s, and the fraction of positive group slopes per session
ranges from 0.71 to 1.00.

Of 602 groups with usable rank-1 direction arrays, 93.0% move toward increasing
east direction cosine. Of the 171 threshold crossovers in this geometry subset,
169 (98.8%) move eastward. Their median east-cosine change is +0.303 and median
angular displacement is about 20.1 degrees. Across the 602 groups, proxy change
correlates with east-cosine change at 0.61, compared with 0.13 for north-cosine
change. This agrees with the earlier fit in which increasing east cosine favors
RX0. The three-group difference from 174 arises from groups without usable
rank-1 direction arrays, not from contradictory motion.

The transitions cover all eight channel/edge lanes, although lower sidebands and
channel 1 contribute most. Among all 174 transitions, 160 receiver pairs have the
same available rank-1 candidate on both sides, 11 disagree, and three have a
missing leader on at least one side. This is another reason not to promote the
threshold event itself to an identity fact.

The apparent absence of reverse transitions is consistent with the inferred,
mostly eastward motion in this window, conditional on the chosen rank-1 candidate
IDs. Those candidate trajectories are hypotheses rather than independent motion
truth. The export is also conditioned on both receivers detecting a candidate and
passing timing/CFO uniqueness gates. It does not include the receiver-specific
exposure, detection threshold, failed matches, or censored non-detections needed
to estimate bidirectional transition probabilities.

## Model constraints for the satellite-ID rerun

Use exact paired observations as positive same-signal anchors and join the two
receiver-local paths without counting simultaneous points twice. A temporal
response term may use the full continuous proxy sequence and candidate direction,
with a shared installation orientation and lane intercepts. It should compare
candidate-predicted eastward response evolution rather than reward the mere label
RX1-to-RX0.

Do not encode `RX1 -> RX0` as a universal transition prior or penalize a candidate
for lacking a reverse/forward threshold crossing. The current sample contains
almost no reverse angular motion, so direction symmetry is untested. Preserve the
global receiver mapping uncertainty, receiver/lane gain offsets, temporal
correlation, and a nuisance allowance for obstruction or changing sensitivity.
The proxy is a nonlinear GLRT-margin ratio, not calibrated received power.

The association LO model and the response model should remain separate. Propagate
association uncertainty or at minimum report sensitivity to the CFO gate and
receiver-offset fit. Hardware gain mismatch can shift the ratio intercept and
lane-dependent response; it cannot be inferred away from these same selected
tracks. Candidate comparison should therefore obtain identity gain only from
candidate-specific directional evolution beyond a receiver/lane/session nuisance
baseline, with held-out sessions or satellites and an ablation that removes the
response term.

### Common-time-trend stress test

The first transition-model draft demeaned response and ENU within
`(session, satellite)` but did not remove lane intercepts within that group and
did not compare against a generic time trend. That is material because one such
group can contain several channel/edge lanes and the sampled ENU trajectories are
almost linear over these short arcs.

On the 195 later scored tracks, a separately fitted intercept-plus-linear-time
baseline has median RMS 0.676 dB. It beats the draft rank-1 directional model on
184/195 tracks (94.4%) and the rank-2 model on 187/195 (95.9%). This does not show
that direction is absent: time and direction are nearly collinear in this selected
window. It does show that the draft score has not isolated candidate-specific
direction information from the universal increasing trend.

As a deliberately severe diagnostic, residualizing both response and candidate
ENU against intercept plus linear time within each session/satellite/lane before
fitting reduces the later median rank-1/rank-2 RMS values to 0.691/0.697 dB. The
median rank-2-minus-rank-1 separation falls from 0.0243 dB in the draft score to
0.00194 dB, and raw versus residualized candidate ordering agrees on only 49.2%
of tracks. The residualized response coefficients are numerically unstable, a
symptom of weak residual angular support rather than a usable replacement model.

The circular-response-shift null does not resolve this confounding. Rolling a
monotonic short sequence creates an artificial discontinuity while preserving a
smooth candidate arc, making real alignment too easy to distinguish. Add a smooth
common-time nuisance model or null, preserve lane intercepts, and test the
incremental held-out score of candidate ENU over that baseline. If this window
cannot identify the increment because time and east cosine are collinear, retain
the transition evidence as continuity/response description and abstain from using
it to change the Doppler candidate.

## Reproduction identities

The audit used the following SHA-256 identities:

- `exact_pairs.json.gz`: `ee4aa196cba196c972b45091c31d65ccde15112847a888c17f3ed19cfc5b365b`
- `research_dual_lnb_identity_pairs.py`: `bd1fd77e07776d760332986a320d4134de0333932d6620fb80346148a63a244c`
- `summarize_dual_lnb_transitions.py`: `1261714aa85835ed3fbabccca514a7d4a649eda4a8bc25ee430e1dfe238d0a39`
- `/tmp/dual-lnb-transition-inventory.json`: `c882bd1578afe07502be7cdeb334ca01591590e750f256613db0a471f8089f98`

The hardware interpretation is not independently proven. The observed relation
could combine antenna response, receiver gain or sensitivity, obstruction, and
selection. The frozen export cannot separate those contributions.
