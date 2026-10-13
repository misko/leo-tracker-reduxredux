# DS21-039 UTC timing provenance

The recorded input supplies a host-clock bracket for the first **valid** device sample, plus nominal-rate sample counters. It does not independently attest absolute UTC synchronization, PPS/GNSS timing, or oscillator-rate accuracy. This source/metadata audit found no concrete conversion bug and does not justify a timing correction.

The source-bound arithmetic and inspected source/test hashes are in [UTC_TIMING_PROVENANCE.json](UTC_TIMING_PROVENANCE.json). The input digest is `2631e731b3ef0b2ba13ee0ff2e6a689ec1a31c6fbb0f19047121eb214a03ac94`; session is `fast-4b6fff793fba610ed2674dcc6d2908ba`. No predictor, optimizer, raw IQ, reference join, held scoring, or locked input was used. Current source hashes describe the mechanism inspected; they are not an independent record of the exact acquisition source version deployed on hardware.

## What the recorded clocks establish

`PpuContinuousWindowSource` samples host realtime/monotonic clocks immediately before START and after the first IQ delivery, and binds that bracket to `record.valid_start`. It explicitly avoids equating delivery time with sample time. Here the first valid counter is **1216419170547**. Reconstructing the existing timing-authority formula gives:

| Recorded timing evidence | Value |
|---|---:|
| First valid sample earliest host UTC | 1791800721702706528 ns |
| Midpoint estimate | 1791800721827841169 ns |
| Latest host UTC | 1791800721952975811 ns |
| Bracket width | **250.269283 ms** |
| Realtime-minus-monotonic spread, authority begin/end triplet | 6.598 µs |
| Spread across all 6,762 delivery clocks plus pre-START clock | **9.341 µs** |
| Existing qualification limit | 2 s |

The bracket half-width is about 125.135 ms. It is a host bracketing interval, not a calibrated statistical standard deviation. The small offset spread establishes host-clock continuity during this recording; a common error relative to UTC would remain invisible. Neither the input timing fields nor the inspected recording/export configuration records contemporaneous absolute-sync status or sample-clock ppm uncertainty.

For the 3,568 exported processed visits, delivery occurs 90.159–132.594 ms after the valid-start epoch calculated from this midpoint and nominal 2.5 MS/s. These descriptive lags are compatible with transport/buffering delay. They do not identify a sample-clock error or justify shifting epochs. No horizontal position-error bound follows from the bracket.

## Counter, guard and support-center chain

The acquisition adapter requires a complete 50,000-sample window and at least 50,000 samples of post-recall guard for the configured 20 ms transition policy. Export carries `valid_start` as the timing counter. Retune, guard and skipped-visit gaps remain in counter differences; payload indexing (`visit * 50000`) is separate and is not a timing source.

`project_scanner_candidates` subtracts integer device counters before adding fractional GLRT support positions, then rounds relative nanoseconds and adds the integer UTC origin. The epoch is the mean center of the actual GLRT symbol support, not a nominal window start or an assumed start-plus-10 ms. Native alternatives retain their own distinct support centers. Preparation subtracts integer UTC epochs before dividing by `1e9`. Orbit-bank propagation likewise adds rounded relative nanoseconds to the integer origin and passes separate Julian-day/day-fraction values to SGP4. No whole-epoch float conversion, ns/seconds interchange, retune double addition, or guard-time compression was found along this chain.

Projection agreement therefore verifies consistent use of the recorded timing authority. It does not independently verify the physical accuracy of that authority. A fitted common timing shift may absorb an unknown clock offset along with other model effects; individual shifts approaching 17 seconds also include orbit/association freedom and must not be called measured hardware timing errors.

## Existing regression coverage and next evidence gap

Existing component tests already cover first-valid anchoring, caller-hook ordering, configured post-recall guards, actual gaps with device counters above `2**53` (fixture origin `2**54`), exclusion of whole windows without compressing counters/origin/terminal, export-to-projector composition, and unequal native support centers with UTC origin `1.9e18`. These directly cover the conversion risks inspected here. They were source-reviewed for this audit; no new tests or code changes were warranted and none were run.

The remaining physical evidence gap is an independent, contemporaneous host absolute-sync/clock-rate attestation. Its absence does not establish a clock fault. If future evidence identifies a conversion discrepancy, a narrow synthetic acquisition-receipt → export-loader → projector regression should reproduce that discrepancy before any model correction. Until then, keep the recorded epochs and existing timing priors unchanged.
