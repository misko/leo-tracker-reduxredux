# Replacement scanner radio, 2026-09-12

The user selected serial `104000bac4950008230026001b440a003a`, verified at
`192.168.1.17` as `radio_pluto_003a`. Its former exclusion is superseded by this
instruction. Exact serial, LAN endpoint, metadata ABI, geometry and capability
checks remain mandatory.

The existing v0.49 firmware was retained. The idle radio was changed from
`mode=1r1t` to `mode=2r2t`, rebooted, and re-attested with both receiver paths.
Only `mode` changed; the original boot environment and versions are retained
under root-only `/var/tmp/leo-radio003a-2r2t-20260912`. The scanner still records
one receiver chosen from the durable scan identity, at native 10 MS/s.

The no-RF capability probe passed with provider revision
`26310f8a5079f9eb6ed25e3000e018da33550b9b`. An initial probe-report serialization
error left its temporary daemon running; the exact PID/start-time/binary identity
was inspected, stopped and cleaned through PPU ownership checks. The corrected
probe completed normal cleanup. A separate canary credential preflight failed
before staging: PPU requires a single exact-host credential, so the scanner pin
now contains only `.17`; the previous `.20` pin is retained in the rollback backup.

The first RF check stopped at cancellation because PPU metadata had closed visits
whose final IQ had not yet reached the host. A regression test reproduces that
case. The adapter now drains closed-visit IQ before cancellation, with a ten-second
deadline; it preserves strict receipt equality and fails if draining cannot finish.
Bounded daemon diagnostics are attached before cleanup, including on capture failure.

The recheck published `scan-hop-ca372e1850cf056e` in the isolated store
`/srv/bulk/leo-radio003a-canary-20260912-03`: physical RX1, 10 MS/s, 200 valid
120 ms visits, 240,000,000 retained samples across a 251,436,366-sample device span.
Duty was **95.4515%**, with zero missing samples, overflows, event gaps or writer
enqueue failures. The writer queue high-water mark was two of 64 visits.
Cancellation, transport closure, Fast Lock deactivation and receiver restoration
were verified. This approximately 25.14-second device-span check does not qualify
300-second duty or the adaptive profile.

Initial acquisition release `caa67df2b6a04d284da15979b75b956071b26e30` was selected, with PPU
`43fd89b0920b0caf6a0402ad23785f54d5744859` and the source-bound provider above.
217 Leo component/deployment tests passed. PPU's five affected component suites
passed 230 tests, followed by three additional ownership/admission checks.
The immutable release passed artifact and publication validation and generated
the production web assets. Chromium loaded the live Scanner view, 20 history rows,
and its waterfall image with no failed requests or page errors.

The 22:40 production slot exhausted retries before RF because the root-run canary
created the new radio's shared lock as root. After confirming that lock was idle,
ownership was transferred to `leo` and the service restarted. The 23:00 slot then
failed twice during RF with `COUNTER_DISCONTINUITY`: each lost one 131,072-sample
block (13.1072 ms at 10 MS/s). The daemon transported 1,067 frames in 14.38 seconds
and 2,775 frames in 36.77 seconds, respectively: approximately 38.90 and 39.57 MB/s
against the required 40 MB/s. Those aggregate timings are consistent with a
gradually exhausted buffer queue; they do not establish a unique root cause.
Raw logs and parsed timing totals are retained alongside this report. The second
attempt also reported an inexact host-settings restoration; a later idle readback
showed 30.72 MS/s, 18 MHz bandwidth, 2.4 GHz LO and both original slow-attack modes.
That later observation does not retroactively attest the failed cleanup receipt.

Acquisition was stopped at 23:01:46 UTC, cancelling the third attempt before open.
Both device buffers were observed disabled, only stock iiOD
remained, and SSH serial readback matched the selected radio. API and analysis
services remained available during diagnosis. The restart-helper control-command
fix was committed as `604890e1`, tested with eight deployment tests, and subsequently
included in the new acquisition release below.

A bounded follow-up tested the existing `--rw-cpu-affinity 1` option, matching the
stock daemon's worker affinity while leaving the capture profile unchanged.
The candidate used the public lifecycle runner hook, verified the exact radio
and advertised affinity before RF, and retained both launch-script hashes.
It failed after 222 transported frames with the same one-block discontinuity;
normal ownership cleanup and full receiver restoration succeeded. This candidate
is rejected and was not installed or activated in production.

The next comparison used the existing 262,144-sample block setting, doubling
native one-RX payloads from 512 KiB to 1 MiB and halving per-refill request and
metadata overhead. It sustained about 65 seconds without a reported counter gap,
but cancellation failed at host-settings restoration. Code inspection found
that the hop adapter compared complete gain observations, contradicting the
radio's existing settable-state restoration predicate. AGC gains can change;
manual gains remain configuration and must match exactly.

PPU `7c3829887f3526710bbc1a002fb9d4cf4e554bf6` reuses that predicate and retains
both observed gain values in the lifecycle receipt. Tests prove that AGC gain
changes are accepted, manual gain changes and every configurable-field mismatch
are rejected, Fast Lock must be inactive, and the radio still closes on failure.
136 PPU tests passed. The Leo pin and receipt mapping passed 137 tests; the
restart-control helper's four execution tests also passed on the deployment branch.
No persisted schema or scientific threshold changed.

