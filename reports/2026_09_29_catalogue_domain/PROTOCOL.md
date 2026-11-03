# Geographic and timing domain of the local candidate shortlist

Use the same nine tracks as full_catalogue_probe: three ID-selected eligible
tracks from the earliest frozen outside target per dataset. Reconstruct the
same causal catalogue through read-only archive ports.

Freeze 14 observer positions: each dataset's N24 fit, configured center,
four ±12 km E/N corners, four interior cardinal offsets at 6 km, and four
out-of-region cardinal offsets at 100 km. Cross each with timing −5, 0, +5 s.
This gives 378 track/location/timing settings, each evaluated under training
and complete-track contrast likelihood. The 100 km points are coverage stress
tests outside the current fit bounds, not candidate location estimates.

Require exact retained-bank visibility and prediction replay <1e-6 Hz at all
tested timing nodes. Report retained signal mass and compute omitted mass
directly in log space to avoid rounding tiny tails to zero. Report omitted
best candidates and changed signal/background responsibility, by location
class and timing. No new positions, priors or RF data are fitted or collected.
Three workers, 120 seconds each. A finite grid is not a continuous coverage
bound, a calibrated posterior or blind localization evidence.
