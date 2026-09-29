# Whole-domain cone exclusion before a hard-cone fit

This diagnostic asks whether changing position or timing anywhere inside the
existing search bounds can rescue an unsupported track. It does not fit a
location, select a beamwidth, change the frozen cone/trend experiment, or
establish sub-km performance. Run only when the current fitting worker is
terminal. Use the eighteen fixed consecutive panels and the existing cached
candidate banks; main dataset aggregates use the nine nonoverlapping eight-scan
panels so each of 72 scans appears once.

Freeze nominal receiver axes at west/east 10 degrees from zenith and evaluate
20/30/40/50-degree half-angles, including all sixteen width pairs in reporting.
World pose and receiver mapping remain uncalibrated assumptions. Use the
existing geographic coordinate map about its inherited center, E/N +/-12 km,
zero altitude, and the entire linearly interpolated timing bank [-5,5] seconds.
Do not consult the exposed reference to construct or select the domain.

For each candidate and timing segment, anchor its ECEF positions at the
segment midpoint. Half the endpoint displacement bounds satellite movement
through that segment at each observed time. A conservative receiver displacement
bound covers the entire position box. Add these radii to bound changes in the
line-of-sight vector. For a ball of radius d around a vector of length r, its
angular radius is at most asin(d/r) when d<r. Otherwise assign no exclusion.
Subtract this angle and a bound on the ENU-axis rotation from the anchor's
boresight angle. Max over training observations and min over timing segments
gives a lower bound on the candidate's best possible worst training angle.

The zero-altitude WGS84 meridional and prime-vertical radii are both below
6400 km. Latitude and longitude tangent vectors are orthogonal. Integrating
along a straight path in coordinate space gives receiver displacement at most
6400*sqrt(dlat^2+(max_cos_lat*dlon)^2). Frame rotation is bounded by dlat+dlon.
The implementation subtracts 1e-8 degrees as a numerical guard and requires a
further 1e-7-degree strict margin before exclusion. This is a conservative
analytic bound evaluated in floating point, not formal interval arithmetic.

A candidate is excluded only when that bound exceeds its RX half-angle. A
track is excluded only when every retained candidate is excluded. One excluded
track rules out a complete all-track satellite explanation for that scan
within this bank/domain/pose. All retained candidates are included, even those
not passing a horizon gate, making exclusions conservative. Nonexcluded means
unresolved, not feasible: different tracks or observations may still require
incompatible positions or timings. An unassociated/background explanation is
not a complete satellite explanation. A failure within this bank does not
prove that the full satellite catalogue has no explanation.

Before evaluating data, pass synthetic tests for receiver and axis envelopes,
whole-track support and held isolation, sampled interior timing/position
geometry, an interior cone crossing with both timing endpoints outside, a LOS
ball containing the receiver, monotonic weakening as the domain expands, and
invalid input rejection. No tests or bounds may be tuned after outcomes.

For each panel, replay the earlier fixed-position nominal support audit at its
unchanged position/timings: identical track IDs, counts, minimum training
half-angles and support counts at all four widths. Require every candidate's
new lower bound to be below its actual worst angle at that old point within
1e-7 degrees. Held observations do not enter the bound or exclusion counts.
Retain every candidate bound and replay result, not just aggregate exclusions.

One worker, BLAS1/nice19, 4 GiB address-space cap, 90 seconds per child, at least
5 GiB available RAM before admission. Hash all sources and inputs before the
first data execution; verify execution sources and each child's own inputs
before and after that child. Preserve all process failures; no silent retries.
No RF collection, raw-IQ reads, new propagation, provider fetches, or production
component changes. Report all planned panels; incomplete evidence cannot
become a complete aggregate. This diagnostic supplies no new geographic error.
