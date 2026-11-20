# Displaced-site identity diagnostics

Reuse the already scored four development captures and the same native
tracklets, clock model, search gates, orbital catalogue, score scales and
first-eight/last-four sample split. At each capture, evaluate receiver sites
at the planted location and at 10, 25, 50, 100, 250 and 500 km along four
cardinal bearings. The zero-displacement condition is sampled once per
capture. Bearings are measured clockwise from north, with one receiver
site evaluated independently at a time. Offsets use the spherical
great-circle destination.

At each site evaluate every causal object visible during the sampled
tracklet at elevation above five degrees. Use centered CFO training
shape to form the same 16-candidate shortlist for all score variants
and both calibration arms. Use no planted IDs to score candidates or
select the shortlist. Compare tracklet IDs and distinct emitters after
nomination. Present recall and spread across sites and bearings and
separately count truth visible and present in the common shortlist.
Record elapsed time and catalogue projection counts at each hypothesis.
This experiment leaves the fresh acceptance results and receiver
implementations unchanged.
