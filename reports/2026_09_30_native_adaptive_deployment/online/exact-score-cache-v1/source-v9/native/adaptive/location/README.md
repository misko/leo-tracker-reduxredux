# Native adaptive location component

This directory implements the portable C5/C6/C7 numerical boundary described
in `plan.md`. `location.h` is the integration surface. Production callers pass
immutable TLE, orbit, track, and receiver records; the component does not know
about Python, PostgreSQL, HTTP, devices, or repository paths.

## Build

```sh
native/adaptive/location/build.sh host /tmp/leo-location-host
native/adaptive/location/build.sh sanitize /tmp/leo-location-sanitize
native/adaptive/location/build.sh arm /tmp/leo-location-arm
```

Each build produces `libleolocation.a`, `libleolocation.so`, `leo-location`,
`test_location`, and `test_score_stencil`. Host and sanitizer builds run both
unit executables. The ARM build compiles the same unit executables for later
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
