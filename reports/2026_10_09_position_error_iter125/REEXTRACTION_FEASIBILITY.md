# Existing-IQ re-extraction: source feasibility, not an executed experiment

Existing public storage ports can supply the recorded samples without new RF.
[Scanner refinement source](../../src/leo/storage/scanner_refinement_source.py)
already opens fixed/adaptive stores read-only, exposes a callable probe-reader
boundary, and obtains IQ using `read_valid_ci16` or adaptive
`reader.read_visit_ci16`. These are appropriate component boundaries; a new
research adapter must not construct object-storage paths or private ORM access.
Current adaptive access reads a visit, so resident-IQ cost needs a bounded
visit-at-a-time implementation rather than assuming a narrow file-range API.

The existing comparison adapter's probe policy is **not** the requested
re-extraction policy: it chooses two visits per target and creates21ms probes
for injected shift/delay tests. Its [immutable comparison contract](../../src/leo/contracts/scanner_refinement.py)
also lists only2.5/5MS/s. Do not repurpose it to imply complete coverage of10MS/s
adaptive recordings or to replace the original positioning measurements.

Use the manifest-bound [tracking input port](../../src/leo/storage/scanner_tracking_source.py)
for original visit/probe/RX/channel, sample rate, device/payload counters and
candidate rank/epoch/fractional offset. Preserve the actual previously selected
candidate IDs and original margin admission; do not reacquire, select by new
score or discard cases where interpolation worsens. The reduced
`TrackingCandidate` contract omits **acquired CFO**, required to recreate the
same derotation and residual grid origin. Full persisted adaptive fractional
candidate products contain that field, so a narrow read-only provenance-checked
projection is needed; reconstructing it from the rounded published tracking
CFO would be wrong. Missing fields must produce explicit unavailable rows.

Before any candidate CFO is trusted, reproduce the original native/Python
conditioned exact/control score and CFO at the original anchor/offset and
acquired CFO, with exact sample-rate/template/edge/build provenance. Input
counter/guard/retained-window bounds must match the original20ms probe.
Historical kernels, high-rate symbol geometry or conditioning differences may
prevent parity; preserve those failures instead of substituting current
acquisition. The current125 prototype assumes64 uniformly spaced symbols at
4.4microseconds; capability at each real sample rate requires source-level
geometry verification and component tests before execution.

A bounded initial adapter could read one visit at a time for a frozen
metadata-only recording/probe inventory, extract both receivers' original
selected windows, perform baseline parity and output original/refined CFO with
unchanged admission. That is a measurement product only. A later localization
comparison would hold every observation ID, candidate bank, prior and start
fixed, substitute only CFO, include c=0/fitted-c and retain failures/coverage.
No real-IQ read, measurement replay, subset selection or position fit has been
authorized or run by this feasibility audit.
