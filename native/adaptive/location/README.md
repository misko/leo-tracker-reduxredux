# Native adaptive location component

This directory implements the portable C5/C6/C7 numerical boundary described
in `plan.md`. `location.h` is the integration surface. Production callers pass
immutable TLE, orbit, track, and receiver records; the component does not know
about Python, PostgreSQL, HTTP, devices, or repository paths.

Prepared Doppler fragments can also be passed to the experimental
[Doppler candidate matcher](doppler_match/README.md), through its C++
`doppler_match/matcher.hpp` port. It streams a caller-supplied TLE catalogue
through small orbit buffers and returns per-fragment satellite/position/time
candidates. It is part of this library; `leo-doppler-match` is its separate
recorded-input adapter.

The explicit-path CLI supports final association scoring at a selected regional
point: `leo-location score-at FIXTURE ORIGIN_LAT ORIGIN_LON EAST_KM NORTH_KM
[WORKERS]`. It uses the same site transform as regional search and always runs
full association scoring, including when the binary contains research-only
capped-objective search support. It does not consume fixture comparison sites
for this mode. Its output has the same score JSON shape as ordinary `score`,
with one site. Nonfinite coordinates, invalid origin ranges and unsupported
worker counts are rejected. Site transform rounding can differ across platforms;
compare scorer arithmetic using identical site components when diagnosing it.

## Build

```sh
native/adaptive/location/build.sh host /tmp/leo-location-host
native/adaptive/location/build.sh sanitize /tmp/leo-location-sanitize
native/adaptive/location/build.sh arm /tmp/leo-location-arm
```

Each build produces `libleolocation.a`, `libleolocation.so`, `leo-location`,
`leo-orbit`, `leo-doppler-match`, and component unit executables, including
`test_doppler_match`. Host and sanitizer builds run unit and CLI tests.
The ARM build compiles the same unit executables for later
device execution. ARM outputs statically include libstdc++ and libgcc while
retaining the target libc, libm, and pthread dependencies.

The source-owned SGP4 implementation is version 2.27 from the locally pinned
Python distribution. Its license is preserved in `vendor/sgp4/LICENSE`.

## Contracts and ownership

- An orbit context owns two fixed-capacity state banks. A successful refresh
  atomically publishes an immutable generation view; a failed refresh leaves
  the previous view intact.
- A score context owns residual and interpolation scratch and is used by one
  worker at a time. The interpolation stencil stores the exact knot index and
  Hermite coefficients once per observation/tau pair, then reuses them across
  eligible satellites. Scratch grows lazily and is bounded to 16,384 stencils
  (1,179,648 bytes) per context. Allocation failure or a larger request uses
  the generic interpolator without changing the result. Separate contexts may
  score fixed satellite ranges concurrently. `leo_track_scores_reduce`
  combines those partitions in deterministic order.
- A search context owns a bounded best-first frontier. `next` and `submit` let
  the caller pause between batches. Every operation is generation checked, and
  cancellation is explicit.
- Inputs and result arrays remain caller owned. No component function creates a
  thread or a nested worker pool.

The `leo-location` adapter reads the research-private LOC1 fixture only when an
explicit path is supplied. It is a replay/deployment diagnostic, not a public
persisted format:

```sh
leo-location score FIXTURE [WORKERS]
leo-location search FIXTURE LATITUDE LONGITUDE RADIUS_KM [WORKERS]
```

`WORKERS` is 1 or 2. Two-worker scoring partitions the catalogue into fixed
contiguous ranges and reduces in worker-index order. It does not change the C
API's scheduling ownership.

The search diagnostic emits
`org.leo.native-adaptive-location-search/v2`. `complete=false` with
`stop_reason=point-budget-reached` means the configured point budget was
consumed while `deferred_cells` remained; it is a valid bounded result, not a
claim of global convergence. The component DS9 integration test runs both
original 400-point regional searches through the real scorer and scheduler,
bounds each host subprocess to 300 seconds, and compares the complete ordered
point inventories and scores to the frozen reference at a predeclared
`1e-9 Hz` tolerance.

## Scientific scope

The C++ `session.hpp` port accepts a `LocationInputView` borrowing an immutable
orbit snapshot and track arrays. `search_location` runs the existing 400-point
search with one or two workers, optionally recomputes full final associations,
and returns owned `SearchOutput` values. Inputs must remain alive and unchanged
until return. An optional callback reports progress on the calling thread;
failure leaves the previous output unchanged. The implementation has no file
or CLI dependency. The replay CLI uses this same port while preserving its
existing input/output formats. This port enables direct native composition;
it does not by itself qualify continuous processing.

The orbit replay port is:

```sh
leo-orbit TLES.txt START_UTC_NS KNOT_START_S KNOT_STEP_S KNOT_COUNT OUTPUT.states
```

The input contains a count followed by that many pairs of 69-character TLE
lines. Numeric and Alpha-5 catalogue IDs are supported. Output is little-endian
satellite-major float64 position (km) and velocity (km/s); stdout records the
epoch, knot grid and ordered catalogue IDs. Host builds run twelve CLI rejection
cases in addition to the scientific native tests. Catalogue eligibility remains
the caller's responsibility.

For native pipeline composition, append
`--loc1-site X_KM Y_KM Z_KM UP_X UP_Y UP_Z` to write the existing LOC1 authority
layout instead of raw states. This output contains zero tracks, the generated
catalogue/states and one explicit diagnostic site; the track adapter fills the
measured tracks later. The up vector must be unit length. This option avoids
host-side state packaging and does not change the default output format.

The scorer preserves the DS9 prototype semantics: cubic Hermite interpolation,
the conservative interpolant-horizon rejection, integer tau profiling on the
training partition, fitted frequency offset, evaluation-RMS identity choice,
represented-second weights, and the 800 Hz capped objective. The Bezier test is
only conservative for the interpolated curve; it is not an SGP4 error bound.
The bounded search is a deterministic diagnostic and does not establish a
confirmed position or a real-time IQ-to-location pipeline.

`test_score_stencil` compares every planned state bit for bit with the generic
orbit interpolator across knot boundaries, nonintegral times and error cases.
It also exercises reusable scratch, forced allocation failure, the hard scratch
bound, empty partitions and fully rejected tracks. The frozen research profile
and physical qualification are recorded under
`reports/2026_09_30_native_adaptive_deployment/location/interpolation-stencil-research/`.
