# Conservative quadratic primary timing, development v2

Only the exact 576 development cells /288 paired windows from the sealed round1
panel are used. Read round1 prediction_packets.json, preserve its primary
branch/donor IDs/ranks/native support and every CFO value. Do not re-associate,
re-rank, read target candidates, or open validation tracking files. Freeze
this source/tests, input hashes and all forecasts before archived target
evaluation or dependent raw scoring. No target bias subtraction or RF coupling.

Use timing quadratic only for at least five distinct earlier donors spanning
at least one second. Fit an unweighted quadratic using centered/scaled time
and lstsq; require rank three, design condition number <=100, |timing
acceleration|<=10samples/s², and |propagated timing rate|<=200samples/s over
target start/midpoint/end. The rate check over all three references makes the
whole target's constant-epoch approximation explicit. Otherwise retain the
original linear/one-donor fallback and report every reason. A cell without a
donor stays unavailable. No target-dependent choice or extra alternative trial is added.

Reference convention: each historical constant epoch is a frame start relative
to its window origin, treated here as a NOMINAL MIDPOINT-EFFECTIVE phase
measurement. This is a convention/approximation, not established instantaneous
phase or measured pilot-weighted time. Fit phase from epoch+origin counter
differences against donor midpoint counters. Evaluate the scorer's constant
phase at target midpoint, then express it as an epoch relative to target
origin. Also publish origin/end model evaluations and rates explicitly. Because
all donor/target windows are20ms, a common origin→midpoint reference shift
cancels in full-window extrapolation.

This convention keeps the consistent constant-epoch LINEAR control exactly
equal to round1 predictor primary.full.epoch_samples. Round1's timing adapter
added another rate*0.010s. Preserve its exact legacy-adapter linear epoch as a
separate descriptive control and record its signed difference. Do not silently
recast round1 raw scoring as identical. Either effective-time convention can
be imperfect when pilot weighting varies; independent validation must review
this assumption. No raw outcomes decide the convention.

Keep the earlier CFO and nominal midpoint reference unchanged. For quadratic
timing covariance use max(0.75²,RSS/(n−3)) sample variance and scaled QR/lstsq
design covariance. Forecast variance is measurement variance*(1+leverage)+2²
samples², adding the declared two-sample model discrepancy in quadrature.
Publish coefficient covariance/acceleration SE, span, condition and uncertainty
at each reference. These are engineering scales, not calibrated RF weights.

The timing worker compares one consistent linear point and one
quadratic/fallback point on identical full20ms target support with unchanged
conditioned GLRT. There is no timing search or target-selected mode. The legacy
adapter control is descriptive/optional and must not silently increase a
method's acceptance trial budget. A profiled frequency bin is not automatically
an independent accurate Doppler point; that qualification is separate.

After forecast sealing, an archived DEVELOPMENT diagnostic may reuse exactly
the round1 CFO-only match policy: original gatepassing rank<=8 target closest
to unchanged primary CFO within500Hz, ties original rank. Timing never chooses
the target. Evaluate all three timing controls against that same match, with
every no-donor/fallback/miss visible. Do not retune after those results. No
validation target outcomes or raw IQ are read in this branch. Use BLAS1 and
580-second numerical bounds. Round1 sources and outcomes stay unchanged.
