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

Acquisition release `caa67df2b6a04d284da15979b75b956071b26e30` is selected, with PPU
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
It remains stopped. Both device buffers were observed disabled, only stock iiOD
remained, and SSH serial readback matched the selected radio. API and analysis
services remain available; no complete 300-second product from this radio has
been published. The restart-helper control-command fix is committed as
`604890e1`, tested with eight deployment tests, and has not been deployed.

A bounded follow-up tested the existing `--rw-cpu-affinity 1` option, matching the
stock daemon's worker affinity while leaving the capture profile unchanged.
The candidate used the public lifecycle runner hook, verified the exact radio
and advertised affinity before RF, and retained both launch-script hashes.
It failed after 222 transported frames with the same one-block discontinuity;
normal ownership cleanup and full receiver restoration succeeded. This candidate
is rejected and was not installed or activated in production.

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
total charged qualification collection is 88.58881341299683 seconds;
1,711.4111865870032 seconds remain. Normal scheduled production attempts are
retained separately in the 23:00 failure log. No migration was changed.
Adaptive decision architecture and its deployment gates remain open.

Rollback configuration is retained in `/run/leo-radio003a-cutover/*.before` and
the previous exact-host credential in `/etc/leo/credentials/`; the earlier release
`98207d6fc6eaeaab1ab870998c1519afe0a6b892` remains installed. Restoring the old radio
would require revalidating its current reboot-generated SSH key.
