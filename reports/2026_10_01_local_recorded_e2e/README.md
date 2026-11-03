# Offline recorded-IQ application check

This check exercises the local recorded source, recorded-plan scanner, frozen
corrected detector profile, candidate projection, bounded `Session` queue,
publication, tracking, and conditional location search. It uses the existing
32-visit DS9 panel under `/var/tmp/leo-recorded-ds9-v2/panel32`; it performs no
RF capture, QNAP mutation, or network operation.

The first build exposed two composition defects and did not reach the detector:

- `build-recorded.sh` linked the live-radio entry point into the recorded
  executable, producing duplicate `main` and local-IIO link requirements.
- `recorded_main.cpp` discarded the bundle reader's bounded 1 ms saved-clock
  resolution allowance, so its already-validated timing bracket was rejected
  by `Timebase`.

The build now compiles `live.cpp` with `LEO_LIVE_CORE_ONLY` and obtains timing
configuration from `recorded_timing_config()`. The recorded-bundle component
test proves that an accepted bundle's timing bracket is also accepted by the
returned `Timebase` configuration. Host and ASAN/UBSAN component builds pass,
and the complete recorded application cross-links as a 32-bit ARM executable.

## Retained panel result

The final-source host run completed successfully in 38.10 seconds wall and
37.80 seconds user CPU with 189,732 KiB maximum RSS:

- 32/32 visits intact;
- 32/32 detector jobs accepted and completed;
- zero detector failures, detector queue drops, missing samples, source
  discontinuities, observation queue drops, or timing failures;
- detector queue high-water: 1;
- 512 emitted detector candidates, of which 88 projected and all 88 were
  consumed;
- support derivation succeeded for all 88 projected observations;
- one publication containing 88 observations;
- zero reconstructed tracks, therefore no location search or position.

The 32 detector-result events consumed 37.031904 seconds total, averaging
1,157.247 ms and peaking at 1,486.582 ms per 120 ms visit. Detector queue delay
peaked at 0.221 ms. Thus capture-to-analysis handoff and bounded backpressure
are lossless, but this corrected detector is about 9.6 times slower than the
dwell cadence on the host and the retained candidates do not support a position.
This is an explicit failed real-time/scientific gate, not a reason to relax it.

Position-output plumbing is covered separately by the injected live CLI test,
which sends eight deterministic time-ordered candidates through the same
analysis, orbit, bounded-search, serialization, and cleanup path and requires a
non-null position. That deterministic test is plumbing evidence only; it does
not claim live or retained-IQ detector sensitivity.

A stronger integration now runs the real local source and scanner rather than
stubbing the scanner call. A deterministic provider paces one complete
dual-receiver block every 20 ms. Sixteen visits pass through production block
assembly, energy feedback, adaptive policy, the bounded detector executor,
projection, tracking, orbit generation, one-point search, and publication. The
test requires zero queue drops or detector failures, ACTIVE feedback, an
observed 360 ms adaptive dwell, a reconstructed track, a completed search with
an incumbent, and a non-null position publication. The ASAN/UBSAN host build
passes, and the exact ARM executable passes locally under QEMU with the on-disk
firmware sysroot. Its ARM SHA-256 is
`6f96d878c12ae38684b00a6a4c7d4ef250230ceec0389a98a4565c1aa8ea3a68`.
The deterministic detector remains test injection, not a GLRT sensitivity
claim; all capture, pacing, backpressure, adaptive policy, and downstream
positioning stages are the production implementations.

The retained physical local-IIO boundary evidence remains the authorized
60-second PLUTO+ run in
`../2026_09_30_native_adaptive_deployment/live-qualification/qualification.json`:
350/350 intact visits and detector jobs, zero missing samples or queue drops,
passing timing audit, and successful radio restoration. It intentionally stops
at candidate events. The new paced integration closes the subsequent
candidate-to-position composition in-process without RF, while the retained-IQ
run above covers the real detector/projection boundary. These are separate
claims because the current radio is not expected to receive a usable GLRT and
no new RF collection was authorized.

The scanner component's four ASAN/UBSAN suites also pass from the current
source. They cover ACTIVE/QUIET adaptive dwell transitions, exact transition
timing, cooperative source deadlines, source-port handoff, bounded queue
high-water/drop accounting, and lossless draining of an unpaced recorded plan.
The host's `/tmp` filesystem is below this user's quota, so the suites were run
with their `tmpfile()` call redirected to the workspace build directory; the
initial failure was an observed `EDQUOT` write, not a product or sanitizer
failure.

Existing physical ARM evidence for the ordinary 2.5 MS/s detector reports a
56.94 ms mean per 120 ms dual-receiver dwell and lossless paced runs with an
explicit bounded queue. That supports the feasibility of the live scanner's
detector lane, but it is not interchangeable with this application's 7.5 MS/s
corrected-profile detector. The latter's measured 1,157.247 ms mean remains the
truthful cadence result for this retained panel.

## Reproduction inputs

- Bundle TSV SHA-256:
  `8f194b6de8cf449d76dbab1683fdf36221f0cc98fdc8c9b6bfcdeb32cc9ebe06`
- Exact template:
  `reports/2026_09_30_native_adaptive_deployment/ds9/location-templates/lower-exact.c128`
- Control template:
  `reports/2026_09_30_native_adaptive_deployment/ds9/location-templates/lower-control.c128`
- TLE catalogue:
  `reports/2026_09_30_arm_location_prototype/local/tles.txt`
- Search origin: `37.858988, -122.478103`; one 2 km grid cell within a
  1 km radius.
