# ADR 0007: Sky prediction geometry and its numerical conventions

Status: accepted

Decision date: 2026-08-20 UTC

Authorization: the project owner requested a TLE interface that accepts a GPS
position and antenna pointing and reports the likely Starlinks in the field of
view together with their expected Doppler.

## Context

The hourly collector added in `292437a` fills
`/var/lib/leo/tle/archive/<provider>/<collected_utc_ns>-<sha256>.tle` with
Starlink element sets, but nothing consumed it. Separately, the analysis graph
has carried a `tle-associate` stage since the beginning whose predictions
argument is a literal `None` at `src/leo/analysis/adapters.py`, so every
association returns `unavailable` with the reason *"TLE predictions were not
supplied"*. The stage is marked optional for that reason.

This slice supplies the missing middle: a pure geometry and Doppler core, plus
a verified reader over the archive. It adds no HTTP, CLI or browser surface;
those follow separately.

## Decision

### Layering

`leo.sky` is pure. It imports numpy and `sgp4` and nothing from the catalog,
storage, HTTP or CLI layers, in keeping with ADR 0001. Filesystem access and
digest verification live in `leo.operations.tle_archive`. The two meet only in
`leo.application.sky_field`.

### Propagation runs on the server, never in the browser

One tested propagator, in Python, is the authority for every number the system
reports. A browser view may interpolate positions the server supplies, but it
never runs its own propagation, so there is no second implementation whose
agreement has to be maintained and tested.

### The field of view is a circular cone plus a horizon mask

`BeamPointingV1` carries a boresight azimuth and elevation, a half angle
measured from boresight, and an elevation mask. A wide half angle degenerates
to "everything above the mask", which covers whole-sky browsing. A rectangular
beam is deliberately not modelled now; if a real feed needs one it becomes an
additive kind rather than a change to this contract.

Angular separation from boresight is computed between unit vectors, not by
combining azimuth and elevation differences. A naive difference is badly wrong
across the north wrap and near the zenith, where two objects one degree from
the pole can have azimuths 180 degrees apart.

### Altitude is ellipsoidal, and the contract says so

`ObserverSiteV1.altitude_m` is height above the WGS84 ellipsoid, because that
is what the geodetic-to-ECEF conversion consumes. Around San Francisco Bay the
ellipsoid and the geoid differ by roughly 32 m. The difference is immaterial
for pointing — 32 m against a 550 km slant range is 0.003 degrees — but an
ambiguous unit in a persisted contract is a defect regardless of its magnitude.

### Sampling selects candidates; it does not decide membership

An earlier revision of this document claimed that choosing the sampling spacing
from the beam width guaranteed a transit could not be missed. That claim was
wrong. The dwell it derived from assumes a diametric crossing, but a grazing
chord is arbitrarily short: an object whose closest approach is 2.99 degrees
against a 3.00 degree cone is inside for 0.33 s, and is missed even at the
finest sampling the window contract permitted.

Screening is therefore two-stage. The coarse pass classifies each object three
ways using a margin equal to the furthest the look direction can move between
samples — at most `rate * spacing`. An object outside the relaxed cone at every
sample cannot have entered the true cone in between, so the coarse pass has no
false negatives however brief the transit. Only the ambiguous band is
re-evaluated on a fine grid, which keeps cost proportional to the objects whose
membership is genuinely in question. Against the live snapshot a whole-sky
request refines 189 of 10,956 objects and completes in under a second.

The fine grid is capped, so the achieved angular tolerance is *reported* rather
than assumed: `screening_angular_tolerance_deg` states what the run actually
delivered.

The fine pass is still discrete, and its residual error is bounded by that
tolerance. A sample landing at 3.00004 degrees against a 3 degree cone is
therefore not evidence the object was outside; the decision sits inside the
resolution band. Such objects are retained and marked `boundary_uncertain`, and
the report counts them. Both boundaries count: an object within a tolerance of
the horizon mask is as undecided as one within a tolerance of the cone edge.

The relaxed test that *retains* a borderline object is never the test that
*reports* it. `within_beam_at_anchor` is evaluated exactly, because a relaxed
mask would otherwise call a below-horizon sample in-beam and certain. Erring toward inclusion is deliberate: this is
candidate evidence, and a false negative — silently omitting an object that was
in the beam — is the worse error.

