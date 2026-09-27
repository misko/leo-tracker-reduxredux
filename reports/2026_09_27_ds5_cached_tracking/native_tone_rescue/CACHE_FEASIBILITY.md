# Audit and rescued-track reuse feasibility

`audit_receipts.py` independently recomputes paired timing/frequency association,
receiver counts and CPU ratios directly from saved JSON. It does not import the
evaluation runner or open IQ. The resulting `receipt_audit.json` confirms all 11
recoveries, 78/79 reference identities, unchanged primary-positive decisions,
2us/8kHz association, valid native evidence, integer source-coordinate mapping,
control truth gates and both source inventories. It is an independent code path
reviewed by the same root agent, not external scientific validation.

The chronological metadata identifies seven later rescue-selected visits with
a prior rescue on the same session/channel/edge/rate/receiver; six are within
two seconds, all at 5 MS/s. This is an optimistic eligibility inventory: it does
not apply intervening negative invalidation or establish tuning/calibration
continuity, and no predicted point has been scored.

A zero-drift transport of the previous rescued pair does not reproduce any of
the six current selected pairs within the fixed 2us timing tolerance:

| Current visit | Maximum phase error | Physical CFO change |
|---|---:|---:|
| 1089 | 7.60 us | 3092.72 Hz |
| 1091 | 2.07 us | 1293.29 Hz |
| 1093 | 9.20 us | 4102.99 Hz |
| 1094 | 248.20 us | 183356.52 Hz |
| 1100 | 8.33 us | 224856.94 Hz |
| 1107 | 10.27 us | 230348.07 Hz |

These are post-hoc comparisons against the current chosen pair, not cache-hit
predictions or proof no alternate valid identity exists. Phase prediction uses
integer counter subtraction before 750Hz modulo, then restores the fractional
sample. Absolute device counters are never cast to floating point. CFO change
compares the previous and current pair's second physical-frequency measurement.

Consequently, simply saving a rescued epoch/CFO and calling the point scorer
again is not a demonstrated latency fix. Several visits require drift handling,
and three show large frequency-identity changes. Do not widen the identity gate
or treat timing supplied to a scorer as a fresh fitted measurement.

The next cache experiment should use a bounded local timing search on fresh
tone-conditioned data, preserve physical identity gates, clear failed tracks,
and fall back to the existing one-probe acquisition. Initial rescue hypotheses
must not train slopes as if they were independently fitted epochs. Establish
drift only from independent fits with bounded rates and periodic broad discovery.
Fix that policy and its negative/change controls before running another replay.

The already measured 21–24x candidate can be validated separately without this
cache extension. Cache improvements must earn their own paired timing and
quality evidence; six optimistic opportunities do not imply six saved calls or
single-core real-time performance.
