# Frozen high-coverage residual-track description

Use all15 immutable DSX01 memberships (693 original GLRT winners), raw measured
CFO metadata and saved fitted-c `b1000-profile` association flags from iteration4
frequency_bias. This selects the user's requested development experiment,
462/693 assigned, not a new endpoint. No TLE, orbit, localization fit, candidate
identity, calibrated prediction, source preparation, held test or station input
enters this audit.

Partition every window into RX/channel/actual-RF lanes. Apply the unchanged old
model_b `build_tracklets` defaults (450Hz circular prediction gate,45s maximum
duration,24points) to ALL retained members in each lane, then annotate the saved
unassociated rows. Never link different lanes or globally unwrap mixed tracks.
Retain all extracted fragments and all15 window counts, including short or
rough fragments. These metadata/CFO-selected segments are descriptive, not
emitter identity or evidence of one satellite.

Within each extracted fragment only, time-order rows and accumulate principal
adjacent circular CFO differences using alias period1/4.4e-6 Hz. This chooses a
local numerical branch, not an attested carrier-cycle count. Describe native
CFO span and local unwrapped span separately. Fit a fixed quadratic for n>=5,
linear for3<=n<5, and no curve otherwise. Report in-sample RMS/max and
leave-one-out prediction RMS; do not select polynomial degree or gate using
outcomes. Report analogous quadratic/linear summaries of unassociated members
of a fragment when enough remain. These curve fits summarize frequency
smoothness only and are not localization/model fits.

Rank descriptive fragments by unassociated count, then leave-one-out RMS for
readability, retaining every fragment in JSON/CSV. There is no post-hoc
coherence threshold, candidate match or recovery claim. Preserve exact IDs,
times, raw CFO, alias increments and saved association flags for review.

Run one bounded local-array audit, externally60s TERM/65s KILL, single-threaded.
Owned synthetic tests cover alias seams, separated lane/track inputs, fixed
curve/leave-one-out summaries and short-fragment limits. No new numerical
qualification of the population model occurs.
