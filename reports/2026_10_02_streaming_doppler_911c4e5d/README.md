# Small-memory Doppler candidate retrieval on PLUTO+

The prototype processed the 63 published tracks from `scan-fw-911c4e5db9243281`
on the physical Cortex-A9 PLUTO+ in **27.589 seconds**, using **2,156 KiB peak
process RSS**. Its orbit workspace is **10,944 bytes**, independent of catalogue
size; it streams one satellite at a time. The retained hypothesis capacity is
117,936 bytes. These are measured matcher results, not an IQ-processing or
concurrent-radio throughput qualification.

Inputs are 3,228 measured frequency observations, the scan-bound archived
catalogue of 11,152 Starlink records, the published Sacramento prior (250 km
radius around 38.5816, -121.4944), and a clock-offset search of **[-60, +60] s**.
Receiver altitude is fixed at zero. The nominal 11.2 GHz convention matches the
existing published replay. The actual capture clock bracket is narrower; the
expanded search is deliberate for this experiment.

The output is a shortlist of `(receiver position, clock offset, satellite)`
hypotheses **for each fragment**. It does not yet impose one common receiver
position and clock across fragments. It does not establish a position fix or
satellite identity.

## Results and scientific checks

| Measurement | Result |
|---|---:|
| ARM whole-process wall time | 27.589 s |
| ARM whole-process CPU time | 27.583 s |
| ARM peak RSS | 2,156 KiB / 2.105 MiB |
| Orbit state buffers | 10.688 KiB |
| Host matcher time, separate run | 0.693 s |
| Catalogue records screened | 11,152 |
| Retained regional candidates over the complete window | 1,129 |
| Tracks / observations | 63 / 3,228 |
| Refined hypotheses, eight per track | 504 |
| Median held-out RMS, directly propagated finalists | 56.22 Hz |
| Best candidates with held-out RMS below 200 Hz | 53 / 63 |
| Tracks with runner-up training RMS within 1 Hz | 39 / 63 |
| Best candidates at clock / region boundary | 3 / 12 |

The many close runners and widely distributed candidate positions are substantive
ambiguity, not confirmed associations. A low frequency residual alone is weak
evidence when latitude, longitude, time, and frequency offset can vary for each
short fragment. The 200 Hz threshold is a diagnostic, not a calibrated identity
acceptance test. Published track memberships can share underlying observations;
tracks are not claimed to be independent evidence.

![Candidate positions and held-out errors](candidate-summary.png)

- Regional filtering produced exactly the same ordered hypotheses and scores as
  the host run with regional filtering disabled, using the same proposal grid
  and refinement. An additional five-second orbit-envelope audit found zero
  omissions from the thirty-second gate. This validates this recorded case,
  not a universal propagation/interpolation error bound.
- ARM and host produced the same complete ordered satellite-ID lists for all
  63 tracks. Maximum paired training RMS difference was about 0.000046 Hz.
- All 504 finalists were independently evaluated using the Python SGP4 binding
  and the repository frame-conversion functions, at their actual observation
  times. Maximum five-second interpolation Doppler difference was 0.641 Hz;
  maximum direct-versus-ARM held-out RMS difference was 0.157 Hz.
- A three-point proposal shortcut agreed with the full-spline best satellite
  for only 53 of 63 tracks. It was rejected as the default. The measured ARM
  implementation evaluates all 13 spline nodes during proposals.
- Native numerical tests passed on host, under address/undefined sanitizers,
  and on ARM. The complete recorded matcher also passed sanitizers. Six Python
  tests cover spline reconstruction, held-out isolation, invalid observations,
  capture binding, and exclusion of published positions/identities from inputs.

## Implementation

1. The export fits a small C2 cubic regression spline to **training observations
   only**. Depending on support, it has zero to three interior knots. Thirteen
   samples of that spline are passed to native matching, alongside original
   training and validation measurements. Spline fitting is host-side preparation
   in this prototype; native matching consumes the prepared curve.
