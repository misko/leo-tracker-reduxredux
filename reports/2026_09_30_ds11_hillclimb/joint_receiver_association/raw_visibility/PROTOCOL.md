# Timing-linked raw-detection visibility calibration

Start with family2 donors16/17 and the frozen donor16 timing threshold. For each
inferred physical-source/RF/window, choose one uniquely owned retained candidate
as anchor using the smallest SHA256(candidate_id); duplicates cannot add trials.
Search all passing raw candidates on the other RX for an epoch match. The event
is a timing match, not authenticated visibility or satellite identity. Retain
raw-only partners, retained partners, conflicting inferred source ownership and
unknown partners. Also search at fixed frame-phase shifts1/7,2/7,3/7 periods as
accidental-match controls. Never turn an absent retained track into a hard zero.

Join the prior source-bound geometry and visit split exactly. Fit the probability
of an opposite-RX timing-match event conditional on its anchor, RF and candidate
geometry. Use eight receiver/RF intercepts and optionally a nonnegative elevation
or signed-boresight coefficient (nominal10degrees). This is an empirical event
model that includes detection, retention and accidental timing matches; it is
not a calibrated four-state physical antenna model. Calibrate only donor16
training visits. Validate donor17 held visits against receiver-only, elevation,
RX-swap and within-RF source-geometry permutation controls. Compare average log
scores per source, giving each source equal weight, and require a strict majority
of source wins over receiver-only plus better total source-balanced score than
every control before a position pilot. Preserve optimizer and derivative checks.

The epoch threshold was learned on donor16, so donor16 training fit is not an
independent validation. Any DS11 model requires a separate frozen protocol and
zero-evidence parity, temporal-dependence and ownership handling. Export existing
metadata only, each child<=90seconds and at most three numerical threads overall.
