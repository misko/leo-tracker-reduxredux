# Trusted WP11 calibration operation

The operational slice has two deliberately separate stages.

`BlindPilotCalibrationExtractor` reads exactly 600 windows of 25,000 CI16
samples from the centered RX1 recording, at 250,000-sample strides. It holds one
window at a time. A fixed two-tone FFT search estimates a common offset around
the ±820,312.5 Hz template tones and applies the frozen score threshold. The
result is a sealed `CalibrationExtractorReceiptV1` published as the scientific
evidence product `wp11-frequency-calibration-extractor` version 1.

`TrustedFrequencyCalibrationPromoter` is the only operation in this slice that
constructs `ReceiverFrequencyCalibrationV1`. Its injected trusted ports must:

- return a plan record with an actual immutable-store seal time, which must be
  no later than the plan declaration and therefore before every capture;
- resolve each canonical recording URI, expose the actual manifest and run the
  recording store's full compressed/uncompressed digest verification;
- open a verified `RecordingIqReader` so the promoter can rerun the frozen
  extractor and require byte-for-byte contract equality with the sealed product;
- return a validated release attestation whose Git revision, full source-tree
  digest and executable digest equal the predeclared extractor identity; and
- publish receipt, draft, public calibration and singleton set as one
  create-only promotion bundle.

Only after those checks does the promoter ask the concrete promotion store to
assign an authoritative timestamp, run the replayable mathematical foundation
and convert its distinct draft into a public calibration. The store writes each
document and a manifest with create-only/no-follow operations, file and
directory fsync, atomic directory rename and full readback validation. Exact
retries are idempotent; the same ID with different content is a conflict. The public
contract uses method `trusted_wp11_empirical_pilot_acquisition_center_v1` and
evidence kind `trusted_frequency_calibration_promotion_v1`; its singleton set
resolves only for the exact radio serial, RX1 path and hardware epoch.

The promotion-store root must be an absolute, pre-created local directory. Its
constructor rejects the QNAP namespace lexically before any filesystem call,
then opens every path component as a directory with no-follow semantics. It
never creates missing ancestors or follows a symlinked component.

The promoter returns only a durable publication reference. The authoritative
resolver accepts that reference only from the concrete store, rechecks every
stored digest and contract replay, and asks the deployed-release validator for
the current release again. The current release ID must be explicitly allowed
and its Git/tree/executable attestation must exactly equal the promotion
receipt. A no-op publisher, a hand-built result, a backdated timestamp, changed
release or modified file cannot produce a resolvable calibration.

This commit intentionally does not compose the ports into CLI commands,
catalog queries, service wiring or database schema. Production composition
still needs trusted plan/product catalog adapters, the native-release adapter's
deployment paths and an operator-selected local promotion-store root. Hardware
campaign execution also remains pending. No QNAP or live-radio access belongs
in this operation.
