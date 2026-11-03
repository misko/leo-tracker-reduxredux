# Native adaptive analysis

The implementation plan is in [`plan.md`](../../plan.md). These source-owned
C/C++ components are intended for local PLUTO+ execution and portable replay.
Python tools in `tools/native_adaptive_*` export or compare fixtures during
development; they are not device runtime dependencies.

| Directory | Boundary | Scheduling owner |
|---|---|---|
| `device/local` | Bufferless radio preparation, local libiio DMA and firmware scan ownership | Counter-session reservation; one acquisition owner; borrowed block lease |
| `runtime` | Counter-qualified windows, fractional support, observations | Caller; one bounded executor per reserved lane |
| `detector` | Ordinary GLRT and additive fractional epoch refinement | Single serialized detector lane, explicit busy errors |
| `tracking` | Weighted alias Hough track reconstruction | One snapshot builder |
| `location` | Local SGP4, catalogue scoring, resumable regional search | Caller partitions catalogue across independent contexts |
| `policy` | Original adaptive dwell/target policy with bounded continuous history | One feedback/visit owner |
| `bench` | Independently paced saved-IQ arrivals and overload measurement | Monotonic producer plus bounded detector executor |
| `pipeline` | Reconstructed tracks and recording authority -> graph identities, masks and location inputs | Explicit batch adapter; reference track bytes are discarded |
| `scanner` | Local source, energy feedback, policy and queued detector events | One acquisition owner and one detector worker |

Public persisted server contracts are unchanged. Internal APIs explicitly
describe owned and borrowed buffers. A capture gap, incomplete fractional fit,
busy detector or full queue must remain visible; callers must not manufacture
continuity or substitute zero-valued scientific results.

The PLUTO source uses `iio_create_local_context` and local firmware ioctls.
Network access is used for installation and diagnostic results, not its IQ
path. A Pi USB-SDR implementation can implement the source boundary, but that
adapter and platform qualification are not yet delivered.

## Build and test

Each directory has its own build script and component-owned tests under
`tests/native_adaptive`. The location, tracking and local-device scripts accept
`host`, `sanitize`, or `arm`. Runtime and policy scripts accept an output
directory and `ARM=1`/`SANITIZE=1`. Detector builds require explicit compiler,
archiver and FFTW paths; see its README and frozen build receipts.

```sh
.venv/bin/python -m pytest -q tests/native_adaptive/runtime tests/native_adaptive/bench
bash native/adaptive/runtime/build.sh /tmp/leo-runtime
```

External hardware and corpus requirements must be explicit. Component tests
using injected fake drivers do not open a radio. Saved-IQ replay does not
authorize a new RF capture. Production capture should remain disabled until
its scientific and concurrent-capture qualification gates pass.

## Qualification status

See [`deployment evidence`](../../reports/2026_09_30_native_adaptive_deployment/README.md).
Component deployment is not yet a qualified continuous IQ-to-location service.
In particular, ordinary native-control parity does not imply fractional-server
parity, and the full-catalogue scorer does not yet meet the provisional warm
location update target. Retain these distinctions when evaluating optimizations.
