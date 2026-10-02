# Native 1.25 MS/s adaptive capture proposal

The proposed policy chooses 1.25 MS/s for one of four uniformly selected hash
outcomes and 2.5 MS/s for the other three. It preserves reproducible choices per
radio and scheduling slot, independent edge selection, manual 40 dB gain,
five-minute production captures, and the three-minute post-capture gap.
This is a probability, not a promise of exactly one low-rate scan in every four.

## Evaluate reuse of the installed firmware

Radio .20 advertises runtime protocol v2 with source rates from 520,833 through
61,440,000 S/s and RX mask 3. Its protocol v3 instead advertises a fixed rate
mask that excludes 1.25 MS/s. The first candidate was v2 for the new rate and v3
for 2.5 MS/s. Hardware qualification below rejects that candidate on the current
deployment. Do not expand the host's declared device capabilities or relabel
2.5 MS/s IQ.

The current policy uses 120 ms for both active and quiet visits. Protocol v2's
fixed 120 ms dwell therefore preserves the requested dwell duration while
retaining adaptive target selection and feedback. It does not supply v3's
per-visit gain telemetry; record that absence explicitly. Manual gain readback
remains available. Keep the existing pilot-centered tuning frequencies while
narrowing source rate and analog bandwidth together. Scientific detection at
the narrower bandwidth requires its own validation.

## Preserve recording contracts

The production importer currently rejects 1.25 MS/s. Existing persisted plan,
receipt, timing, and history models enumerate qualified rates. A production
rollout must introduce a new version for native runtime-rate dual-RX geometry,
and propagate it through the importer, storage readers, API, and UI. Existing
versions must remain unchanged. Preserve the actual source rate, protocol,
sample counters, receiver layout, fixed dwell, and missing gain telemetry.

Gate the 25/75 scheduler rollout on a sealed low-rate archive passing import,
readback, and API listing tests. Analysis should report unsupported input until
its rate-dependent processing is validated; it must not silently treat these
samples as 2.5 MS/s. This qualification does not enable the production mixture.

## Bounded qualification

`tools/qualify_adaptive_runtime_rate.py` defaults to a dry run. With `--capture`
it requests one ten-second, dual-RX native 1.25 MS/s capture through the existing
prepare/capture/restore lifecycle. Run it under `/run/leo-adaptive-pipeline.lock`
and use a separate output root, outside the production importer spool. Each
complete visit must contain 150,000 samples per receiver and 1,200,000 ci16 bytes.
Incomplete evidence is retained for diagnosis rather than published.

The component tests cover all four probability branches, deterministic
selection, protocol wire roundtrip, RF-free default behavior, and rejection of
incorrect rate, sample count, or receiver byte geometry. Across 12,000 slots,
the test seed selects 2,971 at 1.25 MS/s and 9,029 at 2.5 MS/s.

## October 2 hardware results

Three bounded ten-second capture requests ran under the acquisition lock after
the scheduled scan completed. The automatic timer was not changed.

| Source rate | Protocol | Result |
| --- | --- | --- |
| 1.25 MS/s | v2 | Setup accepted; timed out waiting for the first READSCAN record after 10 seconds; no IQ archived |
| 2.5 MS/s | v2 | Setup accepted; timed out waiting for the first READSCAN record with a 30-second socket timeout; no IQ archived |
| 2.5 MS/s | v3 | Completed: 74 planned/delivered visits, zero skipped/invalid/cancelled visits, zero terminal error |

The successful control archived 177,600,000 uncompressed IQ bytes, exactly
74 visits × 300,000 samples × 8 bytes for dual-RX ci16. Its session is
`scan-fw-12014fc53b0d847f`. Evidence is retained outside production at
`/srv/bulk/leo/qualification-runtime-rate-20261002`.

All 27 host component tests pass (12 qualification cases and 15 existing cadence
cases). These do not override the negative hardware result. The first failure
used the default socket timeout; the later control used the diagnostic tool's
30-second timeout and saved a failure record beside the incomplete archive.
The campaign lifecycle attempted restoration on both failures and reported no
restoration exception. The subsequent successful v3 control confirms that the
radio remained usable. No firmware was flashed.

This isolates a failure in the deployed runtime-protocol capture path, rather
than proving a 1.25 MS/s hardware limitation. The exact device-side cause remains
unresolved. Device SSH diagnostics were unavailable because the presented host
key differed from the saved key; verification was not bypassed.

## Recommended production solution

Extend the working firmware scan path with an explicitly advertised 1.25 MS/s
capability (or a new wire version if semantics require it), with matching host
negotiation. Preserve existing capability meanings and test setup, counter
geometry, dual-RX delivery, fixed 120 ms visits, and restore behavior. Do not
fall back automatically to the currently failing v2 capture path.

In parallel, implement the new persisted native-rate geometry and reader path
described above. Then repeat this bounded hardware test at 1.25 MS/s, import its
real archive, verify that the web API lists the true source rate, and only then
enable the tested 25/75 selector. Production remains at 2.5 MS/s until those
gates pass. This avoids both a misleading decimated-rate label and failed scans
in a quarter of scheduled slots.
