# Forecast-only receiver-order support audit

Before fitting a new direction model, measure whether the frozen candidate bank
contains competing nominal receiver orders. Use the original ten-record pilot
dataset and the four-record DS8 dataset separately, retaining their split labels.
Read only persisted candidate priors, LOS vectors, visibility and scheduled times;
do not read detector counts, margins, frequencies or observed endpoints.

Nominal boresights are (-sin10,0,cos10) and (+sin10,0,cos10), under the documented
provisional receiver convention. Evaluate their dot products with each stored LOS.
Export scheduled unique interior maxima and bracketed linear equal-plane zeros.
Boundary maxima, tied maxima, equal-time maxima, ambiguous zero plateaus and
missing crossings remain unavailable rather than extrapolated. No continuous
orbit peak is claimed from sampled geometry.

Retain the full scheduled geometry, including invisible points. Export visibility
at peaks and crossing brackets; an order requires visible peaks and a visible
crossing bracket. Do not remove invisible points and turn the resulting endpoints
into new interior maxima. Preserve integer source peak timestamps and use relative
time for interpolation arithmetic.

Export every nominee, including vanishing prior mass. Normalize nominee log priors
without adding a floor. Tabulate positive-order, negative-order and unavailable
mass, entropy and effective candidate count. Opposite-order pair mass is
2*p_positive*p_negative under two independent draws from the frozen conditional
nominee prior. This is a support diagnostic, not an observed direction success
rate. Report continuous support without choosing a post-outcome materiality gate.

Each run is limited to 120 seconds, one numerical thread and 4 GiB. Freeze source,
tests, protocol and dataset hashes before execution. Existing geometry schedules
are sufficient; do not collect RF, reprocess IQ, refit priors or propagate new
ephemerides. The longer DIRECTION-PLAN.md remains a proposal; this audit implements
only its forecast-support prerequisite.
