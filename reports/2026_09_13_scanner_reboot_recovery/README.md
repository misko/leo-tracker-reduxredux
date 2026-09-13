# Scanner recovery after host and radio reboot

The host rebooted shortly before 17:00 UTC on 2026-09-13. The acquisition service
started automatically, but the 17:00 slot failed because the selected radio's
ED25519 host key had changed. Strict host verification correctly rejected it.

The user reported the reboot and had previously authorized the radio's known
reboot-related key rotation. A connection pinned to the newly observed key read
the exact selected hardware serial `104000bac4950008230026001b440a003a` at
`192.168.1.17` and firmware `v0.49-plutoplus-spf-iq-direct-async-v4`.
The new fingerprint is
`SHA256:X9unZ6d5Gy4WAKw220qeh046x8MkxwqJA7b9Qcr/W0w`.

The previous pin was preserved under the root-only directory
`/etc/leo/credentials/reboot-recovery-20260913`. The replacement was installed
atomically, and strict SSH checking remains enabled. The restarted service's
systemd credential was checked against the replacement fingerprint.

The first safe restart waited for a separate `.20` firmware deployment to
release the station's global acquisition lease. It timed out and left capture
paused and the service stopped. Once the lease cleared, the restart succeeded,
and capture was explicitly resumed through the public CLI. Desired and observed
capture state both reported `running`.

## Deployed behavior

Acquisition release `1212242843055e7e4079143ab1940532e8ac76fd` remains selected.
It records one physical RX chosen from each durable scan identity at native
10 MS/s for 300 seconds, with ten-minute UTC start slots, 120 ms valid visits,
262,144-sample refills and 32 kernel buffers.

This is the qualified **fixed-order** profile. Host adaptive feedback has not
been deployed; enabling an adaptive flag on this release would not supply the
missing single-RX feedback integration and qualification. Recovery must not be
reported as a successful adaptive deployment.

## Recovery checks

- The stock iiOD endpoint at `.17:30431` responded to `VERSION` with `0.25.v0.25`.
- Acquisition, API and the analysis timer are enabled at boot.
- Host UTC is NTP-synchronized; `/srv/bulk` is mounted read/write and has about
  40 TB free.
- The web page's referenced JavaScript and CSS returned HTTP 200; their byte
  counts and hashes are retained in `web-assets.json`.
- The 17:10 UTC slot exhausted three attempts on `radio lease is busy` while a
  separate `.20` live RF test held the global acquisition lock. That test released
  the lock by 17:14:13, but a new `.20` firmware deployment held it again at
  17:15:59. The service remains active on its ten-minute cadence, with the next
  slot at 17:20 UTC. A completed new capture and its subsequent publication are
  still required to verify recovery.
- A user question is pending about asking the separate `.20` task to pause new
  RF tests after its current capture for scanner verification. No task message
  was sent, competing process stopped, or acquisition lock bypassed.

The last successful pre-recovery scan was the 02:40 slot, on RX1 at 10 MS/s and
95.4307% valid duty, with full analysis complete. The 02:50 slot failed on radio
lease contention; subsequent inspected slots failed the stock iiOD preflight.
Those historical failures are preserved. This recovery does not establish their
original cause; the rebooted endpoint is healthy in the checks above.

No application code, immutable release or historical acquisition intent was
changed. No additional RF qualification campaign was launched.
