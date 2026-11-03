# DS10 timing metadata cannot justify a tight absolute timing prior

All 24 DS10 N24 recordings have reproducible, qualified host-bracketed device-counter timing metadata. However, 15 fitted recording offsets fall outside the host brackets, and no single constant host-clock bias reconciles all fixed fitted offsets. Do not impose a tight absolute timing prior from this metadata alone.

| Check | Result |
|---|---:|
| Timing present and qualified | 24/24 |
| First-sample bracket width, median | 363.962 ms |
| Bracket width range | 362.720–368.355 ms |
| Realtime-minus-monotonic spread, median | 0.707 microseconds |
| Largest sampled clock-offset spread | 4.352 microseconds |
| Fitted offsets outside host brackets | 15/24 |
| Largest distance outside bracket | 0.682057 s |
| Gap between incompatible common-bias intervals | 0.940520 s |
| Terminal device-counter duration / nominal rate | 300 s for all 24 |

The small realtime-minus-monotonic spread measures consistency among three host-clock samples. It is not absolute UTC accuracy. The roughly ±182 ms first-sample bracket comes from the begin-call interval and is much wider than the clock-spread number. Counter duration divided by nominal rate is not an independent sample-clock calibration.

For each fixed fitted offset tau, a hypothetical common clock bias must lie in `[tau − upper_bracket_offset, tau − lower_bracket_offset]`. Across DS10 N24, the intersection would require bias at least +0.258463 s and at most −0.682057 s, so it is empty. This rules out a common-bias explanation of these existing fitted values under the bracket model. It does not establish the true host bias, nor rule out a different joint location/time fit. Model timing can absorb wrong candidates, orbital error, processing mismatch and position error.

## Method and verification

The [protocol](PROTOCOL.md) predates metadata export. [export.py](export.py) reads metadata through `AdaptiveHopIqStore(..., read_only=True).inspect`, verifies manifest digests against the frozen observation exports, and records installed reader/contract source hashes. It constructs no recording storage paths and reads no IQ. Membership and timing offsets come from the existing DS10 N24 height-zero fit.

[audit.py](audit.py) reuses the independent [DS7–9 bracket reconstruction](../2026_09_29_timing_authority/README.md), checking persisted earliest/latest times, midpoint, qualification, clock spread, observation start and terminal first counter. Its two existing tests pass, including corrupt-field rejection and missing-authority handling. All 24 reconstructions pass. [metadata.json](metadata.json) and [results.json](results.json) retain complete public timing fields, per-scan comparisons and source hashes. The metadata export exits zero within its 120-second cap.

## Consequence for subkilometre work

The preceding [position sensitivity test](../2026_09_30_ds10_position_sensitivity/README.md) shows why independently known timing would help: some one-kilometre displacements can be partially absorbed by 36–135 ms timing changes. The present metadata does not supply an independent millisecond-scale absolute constraint. Historical host UTC discipline remains unbounded in the inspected evidence, as documented in the [physical audit](../2026_09_30_physical_constraint_audit/README.md).

The next useful timing work must establish an independent sample-to-UTC relation or distinguish processing/association mismatch from capture timing. Selecting a tighter prior using roof-reference error would not solve that problem. No new position fit or sub-km accuracy gain is claimed.

No new RF, IQ processing, clock change, archive mutation, production edit or remote publication occurred.
