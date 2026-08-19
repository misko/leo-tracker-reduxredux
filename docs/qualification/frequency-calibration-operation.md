# Trusted WP11 calibration operation

The operational slice has two deliberately separate stages.

The frozen extractor reads exactly 600 windows of 25,000 CI16 samples from the
centered RX1 recording, at 250,000-sample strides. It holds one window at a
time. A fixed two-tone FFT search estimates a common offset around the
±820,312.5 Hz template tones and applies the frozen score threshold. The result
is a sealed `CalibrationExtractorReceiptV1` published as the scientific
evidence product `wp11-frequency-calibration-extractor` version 1.

Operational trust comes only from `ReleaseLocalCalibrationExtractor`. It takes
an exact full-dwell RX1 snapshot through the reviewed anonymous-FD protocol and
runs the calibration mode of the sealed native evidence worker with the
validated release-local interpreter under isolated mode. The worker executes
the installed, package-tree-attested extractor and returns all 600 observations.
The execution contract binds the IQ, plan, capture, native-release, worker,
interpreter, installed package tree, fixed environment and raw worker-output
digests. The workspace extractor is useful for research comparison only and is
never an authority for promotion.

`TrustedFrequencyCalibrationPromoter` is the only operation in this slice that
constructs `ReceiverFrequencyCalibrationV1`. Its injected trusted ports must:

- return a plan record with an actual immutable-store seal time, which must be
  no later than the plan declaration and therefore before every capture;
- resolve each canonical recording URI, expose the actual manifest and run the
  recording store's full compressed/uncompressed digest verification;
- open a verified `RecordingIqReader` so the release-local worker can rerun the
  frozen extractor and require byte-for-byte contract equality with the sealed
  product;
- return a validated release attestation whose Git revision, full source-tree
  digest and executable digest equal the predeclared extractor identity; and
- publish receipt, draft, public calibration and singleton set as one
  create-only promotion bundle.

Only after those checks does the promoter ask the concrete promotion store to
assign an authoritative timestamp, run the replayable mathematical foundation
and convert its distinct draft into a public calibration. The store writes each
document and a manifest with create-only/no-follow operations, file and
directory fsync, atomic directory rename and full readback validation. The
store retains the validated root directory descriptor and performs every child
operation relative to it, so later pathname replacement cannot redirect a
write. Exact retries and simultaneous identical attempts replay the winner's
authoritative timestamp and are idempotent; the same ID with different content
is a conflict. The public
contract uses method `trusted_wp11_empirical_pilot_acquisition_center_v1` and
evidence kind `trusted_frequency_calibration_promotion_v1`; its singleton set
resolves only for the exact radio serial, RX1 path and hardware epoch.

The promotion-store root must be an absolute, pre-created local directory. Its
constructor rejects the QNAP namespace lexically before any filesystem call,
then opens every path component as a directory with no-follow semantics. It
never creates missing ancestors or follows a symlinked component.

The concrete store has no public arbitrary-builder entry point. It issues one
identity-bound private capability to its exact `TrustedFrequencyCalibrationPromoter`
owner and checks both owner and capability before invoking the verified-result
builder. Hand-built builders therefore cannot create a resolvable bundle.

The promoter returns only a durable publication reference. The authoritative
resolver accepts that reference only from the concrete store, rechecks every
stored digest and contract replay, and asks the deployed-release validator for
the current release again. The current release ID must be explicitly allowed
and its Git/tree/executable, worker, interpreter and installed-package
attestation must exactly equal every persisted execution and the promotion
receipt. A no-op publisher, a hand-built result, a backdated timestamp, changed
release, forged worker output or modified file cannot produce a resolvable
calibration.

This commit intentionally does not compose the ports into CLI commands,
catalog queries, service wiring or database schema. Production composition
still needs trusted plan/product catalog adapters, the native-release adapter's
deployment paths and an operator-selected local promotion-store root. Hardware
campaign execution also remains pending. No QNAP or live-radio access belongs
in this operation.

## CLI and processing composition

`leo process calibration` exposes four typed commands. Human and `--json`
rendering consume the same immutable result models and ordinary CLI exit-code
mapping.

- `predeclare` validates the current deployed native release, freezes its exact
  source/release identities and at least three preassigned capture session IDs,
  then create-only publishes the plan under the pre-created local qualification
  root.
- `queue` loads that exact plan and requests only
  `wp11-frequency-calibration-extractor` runs with `evidence_only` promotion
  policy. These runs cannot replace Standard current analysis.
- `promote` obtains exact recording/product inputs from the injected calibration
  catalog port, invokes the trusted promoter, authoritatively resolves the
  durable result, then publishes the catalog projection.
- `show` loads the catalog projection and resolves its durable publication
  again before display.

The extractor has a concrete dependency-free pipeline `StageSpec` and emits
only the existing `wp11-frequency-calibration-extractor` scientific product.
The production builder composes the ordinary recording/artifact stores with
the immutable plan/promotion stores, release-local executor, shared processing
service and authoritative PostgreSQL adapter. Each queued run ID derives from
the immutable plan digest and session ID, and the worker refuses a missing,
multiply-declared or differently bound plan. Promotion passes only the durable
publication reference to PostgreSQL; the adapter invokes the authoritative
resolver itself before registration, and `show` repeats that readback.

`--evidence-uri` is deliberately not an operator option. V1 predeclaration
derives its frozen evidence URI from `plan_id` and returns the immutable plan
reference separately. Qualification plan and promotion directories and the
local bulk root must be pre-created. Composition rejects QNAP lexically before
filesystem access and opens path components with no-follow semantics before
constructing the recording store.
