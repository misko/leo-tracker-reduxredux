# Timing and observation ingress component qualification

Host, ASan/UBSan and PLUTO+ CPU tests pass for measured counter/UTC authority and
scanner-v2 candidate projection. The DS9 handoff processes 24,681 saved candidate
records and reproduces 11,747 retained observations exactly against the native
projector: identifiers, support UTC, CFO, uncertainty and support moments.
The device replay takes 26.39 seconds including text parsing and both projection
paths. This is test throughput, not live detector or whole-application timing.

The [reviewed receipt](receipt-review-v2.json) binds sources, fixtures
and ARM bytes after independent review. The repeated DS9 replay passes in
25.59 seconds with 1,784 KiB maximum RSS. Review added fail-closed handling of
over-wide brackets, rejection of publication with pending observations, and
acceptance of attested v0.59 ALC CRC mutation while still checking profile ID
and frequency. Host, sanitizer and ARM component tests pass after these fixes.

The [authority receipt](receipt-authority-v3.json) adds an explicit
historical-metadata mode for recordings that never stored profile CRCs. It
requires zero CRCs and does not weaken the default live attestation rule.
Host, sanitizer and ARM tests pass; the unchanged 24,681-row DS9 projection
comparison passes again in 25.42 seconds on ARM. Those binaries are in
`/mnt/glrtbench/native-adaptive/tests/recorded-authority-v3`.

The [moment-arithmetic receipt](receipt-moments-v4.json) repeats host,
sanitizer and physical ARM tests after making support moments deterministic.
All 24,681 records pass the native projection comparison (27.51 seconds on ARM).
The full-catalogue application replay also has byte-identical support values,
digests and partitions across host and ARM; see the
[portability evidence](../runtime/fractional-support-determinism.json).

The [watermark receipt](receipt-watermark-v5.json) adds the reviewed
pending-inbox guard: quiet progress cannot expire already accepted evidence
before it is consumed. Host, sanitizer and physical ARM regression tests pass.
The current [frontier receipt](receipt-frontier-v6.json) also tests the
analysis-owner watermark query needed to avoid regressing quiet progress.

`receipt.json` preserves the earlier result. Initial ARM tests ran from
`/mnt/glrtbench/native-adaptive/tests/timing-ingest-v1` on `192.168.1.15`.
Reviewed tests are in `timing-ingest-review-v2` alongside that directory.
The deployed production scanner release is unchanged. No RF was acquired.

Covered failure cases include counter epochs beyond 2^53, counter reset, UTC
step, asymmetric clock reads, failed counter reads, expired anchors, generation
replacement, mismatched profile attestation, invalid probes and incomplete
fractional candidates. Detector completion/queue time does not change UTC.

Historical DS9 brackets are reconstructed from persisted authority for this
replay, with zero additional drift/resolution to preserve recorded uncertainty.
This does not establish a new live clock calibration, server detector recovery,
or full real-time application acceptance.
