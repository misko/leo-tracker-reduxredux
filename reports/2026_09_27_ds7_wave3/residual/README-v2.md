# DS7 residual audit v2

This reference-free audit compares the frozen first-eight joint and independent
predictions on identical masks and banks. Every response is now bound to its
sealed request, response digest, and exact session order. Candidate weights,
MAP selection, and stationary offsets use training observations only. Held
predictive density uses those fixed training quantities.

The principal result is unchanged: the joint fit loses 713.85 training nats and
432.55 fixed-parameter held predictive nats relative to the independent fits.
Pooled held RMS is 427.78 versus 418.18 Hz. Seven of eight recordings lose held
predictive density. The eighth recording contributes 342.13 training nats and
183.29 held nats of the loss; its worst track contributes 134.03 and 120.72
nats respectively.

Training posterior concentration is high within the frozen, incomplete bank:
median MAP probability and effective candidate count are 1.0 and 1.0. This is
conditional concentration and does not verify physical candidate identity.

Residual slopes are exploratory diagnostics, not calibration fits or evidence
of receiver drift. For each track, normalized time is centered separately on
training and held partitions before pooling by receiver/channel or RF. Several
groups have large slopes, but training and held magnitudes and signs are not
consistent enough to admit a clock or slope nuisance model. For example,
receiver 1/channel 3 changes from -456.66 Hz per normalized recording on train
to +1270.29 Hz on held, while receiver 0/channel 4 remains negative at -478.78
and -838.34 Hz. These patterns motivate investigation but do not establish a
shared correction.

The CFO unit trace resolves a critical ambiguity. The public loader exposes the
native `fractional_tracking_cfo_hz` and actual RF. Persistent trajectory
reconstruction explicitly multiplies native CFO by
`canonical_rf_hz / actual_rf_hz`, de-aliases in that normalized domain, and
persists `normalized_dealiased_cfo_hz` as `measured_cfo_hz`. Its canonical RF
defaults to 11.2 GHz. The baseline's 11.2 GHz prediction convention therefore
matches the persisted numerical observations; no RF rescaling correction is
justified.

The residual evidence does not admit a new clock/slope nuisance. The next
scientifically clean discriminator is frozen temporal transfer to the later
chronological group, with unchanged model, banks, and arm. This tests whether
the first-eight behavior persists outside the development interval without
using scores or held samples to tune a correction.

`audit-v1.json` is preserved. `audit-v2.json` contains the hardened source
bindings and partition-centered train/held slope diagnostics. The v2 analyzer
completed in under 11 seconds.

