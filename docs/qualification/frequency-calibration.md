# WP11 receiver-path frequency calibration

WP11 uses a separate, predeclared calibration campaign before acceptance. Each
fixed Pluto+ serial/RX1 physical path and topology epoch gets at least three
independent 60-second CH4-lower dwells. These captures carry the
`CALIBRATION` tag, forbid acceptance reuse, and use only the centered profile
revision `sha256:0f6aa753e16feaba1f76df21f0b620f32ab0b72456cb6034f2b1ea6a60c11e1a`.

The plan freezes the exact 1,709,521,250 Hz IF / 11,459,521,250 Hz RF tune,
2.5 MS/s and 2.5 MHz bandwidth, RX1 at 40 dB, 150,000,000 samples, template and
extractor digests, 600 ordered 25,000-sample windows at 250,000-sample strides,
decision threshold, separately named within-session and session-center robust
limits, evidence URI, and extractor Git revision, full source-tree digest and
executable digest. The two allowed radio serial/path/topology epochs and their
evidence digests are fixed station constants. A redigested relaxed plan is
invalid.

Inputs are not loose candidate lists. `CalibrationCaptureEnvelopeV1` contains a
full immutable `RecordingManifestV1`, its canonical digest and recording URI,
plus physical path/topology evidence. It verifies the committed live stream,
profile and applied settings, exact sample inventory, continuity and N/Fs
timing. Campaign timing-uncertainty intervals must not overlap.
`CalibrationExtractorReceiptV1` retains exactly 600 decisions and binds them to
that envelope, URI, manifest, session, stream, radio serial, physical path,
epoch, profile, template, extractor implementation/configuration and source
revision. All URIs, sessions, streams, manifests and observation IDs are unique.

Each session first receives its own median, MAD dispersion, multimodality and
full candidate-radius checks. Its radius propagates into final uncertainty;
the adversarial set `(-1.2 MHz, 0, +1.2 MHz)` is therefore insufficient rather
than collapsing to a plausible zero median. Each usable session then
contributes exactly one center, preventing candidate-rich sessions from
dominating the result. The final center is the median of session medians;
session-center MAD rejection, dispersion and multimodality, candidate/session
minima and all counts are deterministic. Persisted evidence reruns the pure derivation during
validation, so changing and redigesting a count, center, bound, margin, reason,
inlier set or status is rejected. Sufficient output validation reconstructs an
exact, separately typed draft estimate including identity, center,
uncertainty, method, proposed validity, evidence URI/digest and proposed output
IDs. The foundation always keeps its public `calibration` and `calibration_set`
fields null.

The sampled-band gate uses `min(sample_rate, bandwidth) / 2`, the 937,500 Hz
pilot occupied half-span, empirical center and uncertainty, and the full
300,000 Hz future satellite-Doppler guard. No additional filter-edge guard has
been scientifically established, so that explicit frozen term is zero; adding
one can only tighten the gate and must not reduce Doppler. The residual digital
search independently covers uncertainty plus the same guard. At the historical
D-chain residual of +4,201.5 Hz, uncertainty must be strictly less than
8,298.5 Hz: zero physical margin is insufficient, as is any negative margin.
Insufficient evidence emits no calibration and has no zero or historical
fallback.

The result is an empirical pilot acquisition/search center for one hardware
epoch, not intrinsic LNB error: blind pilot CFO includes satellite Doppler.
Validity begins strictly after the latest possible final sample from the last
calibration dwell. Timing accepts the exact N/Fs duration only when it lies in
the feasible interval `[last.earliest-first.latest,
last.latest-first.earliest]`, with the frozen integer-Hz quantization policy.

This module is a content-integrity and mathematical foundation, not a producer
authentication boundary. Every result and draft is explicitly
`unverified_foundation` and `acceptance_eligible=false`. The draft type is not a
`ReceiverFrequencyCalibrationV1`, cannot be placed in a resolvable calibration
set, and cannot be consumed by science interfaces expecting the public
calibration contract. A later operational stage must obtain the predeclaration,
manifest and extractor receipt through typed trusted store and extractor ports
before constructing a public calibration for acceptance use. A digest alone
does not prove who produced an object.

Hardware execution remains pending until the active soak is
complete; then capture the separate calibration sessions for each radio/RX1,
seal extractor receipts, review the replayable evidence, and only afterward
begin acceptance captures.
