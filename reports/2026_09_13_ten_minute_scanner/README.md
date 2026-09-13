# Ten-minute scanner start cadence

The user changed the requested interval from twenty to ten minutes on
2026-09-13. Acquisition release `1212242843055e7e4079143ab1940532e8ac76fd`
was activated at 00:51:57 UTC with an acquisition-only
`LEO_SCANNER_INTERVAL_SECONDS=600` override. The common environment retains its
historical default for the other components.

The service remains on the qualified `single-rx-random-10m-300s-v1` fixed-order
profile: selected radio `104000bac4950008230026001b440a003a` at `192.168.1.17`,
one physical RX selected from the durable scan identity, native 10 MS/s,
300-second acquisitions, 120 ms valid visits, 262,144-sample refills, and 32
kernel buffers. Host adaptive feedback is still under implementation and is
**not activated by this cadence release**. Its accepted deployment plan also
uses the requested ten-minute cadence.

## Contracts and restart behavior

`SingleRxScheduledScannerIntentV3` binds the 600-second interval. Published V2
intents still require 1,200 seconds and reject V3 bytes. Native recording,
receiver mapping, analysis and RF geometry contracts are unchanged. The random
RX choice is preserved for UTC slots shared by the two cadences.

The first cutover exposed a real transition fault: the restarted supervisor
attempted to enqueue the already completed 00:40 slot with a different intent.
The catalog correctly rejected that overwrite. The prior release was restored
while the fault was corrected. The supervisor now reads an existing slot through
the catalog port before compiling another intent. Its immutable history remains
intact; any pending historical work still passes ordinary runtime admission.
The catalog's conflicting-enqueue checks remain strict, including races.

The corrected restart waited for a separate radio `.20` firmware deployment to
release the station's shared acquisition lock. No competing process was stopped
and no radio lock was bypassed. The final restart helper reported capture running.
The live process then used `--interval-seconds 600`, and durable operation 10302
bound the 00:50 UTC slot to schema V3, interval 600, RX0, and 10 MS/s. This first
slot started late during cutover; subsequent slots stay on UTC ten-minute
boundaries rather than sleeping ten minutes after a scan finishes.

## Validation

- 79 scanner, CLI, supervisor and acquisition restart-control tests passed.
- 16 real PostgreSQL acquisition queue tests passed in isolated schemas under
  the explicitly selected `leo_tracker_test` database. No production database
  schema or historical acquisition payload was changed.
- Ruff and whitespace checks passed for the changed components.
- The immutable release passed source, runtime and publication verification;
  the production web assets were built successfully. API/UI and analysis release
  selectors were retained. The served CSS and JavaScript returned HTTP 200.
- The preceding 00:40 scan completed as `scan-hop-bdb6309ec18cd7f6`, with 2,387
  visits and 95.4675% valid duty; its published receipt was qualified. Full native
  analysis completed at 00:54:29 UTC. All three published plots returned HTTP 200,
  matched their manifest byte counts and hashes, and passed PNG decoding.
- The first ten-minute-cadence recording, `scan-hop-c83b1b5dd15497a2`, completed
  at 00:57:15 UTC: RX0, 10 MS/s, 300 seconds, 2,387 visits, **95.4505% valid duty**,
  continuity attested, settings restored, and qualified. Durable operation 10302
  succeeded. It appeared in the web history with full analysis pending. The
  service restarted successfully at 00:57:20 UTC to wait for the next slot.

## Rollback

The original acquisition environment and selector are retained in the private
root-owned directory `/run/leo-10min-cutover`. To revert, restore its
`acquisition.env.before`, select acquisition release
`eefcb4f080907c51cddb505944ed4b1caf899751`, and use the acquisition restart helper
between scans. Completed V3 slot history must remain intact. The newer release
can also return to a 1,200-second override without changing radio code.

Research commits: `a41d189e` and `dc750982`. Deployment commits: `2c70d843`
and `12122428`. The first deployment's rejected restart and successful rollback
are retained alongside the successful final restart and release build logs.
