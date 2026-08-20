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

### Objects are excluded for exactly one stated reason, and the reasons are counted

An element set leaves a report because propagation failed, because the orbit is
implausible, because it never rises above the mask, or because it never enters
the cone. `SkyExclusionsV1` reports all four counts, so "nothing in the beam"
is distinguishable from "nothing was considered". The live archive makes the
plausibility guard necessary rather than theoretical: the snapshot collected on
2026-08-20 contains two Starlinks that propagate below 100 km altitude against
a healthy median of 471.8 km.

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
