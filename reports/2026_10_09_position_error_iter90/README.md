# Iteration90 preparation: are paired receiver differences clock-confounded?

Prepared diagnostic only; no recording has been evaluated here. Proceed only if
the complete iteration87 audit supports investigating paired receiver bias, after
parent review, source/input freeze and capacity approval. No new position,
accuracy claim, nonlinear optimizer, production change, RF collection or reserve
outcome access is authorized by this preparation.

All148 consumed recordings remain in the protocol: DS16 63, DS17 51 and DS18 34,
including the original48 plus15 and prior-exposure metadata. Reconstruct each
immutable iteration85 B7 model through iteration87's qualified reconstruction;
both accepted endpoint objectives must match within1e-6 before diagnostics.
Known receiver coordinates/errors are not grouping, selection or solver inputs.

## Pairing and matched arms

Freeze the maximum fitted-B7 responsibility assignment strictly above0.5 and use
it in both c arms. Extract each arm's wrapped residual for that shared satellite.
Join by satellite/channel/time tick `round(time_s*1000)`, using Python nearest
integer ties-to-even. Average duplicates within each receiver before forming
RX1-minus-RX0. Retain pair ticks, channel, duplicate counts and each receiver's
mean original time, exposing residual timestamp differences. No nearest-time
substitution. The resulting pair membership must agree exactly between arms.

Both arm-specific pair residuals are diagnosed separately; this does not define
two different operational correction policies. Any later matched positioning
experiment would freeze one fitted-derived correction across arms and disclose
that conditioning. Static c and RF-time coefficients remain zero in the existing
c0 endpoint. No reference-guided adjustments or inferred LNB diagnosis occur.

## Geometric limitation

An antisymmetric receiver correction contains no direct common geometric
information. With perfectly paired, balanced Gaussian measurements and known
assignments, adding−d/2 to RX0 and+d/2 to RX1 changes the differential residual
sum of squares but leaves the common-mode spatial gradient unchanged. Any
position benefit would have to arise through unpaired/unequal support,
calibration coupling or changed associations. A residual difference such as18Hz
does not imply a corresponding position gain. A future position prototype must
include a synthetic balanced-pair spatial-gradient invariance test. Common and
differential pair coordinates are a cheap equivalent representation, not a new
source of position information.

## Fixed small linear comparisons

Use the tested iteration88 projected solver and unadjusted zero-sum paired-mean
shrinkage as a confounding comparison. One fixed30Hz prior applies everywhere.
Satellites need at least10 pairs and at least2 eligible satellites overall;
unsupported cases are explicit no-ops, with no member excluded. The projected
background is an unpenalized intercept, centered/scaled linear time and
deterministic channel effects. Report data rank, weak modes and regularized rank
separately; a regularized solution does not prove physical identifiability.

The actual Hard60 frequency width is125Hz. Set pair variance to
`2*125² = 31250Hz²`, or pair standard deviation approximately176.777Hz, and
use its inverse as the precision for every pair. This is a working approximation
assuming independent equal-noise window residuals, **not calibrated pair noise**.
It ignores temporal/receiver correlation and does not award extra precision to
duplicate averages. The rule is explicit and fixed, not tuned per scan or inferred
from position accuracy. It does not confuse unit pair counts with Hz-scaled
precision.

A second globally fixed sensitivity appends only the existing B7 smooth-clock
span to that background. Take the first `model.smooth_clock_count` columns of
`model.clock_design`, average rows separately within each receiver's exact
duplicate group, then form the RX1-minus-RX0 row difference on the same paired
keys. Exclude RF-time and satellite blocks. This introduces no new knots or clock
functions. Apply the same pair weights, eligibility and30Hz prior, reporting
remaining data rank, null modes and explicit no-ops. Losing identifiable satellite
contrast directions after this projection is an identifiability finding, not a
failure. Do not select between backgrounds per scan or fit position.

Retain raw paired rows and descriptive output per member/arm. Compare unadjusted
and projected contrast magnitudes, common clock/channel effects, support and
rank. Neither a smaller residual nor a surviving contrast establishes improved
positioning or satellite hardware error. The simple time basis may be inadequate
for residual smooth-clock behavior; report that limitation before attributing
remaining structure to satellites.

## Reproducibility and next decision

`freeze.py` verifies the inherited iteration87 closure and binds its full148
membership, B7 endpoint files, model/native sources, iteration88 solver and this
diagnostic's code. It does not run the audit. Each `audit_pairs.py` shard verifies
all hashes before evaluation; receipts are append-only and retain explicit
input/reconstruction/linear-algebra failures. Reporting code can be developed
separately without changing the numerical closure.

Publish full coverage and dataset/exposure summaries before deciding whether a
position refit is justified. If paired differences disappear under common
clock/channel projection, do not add a satellite correction. If they survive,
that supports a further controlled hypothesis, not an automatic deployment.
Any subsequent positioning test needs same-start B7 zero controls, matched c
arms, complete failures/fallbacks, frequency-fit effects separate from position,
and randomized whole-group validation after global candidate selection. The
post-DS18 reserve remains closed throughout this diagnostic.
