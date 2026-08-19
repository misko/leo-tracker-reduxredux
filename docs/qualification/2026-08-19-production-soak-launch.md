# Production 24-hour soak launch

Date: 2026-08-19 03:47:45 UTC  
Soak ID: `production-24h-20260819-01`  
Code baseline: `d8a4ff3`  
Evidence root: `/srv/bulk/leo/qualification/soak/production-24h-20260819-01`

The production dual-Pluto soak was launched as the persistent user-systemd unit
`leo-soak-production-24h-20260819-01.service`. User lingering is enabled, so
the unit continues independently of an interactive login. The command uses the
ordinary production acquisition path, the 60-second 2.5 MS/s profile, both RX
paths on both radios, zero scheduled cadence, resumable evidence, and a target
of 86,400 active seconds.

Eight persistent processing units, `leo-soak-worker-01.service` through
`leo-soak-worker-08.service`, run the real Standard graph concurrently. The
acquisition unit has CPU/IO weight 600 and best-effort IO priority 2. Workers
have CPU/IO weight 25, nice 10, and idle IO scheduling.

The initial live processes were launched as transient user units. Equivalent
persistent user-unit definitions were then installed under
`~/.config/systemd/user`, enabled under `default.target`, and validated with
`systemd-analyze --user verify`. User lingering is enabled. A reboot therefore
starts the API, eight templated workers, and the resumable soak command with the
same immutable definition and soak ID. The environment file is mode `0600`.

The first durable trial was verified after launch:

- state `committed`, with no gaps, overflows, or policy violations;
- 60 seconds recorded in 69.734 active seconds (86.042% duty);
- minimum estimated overlap fraction `0.99997205635`;
- post-commit registration succeeded and queued one Standard run;
- all nine units remained active;
- the queue reported 279 pending, 8 running, and 0 failed jobs;
- the host had 96 GiB memory available;
- RAID6 remained healthy (`[UUUU]`) while rebuilding at about 50 MB/s.

At seven trials, systemd charged about 8.9 GiB to the acquisition cgroup while
the harness reported roughly 353 MiB peak process RSS. Cgroup `memory.stat`
resolved the apparent mismatch: approximately 8.94 GiB was reclaimable inactive
file cache, anonymous memory was about 118 MiB, swap was zero, and all memory
pressure/OOM event counters were zero. Final reporting must keep page cache and
process-memory growth separate.

The first soak-created Standard run,
`capture-dac202f406bc4727aa781fe6cddd8602`, sealed successfully at
03:57:19 UTC while acquisition continued. All 30 jobs succeeded: 22 produced
complete products and eight produced explicit scientific `no_result` outcomes.
The run was atomically promoted current and its whole-dwell candidates,
coverage, CFO fields, controls, and rejected scientific-confidence result were
read back through the production HTTP API. This is live vertical evidence, not
a fixture projection. Rejection is the honest result: every candidate failed at
least one precommitted control, so no detection claim was published.

This report records launch evidence only. WP10, R-006, R-030, and R-032 remain
in progress until the immutable final summary reports
`completion_reason=duration` and `passed=true`. Do not infer final acceptance
from this file.

Monitor with:

```text
systemctl --user status leo-soak-production-24h-20260819-01.service
jq . /srv/bulk/leo/qualification/soak/production-24h-20260819-01/summary.json
journalctl --user -u leo-soak-production-24h-20260819-01.service -f
```
