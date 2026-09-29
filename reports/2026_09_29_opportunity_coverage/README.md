# Actual receiver observing opportunities: three-record pilot

**The analyzed windows cover 16.7% of valid dwell time in each pilot recording.**
Both receivers have consistent probes in every visit, but a 120 ms dwell has only
one 20 ms analyzed probe. The other 100 ms is unknown to this extraction, not a
satellite non-detection. This is an opportunity audit, not a position improvement.

The predeclared pilot selects the first chronological scan from each immutable
dataset manifest, without using model scores. It covers three of 258 recordings;
the coverage fraction must not be generalized to all recordings without a full audit.

| Dataset / scan suffix | Visits / paired windows | RX0 zero passing candidates | RX1 zero passing candidates | Both empty | Both with candidates | Analyzed / valid dwell |
|---|---:|---:|---:|---:|---:|---:|
| DS7 / 5f7bf896e4552887 | 2,213 | 585 | 1,205 | 535 | 958 | 16.7% |
| DS8 / aadcd44b66085469 | 2,219 | 276 | 725 | 251 | 1,469 | 16.7% |
| DS9 / 98cb28475c2059b9 | 2,211 | 623 | 832 | 562 | 1,318 | 16.7% |

All visits in these three recordings are 120 ms; all probes are 20 ms. Both inputs
and UTC timing are qualified. There are no duplicate probe keys, missing receiver
views, uncovered visits, tuning/counter disagreements, or probes extending outside
the valid visit interval. Passing means the persisted fractional-margin gate passed;
it does not mean a satellite identity was verified. Counts retain empty views.

## Consequence for modeling

Use actual probe sample intervals, exact RF, receiver availability and qualification
to define the observing opportunities. Do not treat the interval between consecutive
track detections or the entire recorded dwell as continuously analyzed. The 16.7%
is extraction coverage of valid dwell samples, not recording duty cycle, antenna
visibility, RF signal occupancy, or a probability of detection.

Even an empty analyzed probe does not prove a nominated satellite was absent:
beam shape, illumination, signal band and detector sensitivity remain uncertain.
A useful likelihood needs an explicit detection probability and false-detection
component, with shared geometry and separately validated cross-RX identity.

Earlier [presence modeling](../2026_09_28_rx_presence_geometry/README.md) already
retained empty windows, and [causal refitting](../2026_09_28_rx_causal_refit/README.md)
failed to establish reliable predictive transfer. This pilot does not reveal a bug
in those studies or invalidate their negative results. It establishes the exact
coverage semantics needed before extending them across DS7/DS8/DS9.

## Evidence and validation

The exporter uses the public TrackingInput loader and read-only adaptive capture
inspection. Each source capture digest must equal its immutable dataset-manifest
digest. Analysis digests, visit sample boundaries, exact RF and per-probe counts
are retained in DS7.json, DS8.json and DS9.json. The installed loader source is
preserved in scanner_tracking_source.py.txt. It requests a 120 ms probe stride;
the exported TrackingInput reports the actual 20 ms probe duration.

The independent auditor computes interval unions in integer samples for each
visit/RX, avoiding double-counting or UTC rounding. Three post-export auditor tests
pass: overlapping intervals, unobserved gaps/empty coverage and invalid intervals.
They validate accounting, not the RF detector. All scripts pass Ruff.

Three bounded metadata children exit zero: 11.10 s summed wall time, maximum
3.80 s, peak RSS 226,096 KiB. No raw IQ, RF collection, propagation, provider query,
fit, golden-fixture change or production change. An exploratory contract inspection
before freezing tried a nonexistent manifest receiver_ids field and raised
AttributeError after printing the first visit; the frozen export uses receiver IDs
from public probe records and all three executions succeeded without retry.

The next step is to extend this accounting to the remaining 255 recordings,
preserving active-dwell lengths and target/donor membership. Only then freeze a
new detection-likelihood comparison that adds evidence beyond the already tested
presence/causal models. Reliable sub-km accuracy remains unproven.

[Protocol](PROTOCOL.md), [selection](plan.json), [summary](summary.json),
[auditor](audit.py), [tests](tests.log), [input hashes](input-seal.json),
[complete evidence hashes](evidence-sha256.json).
