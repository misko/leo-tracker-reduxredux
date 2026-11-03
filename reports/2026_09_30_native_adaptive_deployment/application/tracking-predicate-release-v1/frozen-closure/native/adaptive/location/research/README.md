# Location scoring research variants

This directory contains opt-in experiments. The production location build does
not compile these sources.

`score_interpolation_stencil.cpp` replaces only the scorer object in a separate
research archive. It includes the unchanged production scorer under a private
reference symbol, then precomputes the knot index and Hermite coefficients for
each observation/tau pair once per track. The satellite, track, tau and
observation iteration order, horizon eligibility test, state arithmetic,
finite-output check, residual reduction and tie breaking remain unchanged.
Stencil construction is lazy, so empty satellite partitions and tracks rejected
by the horizon test retain the reference behavior without allocating or
interpolating.

Build and test it with the component-owned recipe:

```sh
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  host /tmp/leo-location-stencil-research-host
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  sanitize /tmp/leo-location-stencil-research-sanitize
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  arm /tmp/leo-location-stencil-research-arm
```

The host ABBA comparison is bounded to at most eight four-run sequences:

```sh
tests/native_adaptive/location/research/run_score_interpolation_stencil_abba.sh \
  /tmp/leo-location-stencil-research-host \
  reports/2026_09_30_native_adaptive_deployment/tracking/native-e2.loc1 \
  /tmp/leo-location-stencil-research-host/abba 4
```

The research test compares planned interpolation bit for bit with the public
generic interpolator at knot boundaries, the final knot and nonintegral times.
It covers nonfinite state propagation, invalid and overflowing snapshots, a
final-knot rounding rejection, empty partitions, fully rejected tracks, and
exact candidate/reference scoring. The full fixture comparison additionally
requires identical one-worker and two-worker JSON output.

This experiment does not alter the location ABI, eligibility, tau grid, search
policy, golden fixtures, or production defaults. Allocation failure for the
additional per-track scratch remains a research qualification item before any
production proposal.
