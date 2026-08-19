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
- durably publish the promotion receipt before the public calibration is
  returned.

Only after those checks does the promoter run the replayable mathematical
foundation and convert its distinct draft into a public calibration. The public
contract uses method `trusted_wp11_empirical_pilot_acquisition_center_v1` and
evidence kind `trusted_frequency_calibration_promotion_v1`; its singleton set
resolves only for the exact radio serial, RX1 path and hardware epoch.

This commit intentionally does not compose the ports into CLI commands,
catalog queries, service wiring or database schema. Production composition
still needs adapters for trusted plan/product catalog records, release
attestation lookup and crash-safe promotion-receipt publication. Hardware
campaign execution also remains pending. No QNAP or live-radio access belongs
in this operation.