Sealed acquisition release `eefcb4f080907c51cddb505944ed4b1caf899751` passed source,
runtime and publication checks and generated the web assets. Its isolated recheck
published `scan-hop-f27772c0a32a2110`: RX0, 517 valid visits, 620,400,000 valid samples
over a 650,196,636-sample device span, **95.4172% duty**, zero missing samples,
overflows, event gaps or enqueue failures. Cancellation and restoration passed.
The writer queue high-water mark was four of 64.

The new release and 262,144-sample block setting were activated through the
restart helper, which reported capture authority running. The normal 23:20 slot
completed on its first attempt as `scan-hop-f98b2fa504260a57`: **95.4264% duty**,
2,386 valid 120 ms visits, 2,863,200,000 valid samples across 3,000,427,297 device
samples (300.0427297 seconds). The receipt binds the exact selected serial, RX0,
native 10 MS/s, 32 requested/read-back kernel buffers, zero missing samples,
overflows and event gaps, and successful restoration. Queue high-water was three
of 64, with no enqueue failures. The service exited successfully and resumed its
normal next-slot wait. One full success is evidence for this configuration, not
a claim that every earlier transport failure has been explained.

The following normal 23:40 slot also completed on its first attempt as
`scan-hop-86c1ad6a5201da99`: RX0, **95.4302% duty**, 2,386 valid visits,
zero missing samples, overflows or event gaps, and successful restoration.
Its manifest was inspected through the read-only storage port and the compact
receipt is retained in `scheduled-2340-capture-pass.json`. The service exited
successfully at 23:45:16 UTC and resumed its next-slot wait. The automatic
background worker completed native analysis of all 2,386 visits/probes at
23:53:33 UTC, without a manual analysis command. The product binds the inspected
capture manifest and native 10 MS/s rate. At 23:54 UTC, all three plots fetched
through their public API URLs passed byte-count, SHA-256 and PNG-dimension checks,
before the next 00:00 scan slot. The complete detail and artifact checks are
retained as `scheduled-2340-analysis-complete.json` and
`scheduled-2340-plot-check.json`. This verifies automatic publication for the
fixed baseline; it is not an adaptive-load qualification.

The capture is visible through API v4. Native-10M analysis completed successfully
at 23:35:17 UTC through the installed production CLI, respecting the shared worker
lease, with two workers and a 120 ms probe stride. All 2,386 visits/probes were
processed; the product binds the exact capture-manifest digest and native rate.
It reports 954 best candidates above the fractional margin gate. These are
detector observations, not calibrated satellite identities.

Chromium verification initially used an incorrect exact image label (omitting
the session suffix), and also exposed an unnecessary radio-classifier request:
this fixed profile deliberately has no on-radio GLRT result. The UI now omits
that panel for this profile while retaining the legacy classifier panel. The
change passed 38 UI tests and the TypeScript/production build. API/UI release
`7f82cf42571c6d5300088acc44251885e464fa9c` was separately sealed and activated;
acquisition remains on `eefcb4f0`, and the analysis service remains on its
compatible `98207d6` release.

The corrected real-browser check passed all three tabs with no page errors or
failed HTTP responses. Every fetched PNG's SHA-256 and byte count matches the
native analysis manifest; dimensions are nonzero and each URL binds this session.
The rendered view was inspected and its screenshot retained. Coverage, GLRT/CFO,
local/joint refinement and measured Doppler trajectories are visible. Catalogue
matching remains explicitly unavailable because candidate population propagation
was incomplete; no satellite identity is asserted. The earlier browser failure
report is retained separately from the successful verification.

The saved approximately 25-second RX1 capture was analyzed through the installed
native-10M analysis service in 34.89 seconds. All 200 visits were processed, and
coverage, GLRT response and CFO plots passed byte-count, digest and PNG-dimension
checks. No candidate exceeded the configured fractional GLRT gate. This result
does not determine whether an antenna is connected. These isolated analysis
products are separate from production scanner history.

The same frozen sixteen-case compact-filter ARM replay also ran on this radio
without RF: 119.97 ms mean and 123.45 ms maximum. It still misses the adaptive
90 ms mean / 100 ms p99 timing gate. The proposed host-feedback architecture is
documented separately and remains pending; probe coverage has not been reduced.

The active adaptive qualification RF ledger charges both partial RF checks in
full, including preparation and cleanup. With the rejected affinity comparison,
total charged qualification collection is 237.3314414732781 seconds;
1,562.6685585267219 seconds remain, including 1,500 seconds reserved for the
adaptive qualification sequence. Normal scheduled production attempts are
retained separately in the 23:00 failure log. No migration was changed.
Adaptive decision architecture and its deployment gates remain open.

Rollback for the latest acquisition-only switch is retained in
`/run/leo-radio003a-block262144`: the previous component environment and selector
still bind the same radio and the preceding sealed release. The original radio
switch configuration is retained in `/run/leo-radio003a-cutover/*.before` and
the previous exact-host credential in `/etc/leo/credentials/`; the earlier release
`98207d6fc6eaeaab1ab870998c1519afe0a6b892` remains installed. Restoring the old radio
would require revalidating its current reboot-generated SSH key.
The preceding API selector is retained in `/run/leo-radio003a-web-assets`.
