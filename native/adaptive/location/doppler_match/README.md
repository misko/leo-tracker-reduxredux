# Doppler fragment candidate matcher

This experimental C++17 module retrieves satellite / receiver-position /
time-offset hypotheses from prepared Doppler curves and a bounded receiver
region. It belongs in `native/adaptive/location`: it composes the component's
existing orbit port, and runs on ARM without Python. Application and pipeline
code can call [matcher.hpp](matcher.hpp); file parsing lives in [cli.cpp](cli.cpp).
The numerical implementation has no filesystem, database, network, recording,
or device dependency. `detail.hpp` is private to this module and its tests.

The module is included in the existing `libleolocation.a` and `.so` builds.
The existing `location.h` C ABI and persisted server contracts are unchanged.
This is an experimental C++ API, not a new persisted schema or a deployment
default. It does not replace the existing regional search or scorer.

## Calling the module

```cpp
#include "doppler_match/matcher.hpp"

namespace dm = leo::adaptive::location::doppler_match;

// Implement this adapter for your own catalogue storage. Copy one record per
// call; return false on premature end, or throw on a read failure.
bool read_next_tle(void* catalogue_cursor, leo_tle_record& record);

dm::Result retrieve(const std::vector<dm::Track>& curves,
                    int64_t epoch_utc_ns, double carrier_hz,
                    dm::Region region, size_t tle_count, void* cursor) {
    dm::Options options;
    options.epoch_utc_ns = epoch_utc_ns;
    options.carrier_hz = carrier_hz;
    options.region = region;
    // Defaults: +/-60 s, eight candidates per track, 30 s coarse / 5 s fine
    // orbit knots, full spline proposals and regional visibility screening.
    return dm::match(curves, options, {tle_count, read_next_tle, cursor});
}
```

Link with `libleolocation.a`, `-pthread` and `-lm`; add `native/adaptive/location`
to the include path. The call is synchronous and creates no worker threads.
Input tracks remain borrowed and immutable until return; the returned values
are owned. Separate calls own separate workspaces. There is no persistent cache
or requirement to precompute states for Earth locations.

Each `Track` contains:

- `times`, `measured`, `training`: original observation times in seconds
  relative to `epoch_utc_ns`, frequency in Hz, and 0/1 held-out/training masks.
- `nodes`, `values`: sampled spline times and frequencies, in the same units.
  Fit this curve using only training observations. The matcher cannot verify
  how an upstream spline was fitted. Thirteen samples reproduce the prototype.

The caller supplies the nominal RF carrier, observation epoch, catalogue
eligibility and region prior. `Region` is latitude/longitude in degrees and a
radius in km; the current receiver model fixes altitude at zero. Catalogue IDs
must be distinct; the source is read once in order and is not rewound. Only
retained shortlists keep TLE records for later refinement.

`result.tracks[i]` contains up to `keep_per_track` candidates, ordered by
training RMS and then catalogue ID. Each candidate gives satellite ID,
receiver latitude/longitude, local east/north displacement, clock offset,
fitted constant frequency offset, and training/held-out RMS. For observation
time `t`, the candidate's UTC is:

```text
epoch_utc_ns + round((t + candidate.time_offset_s) * 1e9)
```

An empty candidate list is a valid result. Invalid or unpropagatable TLE IDs
are reported in `statistics.invalid_catalogue_ids`. Invalid inputs throw
`std::invalid_argument`; source failures and failed refinement propagation
throw `std::runtime_error`; allocation failures can throw `std::bad_alloc`.
Callback exceptions propagate. Failures return no partial result and do not
retain state for the next call.

## Bounds, memory and scientific scope

The implementation streams one satellite through coarse and fine orbit
contexts, each owning two state banks. It uses a regional Hermite horizon
envelope to reject distant satellites, tests nine position seeds and clock
seeds, retains a bounded shortlist, and continuously refines east, north and
time. A constant frequency offset is profiled out; frequency drift is not.
Held-out frequencies affect only the reported validation error.

Current bounds are 1–1,000 tracks, 6–10,000 observations per track, 3–101 odd
spline nodes, at least four training observations and one held-out observation,
1–20,000 TLEs, 1–32 candidates per track, radius `(0, 500]` km, clock bound
`(0, 60]` s, and at most 1,200 s of total observation history. Coarse/fine steps
are positive and at most 30/10 s respectively, with coarse >= fine. Grid
allocation is capped at 8,192 knots per context; clock seed spacing must yield
at most 257 seed times. These are allocation/work limits, not a latency promise
for every combination of inputs.

Orbit-state storage is `2 * (coarse_knots + fine_knots) * sizeof(leo_orbit_state)`;
it does not grow with catalogue size. Shortlists grow with track count times
the requested candidate count. Statistics also keep retained/invalid IDs, and
the result owns candidate tuples. The two reported capacity counters describe
orbit states and internal shortlist storage, not whole-process RAM or all
temporary allocations.

For [scan-fw-911c4e5db9243281](../../../../reports/2026_10_02_streaming_doppler_911c4e5d/README.md),
the original prototype measured **27.59 s and 2.105 MiB peak RSS on Cortex-A9**
for 63 tracks and 11,152 TLEs. Its orbit-state capacity was 10,944 bytes and
shortlist capacity 117,936 bytes. Those are historical prototype measurements;
packaging parity does not constitute a new device or concurrent-capture timing
qualification.

Position and time are fitted independently for each fragment. Candidates are
ambiguous and are not a joint location/clock fix or satellite identification.
The seed grid and shortlist make retrieval heuristic; the regional gate's
interpolation guard is empirical, not an SGP4 error proof. `audit_gate` compares
rejected coarse envelopes to fine envelopes; `disable_gate` enables a reference
run. Neither establishes exhaustive continuous-search completeness.

## Build and recorded replay

From the repository root, choose an absolute build directory:

```bash
bash native/adaptive/location/build.sh host /absolute/build
/absolute/build/leo-doppler-match OBSERVATIONS.txt CATALOGUE.tle
python3 tests/native_adaptive/location/check_doppler_match_cli.py \
  /absolute/build/leo-doppler-match \
  reports/2026_10_02_streaming_doppler_911c4e5d
```

The explicit report argument checks exact host parity against the frozen 63-track,
504-candidate result, excluding only timing fields. It reads local files and
does not contact a service or radio. This frozen fixture is never regenerated
by a build or test.

`build.sh sanitize` runs the same owned numerical, API and CLI tests with
ASan/UBSan. `build.sh arm` cross-compiles the library, CLI and tests; executing
those outputs on hardware is a separate explicit step. Synthetic tests need no
radio, QNAP, PostgreSQL, or recorded corpus.

The CLI retains the prototype's private `SDP1` observation input, counted TLE
pairs, JSON fields and experiment flags (`--audit-gate`, `--no-gate`,
`--endpoint-proposals`, `--full-proposals`). Endpoint-only proposals are an
experimental comparison and lost winners in the recorded scan; the default
uses every spline sample. File adapters remain outside the library.

`tools/prototype_streaming_doppler.py` prepares curves from explicitly supplied
published measurement documents. `tools/report_streaming_doppler.py` verifies
candidate results and exports tuples. These are development adapters, not ARM
dependencies. The old `research/streaming_match*` sources and build script are
frozen measurement references; active matcher development belongs here.