2. Stream the TLE file. Build a coarse 30-second Hermite orbit for one satellite.
   Bound its regional horizon using all four Bezier controls per interval, an
   enlarged regional normal cap, the ellipsoid support, and a 2 km interpolation
   allowance. The allowance is empirical, not a formal SGP4 bound.
3. For survivors, build a five-second orbit for that satellite. The full scan's
   fragment intervals plus timing uncertainty and interpolation padding require
   [-90, 390] seconds relative to capture start. Only this satellite's coarse
   and fine buffers are resident; no dense satellite-by-time bank is allocated.
4. Propose at the prior centre and eight boundary points, with clock offsets at
   20-second increments. Eliminate one frequency offset analytically. Keep the
   eight best distinct satellite proposals per track.
5. Refine east, north, and time with a small bounded damped least-squares solve
   against the spline. Fit the offset to original training data, rank on its
   RMS, and report the untouched validation RMS. No frequency-drift parameter
   is fitted. One seed per satellite is retained; this is a heuristic search
   and can miss other minima or satellites outside the eight-proposal shortlist.

The search disk uses a spherical exponential map for local east/north offsets;
each trial site's ECEF position uses WGS84. The matching model is geometric
Doppler plus a constant frequency offset. Receiver drift and transmitter
frequency behavior are not separately identified.

The ARM run uses `nice -n 10` and a 60-second process limit. It was run on an idle
device, without RF access or service changes. No performance claim is made for
simultaneous capture or unseen scans. Propagation took 4.75 seconds; proposal
scoring took 22.01 seconds. Refinement, which overlaps the reported propagation
accounting, took 0.99 seconds. Those component times must not simply be summed.

## Artifacts

- [All 504 position/time hypotheses as CSV](hypotheses.csv): includes fragment
  IDs, coordinates, clock offsets, absolute UTC nanoseconds at local zero and
  fragment start, and training/validation errors. Different rows can imply
  different clocks; these are alternative hypotheses.
- [Summary and validation](summary.json), [ARM result](arm.json),
  [ARM timing](arm.time.txt), [payload/source hashes and command](arm-protocol.json).
- [Frozen input metadata](input/input.json), [measured inputs](input/observations.txt),
  [catalogue](input/catalogue.tle). The exporter admits no published satellite
  winners or known-position coordinates. Published membership reconstruction
  itself is reused and remains outside this qualification.
- [Unfiltered reference](host-ungated-reference.json),
  [gate audit](host-full-audit.json), [rejected shortcut](host-endpoint-experiment.json).

## Reproduce

From the repository root, use a writable build directory. The source-owned SGP4
library is linked directly; the legacy repositories are not dependencies.

```bash
TMPDIR=/dev/shm bash tests/native_adaptive/location/research/build_streaming_match.sh \
  host /home/mouse9911/.cache/leo-streaming-prototype-host

/home/mouse9911/.cache/leo-streaming-prototype-host/streaming-match \
  reports/2026_10_02_streaming_doppler_911c4e5d/input/observations.txt \
  reports/2026_10_02_streaming_doppler_911c4e5d/input/catalogue.tle

.venv/bin/pytest -q tests/research/test_streaming_doppler_prototype.py
.venv/bin/python tools/report_streaming_doppler.py \
  reports/2026_10_02_streaming_doppler_911c4e5d
```

Use build mode `arm` for the existing Cortex-A9 cross-toolchain, or `sanitize`
for host numerical tests and address/undefined checking. Run `--audit-gate` to
check rejected coarse candidates against fine envelopes; `--no-gate` produces
the unfiltered proposal reference. `--endpoint-proposals` reproduces the
rejected faster shortcut.

Next useful work is to couple hypotheses through a shared receiver position
and clock, and test on additional recorded scans. Increasing the cache is not
required for that step.
