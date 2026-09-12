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
ownership was transferred to `leo` and the service restarted. The public capture
authority reports running, with no active acquisition lease. The next normal slot
is 23:00 UTC; its complete capture, analysis and browser output remain to verify.
The restart helper's standalone status invocation lacks systemd credentials;
the equivalent read-only capture-authority check succeeded with scanner admission
disabled for that command only, followed by normal systemd startup with credentials.

The active adaptive qualification RF ledger charges both partial RF checks in
full, including preparation and cleanup. Total charged collection is
77.86576568294957 seconds; 1,722.1342343170505 seconds remain. No migration was changed.
Adaptive decision architecture and its deployment gates remain open.

Rollback configuration is retained in `/run/leo-radio003a-cutover/*.before` and
the previous exact-host credential in `/etc/leo/credentials/`; the earlier release
`98207d6fc6eaeaab1ab870998c1519afe0a6b892` remains installed. Restoring the old radio
would require revalidating its current reboot-generated SSH key.