Objects are ranked for truncation by their closest *observable* approach, not
their closest approach overall. An object whose nearest pass happened below the
horizon mask would otherwise outrank one that was genuinely closer while
visible, and at the reporting limit that discards the better candidate.

Every reported object's numbers come from the fine grid, not the coarse one. An
object selected by refinement can have no eligible coarse sample at all, and
reporting it from the coarse track produced an infinite closest approach that
the contract rightly refused. Coarse separation now serves only to order
objects before truncation.

### Eligibility is evaluated per knot, and screening resolution is derived from the beam

An object counts as in-beam only when it is inside the cone **and** above the
horizon mask at the same sampled instant. Reducing the two conditions
independently — peak elevation over the window against minimum separation over
the window — admits an object that was inside the cone at one instant and
observable at a different one, having been observable at neither.

Screening resolution is derived from the beam rather than inherited from the
window's presentation sampling. An object crosses a cone of half angle `h` in
roughly `2h / rate` seconds, and at 1.5 deg/s a 3-degree beam is crossed in
about 7.6 s. The 5-knot presentation default samples every 30 s, so a whole
transit can fall between knots.

The two grids are separate types rather than one contract reshaped. Copying a
`SkyWindowV1` and overwriting its sample count bypasses its validators —
`model_copy` does not revalidate — and produced unevenly spaced knots, which
silently corrupts the time base of the Doppler fit. `SamplingGrid` is an
internal structure with explicit instants; `SkyWindowV1` remains what the
operator asked for.

The effect on real data is not marginal. Against the 10,956-object snapshot
collected 2026-08-20, a 3-degree dish at azimuth 180 / elevation 45 finds four
objects at derived resolution and one at the presentation default.

### The window's sample count must be odd

The anchor is the operator's chosen instant and every consumer needs it to be
one of the sampled instants. An even count places no knot there, so the
contract rejects it. Before this rule a valid persisted window could reach a
consumer that assumed the anchor was present.

### A failure to compute is never reported as a fact about the sky

Saying an object was outside the beam claims knowledge of where it was. A
propagation failure supports no such claim, so failures found during refinement
are carried into the exclusion summary as failures rather than being charged to
the beam. The same check runs on the final reporting pass: objects that never
needed refinement were only proven usable on the coarse grid, and the fine grid
evaluates instants the coarse one never touched.

### Objects are excluded for exactly one stated reason, and the reasons are counted

An element set leaves a report because propagation failed, because the orbit is
implausible, because it never rises above the mask, or because it never enters
the cone. `SkyExclusionsV1` reports all four counts, so "nothing in the beam"
is distinguishable from "nothing was considered". The four categories partition
the snapshot exactly, and `SkyFieldReportV1` enforces that partition: a report
whose selected and excluded objects do not add up to the snapshot inventory
cannot be constructed. The live archive makes the
plausibility guard necessary rather than theoretical: the snapshot collected on
2026-08-20 contains two Starlinks that propagate below 100 km altitude against
a healthy median of 471.8 km.

### Element sets are validated here, not by the propagator

`sgp4.Satrec.twoline2rv` is deliberately lenient: it verifies neither the mod-10
checksum nor that the two lines name the same catalogue object, so a corrupted
digit is propagated as a plausible but wrong orbit. Each record is therefore
checked for exact 69-character lines, a valid checksum on both lines, and
agreement between the two catalogue numbers. A malformed pair fails the whole
catalogue rather than being skipped, so a damaged archive cannot masquerade as
a smaller constellation. All 10,956 records in the live snapshot pass.

### Freshness is measured from the element epoch, not from collection time

These are different quantities and conflating them is misleading: a snapshot
fetched seconds ago can carry decades-old elements, and an earlier revision
reported a year-2000 element set as zero seconds old and fresh.

Each object therefore carries `element_epoch_utc_ns` and `element_age_s` taken
from its own element set, and the report carries `collection_age_s` separately.
Element age is a magnitude. An element set dated after the observation is
propagated backwards and is no more trustworthy than an equally old one, but a
signed age made a future epoch look fresh. Staleness is judged on the absolute
element age against a documented 24-hour threshold,
because published elements drift 1-3 km per day along track, which beyond a day
is comparable to the ground footprint of a degree-wide beam.

