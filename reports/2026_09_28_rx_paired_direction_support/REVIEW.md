# Independent review: paired receiver direction support

## Pose and mapping evidence

No repository evidence supersedes `gauss-r20-roof-20260926-v1` with a verified cable trace or a
measured world-frame tilt.  The current [pose authority](../../deploy/station/gauss-r20-roof-20260926-v1.json)
still says all of the following explicitly:

- physical connector RX1 is assigned to software receiver 0 and nominal azimuth 270 degrees;
- physical connector RX2 is assigned to software receiver 1 and nominal azimuth 90 degrees;
- both assignments have `mapping_status: provisional`;
- the orientation evidence is operator-reported RX2 east/RX1 west and is “not a cable trace”;
- geographic north is assumed, receiver elevations are null, the directed phase-center baseline is
  null, and RF phase centers and world tilt are unmeasured; and
- 10 degrees outward and 0.08 m separation describe nominal fixture geometry.

The corresponding [operations record](../../docs/operations/radio20-roof-pose-20260926.md) repeats
that physical RX1/RX2 to software RX0/RX1 is provisional and that actual elevations, RF phase
centers, and the directed baseline remain unknown.  It also says the companion publisher preserves
capture-linked evidence but tracking does not consume it automatically.  The production
[deployment instructions](../../docs/operations/production-deployment.md) are stronger operational
evidence against treating the mapping as verified: they say not to use baseline direction until a
cable trace supports a new authority revision.

The referenced `.21` fixture authority does not fill this gap.  Its slot axes encode the nominal
`sin(10 degrees)` fixture geometry, while `rf_boresight_unit` and `rf_phase_center_position_m` are
null.  Its receiver assignments are also provisional and state that the physical left/right cable
trace was not recorded
([`gauss-r21-lt3d-001a-20260920-v1.json`](../../deploy/station/gauss-r21-lt3d-001a-20260920-v1.json)).
The current `.20` record says only that its fixture is identical to this nominal design; it does not
transfer `.21`'s physical receiver identities or verify `.20`'s cables.

The earlier [pose provenance audit](../2026_09_28_rx_geometry_support/POSE.md) remains accurate:
the saved feature signs are internally consistent with the recorded nominal convention, but that
convention is not physical metrology.  Repeated copies of the same pose object in manifests are
capture bindings, not independent cable or orientation observations.  A swapped-sign result may
therefore measure sensitivity to a convention; it cannot establish reversed cables.  This review
found no newer authoritative revision that changes that conclusion, and it does not modify the
pose authority.

## Appropriate scope for a support audit

A first stage should be descriptive and frequency-free.  For every exact source window and RF lane,
retain both receiver candidate arrays, including empty arrays, and export paired summaries before
looking at satellite labels:

- passed-candidate counts `(n0, n1)`, their difference, sum, and the four availability states;
- candidate-level `fractional_margin`, rank, candidate ID, and frequency, preserving duplicates;
- receiver summaries fixed in advance, such as maximum margin, sum of margins, and top-rank margin,
  with a separate missing indicator rather than replacing an empty set by a numerical zero; and
- forecast-only partial-arc variables for every retained `(track_id, catalog_number)`: nominal
  receiver contrast, its time change/secant, visibility, prior mass, and whether materially weighted
  nominees in the same lane disagree in sign or trajectory ordering.

Aggregate windows within lane and record before equal-record summaries.  Report reception and held
roles separately and preserve actual irregular times.  Forecast support may be summarized over all
roles because it contains no detector outcomes, but no post-outcome support threshold may select the
detector population.  The useful question at this stage is whether a receiver-relative count or
margin asymmetry varies with a predeclared forecast contrast and whether competing nominees predict
different partial-arc patterns.  This is a support/identifiability check, not a fit or identity score.

## Scientific pitfalls and required controls

`fractional_margin` is a detector gate margin, not received amplitude, calibrated power, SNR, or an
antenna-gain measurement.  The geometry dataset retains only candidates that passed the fractional
margin gate.  Its observed rows contain candidate ID, rank, canonical frequency, and margin; they do
not contain failed candidates or a continuous uncensored amplitude.  Any “mark” conclusion must be
named as passed-candidate detector margin and conditioned on this censoring.

Candidate count is also not source count.  In the first calibration window, distinct candidate IDs
and ranks can carry identical canonical frequency and identical fractional margin.  These may be
multiple detector hypotheses for one feature.  Deduplicating them after seeing a favorable result
would be selection, while treating them as independent satellites would be false.  Export both raw
candidate rows and deterministic equivalence groups defined before outcomes, for example exact
receiver/window/frequency/margin equality, and show sensitivity of count summaries to that grouping.
Do not infer simultaneous emitters from either version.

Receiver observations in one source window share acquisition conditions and detector processing;
individual candidates are not independent trials.  Uncertainty and sign counts must therefore use
record or lane clusters, not candidate rows.  Receiver candidate arrays may also have different
missingness or gate behavior.  Separate empty receiver arrays from present arrays with low margins,
and report support denominators rather than conditioning only on windows where both receivers fire.
Conditioning on “both present,” a close frequency match, a selected candidate, or a later successful
forecast would create collider/outcome selection and discard precisely the directional absences the
audit is meant to describe.

The two receiver streams need exact source-window pairing and the existing training-only receiver
CFO calibration, but frequency must not choose which margin/count rows enter.  Candidate rank is
receiver-local and should not be paired across receivers as an identity.  Likewise nearest frequency,
same rank, same catalogue forecast, or shared track is not a decoded same-emitter label.  The current
track artifacts contain duplicate cross-receiver views and same-catalogue hypotheses; any later
association model should group those semantics before interpreting paired response as target
presence.

Partial-arc forecast disagreement should retain every nominee and its frozen prior.  Report prior
mass for positive, negative, zero, and unavailable secants, plus pairwise opposite-sign mass.  Do not
apply a material-weight cutoff that can manufacture disagreement, flatten priors, or select the one
DS8 lane noticed after inspection.  Full scheduled peak order was almost uniformly unavailable or
one-sided in the previous [direction-support audit](../2026_09_28_rx_ds8_alignment/README.md); a
partial-arc secant can show usable variation but does not become a beam crossing or geographic travel
direction.  Visibility, boundary maxima, time gaps, and candidate membership must remain explicit.

Minimum negative controls for the descriptive relation are receiver-label swap, within-role time
reversal, and candidate-geometry permutation while leaving observed receiver arrays fixed.  A
common-mode control using up/elevation without the receiver sign helps distinguish generic pass
evolution from differential response.  Because the cable mapping and world tilt remain provisional,
both nominal sign conventions should be exported as labeled sensitivity views; neither may be
selected as the physical convention from these reused outcomes.

## Decision

The proposed bounded support audit is worthwhile if it remains a census of censored detector marks,
paired availability, and forecast disagreement.  It can answer whether the existing corpus has
enough receiver-relative and candidate-specific variation to justify a later frozen likelihood.  It
cannot validate the 10-degree axes, identify a satellite, prove arrival order, measure antenna gain,
or resolve the cable mapping.  A later fit should proceed only if the descriptive support is not
dominated by duplicate detector hypotheses, both-receiver conditioning, one record, or one common
forecast sign.  Verified direction ultimately requires a new pose revision backed by cable trace and
world-frame antenna-axis evidence, or a predeclared sign nuisance confirmed on unused records.
