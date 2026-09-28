# Adaptive capture publication recovery

Investigation on 2026-09-27 found that acquisition was healthy but publication
was stalled. Eight consecutive automatic captures completed between 01:16 and
02:05 UTC. The Web UI and its v3 adaptive-session API still showed the 00:30
capture as newest.

Two firmware import workers had spent roughly 30 minutes blocked in XFS fsync
waiting for writeback. Both timed out without publishing. The storage volume
had 28 TB free, and the NVMe spool had 1.2 TB free. RAID members were healthy.
This was an I/O progress problem, not a missing capture schedule or full disk.

Recovery actions:

- Installed `deploy/systemd/leo-adaptive-spool-publication-priority.conf` as
  `/etc/systemd/system/leo-adaptive-spool-transfer.service.d/zz-publication-priority.conf`.
  Publication now uses best-effort I/O priority 4 instead of idle scheduling,
  with IOWeight 500. Applied the same priority to the running publisher workers.
- Lowered the existing full-corpus search (PID 1361911) to CPU nice 19 and idle
  I/O priority. Temporarily paused it with an independent timed resume safeguard;
  explicitly resumed it afterward and stopped the safeguard timer.
- Idle priority alone did not prevent the stall from returning. Moved only that
  search process into the transient `leo-bulk-search-throttled.scope`, with
  `IOReadBandwidthMax=/dev/mapper/vg_bulk-bulk 2097152`. Its original cgroup was
  `/user.slice/user-1000.slice/session-313.scope`. The search continues running;
  the scope lasts for its lifetime. The cgroup's `io.max` confirms the limit.
- Temporarily reduced the live bulk cache migration threshold from 131072
  sectors, through 16384 and zero while draining contention, then set it to
  32768 sectors. This final runtime setting permits two 8 MiB cache blocks of
  migration. It is not an on-disk LVM configuration change. The original runtime
  value can be restored with `dmsetup message vg_bulk-bulk 0 migration_threshold 131072`.

Cache migration throttling follows the kernel's documented live-message
interface: https://docs.kernel.org/admin-guide/device-mapper/cache.html .

Systemd verification accepted the publication unit (only unrelated existing
CPUAccounting deprecation warnings). Acquisition was not interrupted: it started
automatically at 02:07:35, finished successfully at 02:12:39, and scheduled the
next capture for 02:14:39 UTC. Its timer remains enabled after reboot.

The browser's global “CAPTURE STOPPED” indicator belongs to the separate legacy
controller; it does not represent the adaptive service's state.

At 02:15 UTC, a Chromium browser observed the history refresh, selected
`scan-fw-e84e2f55976c0a8c`, and verified its rendered detail page: RF start
01:53:28 UTC, 300-second span, 2.5 MS/s, both receivers, 2221/2221 retained visits.
See `web-ui.png`. The API independently returned the same capture as newest.
The 02:00 capture's import continued progressing (10.8 GB of 16.0 GB copied at
the final check); publication backlog recovery is still in progress.

The subsequent acquisition started automatically at 02:14:39 UTC. Both the
acquisition and publication timers remain enabled. No capture scheduler change
was necessary during this recovery.