The report-level maximum is taken over the *reported* objects rather than the
whole catalogue. A catalogue-wide maximum is dominated by whatever the
provider's own query window admits — Space-Track returns elements up to ten days
old — and would mark essentially every report stale while saying nothing about
the answer.

### Archive references are data, not authority

A `TleSnapshotRef` is not trusted to name a path inside the archive. Its
location is re-derived from the configured root, the provider and the canonical
file name.

Refusing a symlink at the final component alone is not confinement: a symlinked
archive root, or a symlinked provider directory, redirects the read just as
effectively. Every component is therefore opened relative to the previous one
with `O_NOFOLLOW`, the same retained-descriptor discipline
`leo.station.pinned_loader` uses for authority documents. The walk begins at
`/` and covers the configured root's own components, because `O_NOFOLLOW`
constrains only the final component of the path it is handed: opening
`/a/b/root` directly still follows a symlinked `/a/b`. All four bypasses —
forged path, final-component symlink, symlinked root, symlinked intermediate
directory — were reproduced before the fix and are covered by tests.

### Doppler is reported as derivatives at a reference instant

`DopplerPolynomialV1` carries `frequency_at_reference_hz`, `slope_hz_s` and
`acceleration_hz_s2` under exactly those names, matching the `TlePrediction`
shape the association stage already expects and the degree-1/2/3 CFO
trajectories the Standard pipeline fits to observed signals. A prediction can
therefore be compared against an observation without reshaping either.

The classical first-order shift is used. The relativistic correction at orbital
speeds is parts in 1e10, far below the error contributed by element-set age.

## Numerical conventions

Two conventions were adopted because tests caught the alternatives failing.

**Inverse trigonometric functions are chosen for conditioning, not brevity.**
Elevation uses `arctan2(up, hypot(east, north))` rather than
`arcsin(up / range)`, and boresight separation uses `arctan2(|a x b|, a . b)`
rather than `arccos(a . b)`. Both `arcsin` and `arccos` have unbounded
derivative at the edge of their domain, which is precisely where a zenith pass
and an on-boresight object land. Measured against closed-form cases, the naive
forms lost roughly half the available precision: elevation returned
89.99999879 degrees for an exact zenith, and separation returned 1.2e-6 degrees
for an object exactly on boresight.

**The cone boundary is inclusive up to a stated tolerance.** An object placed
exactly on the half-angle must be selected deterministically rather than by
whichever way the final rounding went, so the comparison carries a 1e-9 degree
tolerance — far below any physically meaningful pointing accuracy.

## Consequences

**SGP4 velocity is not the derivative of SGP4 position.** Differencing SGP4's
reported position against its reported velocity leaves a residual near
1.2e-3 km/s that does not shrink with step size; it is a property of the
theory, not of this repository. Two things follow. Range-rate correctness is
verified against a synthetic exactly-consistent orbit, where the central
difference converges at second order as it should, and SGP4's own inconsistency
is pinned by a separate characterisation test so that a future change in the
propagator is noticed. The practical effect on predicted Doppler is a few Hz to
a few tens of Hz at Ku band, well below the error contributed by element-set
age.

**UT1 is approximated by UTC and polar motion is neglected.** The first rotates
the Earth by at most 0.00375 degrees, displacing a 6,900 km orbit radius by
under 500 m; the second is worth a few metres. Both are far below the angular
scale of any real antenna beam, and both are stated in the module that makes
the approximation.

**Predictions are not detections.** A report says that a published element set
places an object in the beam. It makes no claim that anything was received,
detected, attributed or identified, and the contract docstrings say so. This
preserves the candidate-only vocabulary the rest of the system maintains.

## Alternatives considered

**Propagating in the browser with `satellite.js`.** Rejected: it would let a
globe animate without refetching, at the cost of a second propagator whose
agreement with the Python one becomes a standing test obligation.

**Reusing `receiver_path` and `hardware_epoch` to describe pointing.** Rejected:
those tables carry hardware identity, not geometry, and the LNB topology
evidence in `docs/qualification/station-topology/` records `lnb_id` and
`receiver_chain_id` with no pointing at all. Observer position and beam
geometry are new concepts and get new contracts.

**Deriving the observer position from the station topology.** Rejected: there
is no latitude or longitude anywhere in the repository. The interface opens
with no site selected, and the operator supplies one or picks a reviewed preset
whose provenance and position uncertainty are recorded alongside it.
