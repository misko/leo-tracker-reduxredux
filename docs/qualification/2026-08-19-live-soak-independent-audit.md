# Independent live-soak audit

Date of snapshot: 2026-08-19 04:06:04 UTC  
Soak ID: `production-24h-20260819-01`  
Evidence root: `/srv/bulk/leo/qualification/soak/production-24h-20260819-01`

This is a read-only interim audit of WP10 and requirements R-006, R-030, and
R-032. It is not final acceptance evidence. The acquisition process, workers,
catalog, timers, and immutable evidence were not modified by this audit.

## Evidence that is currently healthy

At the snapshot, the bounded summary reported 14 of 14 trials committed, 840
sample-derived recording seconds in 1,051.992 active seconds (79.849% duty), no
policy violation, and:

- zero failed or degraded trials;
- zero invalid digests, false-complete claims, reported gaps, reported
  overflows, admission rejections, or post-commit callback failures;
- one successfully queued Standard run for every committed trial;
- minimum estimated dual-radio overlap of `0.9994009749666667`;
- process peak RSS of 359,407,616 bytes, 265,261,056 bytes above the immutable
  baseline and below the 512 MiB policy limit;
- maximum observed total queue depth 281, against an initial total queue depth
  of 278;
- storage utilization below 0.15% and no admission pressure.

All inspected trial files were contiguous, immutable per-index documents. Their
session IDs, states, digest results, sample totals, callback results, and queued
run IDs agreed with the aggregate. The PostgreSQL catalog contained one
30-job Standard run per soak session and no failed soak job.

The acquisition cgroup's apparent 17.4 GB memory peak was almost entirely
reclaimable write cache. At the snapshot, `memory.stat` attributed about 17.2
GB to inactive file pages and 134 MB to anonymous memory; swap cache and every
`memory.events` pressure/OOM counter were zero. Final evidence must retain this
distinction instead of treating cgroup `MemoryCurrent` as process heap.

The RAID6 was online with all four members (`[UUUU]`) and was 7.9% through its
resync at about 53.8 MB/s. The XFS data plane was mounted at `/srv/bulk` through
the 47.29 TiB writethrough-cached LVM volume. This is valid degraded-state
evidence, not the required post-resync tuning result.

The five-minute reconciliation and fifteen-minute retention timers were enabled
and their inspected invocations exited zero. Retention selected no victim at
the observed utilization and left admission open.

## Acceptance gaps that the aggregate does not expose

### Continuity is not observable on the Pluto transport (`RESOLVED`)

Every inspected live manifest truthfully records
`sample_loss_observable=false`, synchronization grade `degraded`, and
`guaranteed_overlap_ns=0`. The Pluto adapter has no device sample counter.
Consequently, zero `gap_count` and `overflow_count` means that no supported
counter reported a loss; it does **not** prove an unconditional absence of
sample loss. R-006/R-032 must not strengthen this evidence in the final report.

Commit `d3f65ac` resolved the acceptance ambiguity through reviewed change
control. The synchronization gate and ADR 0003 now require no unexplained loss
where continuity is observable and explicit non-observability otherwise; host
buffer counts alone never prove device-side loss absence. Future device/FPGA
counters or an independent continuity marker may strengthen new evidence but
must not reinterpret this run.

### Initial unrelated work masks the soak-specific queue

The summary's `processing_backlog_growth=3` compares total queue high-water 281
with an initial queue of 278 unrelated jobs. By the audit snapshot, all 278
inherited jobs had succeeded, while the soak cohort had produced 420 jobs: 251
were succeeded, 161 pending, and eight leased. Thus the soak-origin queue had
grown from zero to 169 even though the total-queue metric appeared nearly flat.

This does not yet prove a capacity failure: workers first had to drain the
inherited cohort, and the observation interval was short. It does mean the
aggregate alone cannot prove a bounded production queue. Final WP10 evidence
must report cohort-specific arrivals, completions, pending/leased high-water,
and end-of-run drain time. A pass should require that soak-origin backlog is
stable or draining over a representative steady-state interval, and preferably
drains to zero after acquisition stops.

A follow-up at 04:08:28 UTC was encouraging. The soak cohort then had 480 jobs:
369 succeeded, 103 pending, eight leased, and zero failed. Pending plus leased
had fallen from 169 to 111. The last inherited job completed at
03:57:18.615662 UTC; between that point and the follow-up, 270 soak jobs arrived
and 327 completed (approximately 0.393 and 0.476 jobs/second respectively).
This clears the declared instantaneous limit but is only an early interval, not
the required final-six-hour rate result.

### The active unit initially lacked the documented OOM preference (`RESOLVED`)

At the original snapshot, the live transient acquisition and all eight live
transient workers had `OOMScoreAdjust=200`. Acquisition therefore had no live
OOM preference over workers. The attempted persistent acquisition value of
`-100` was also below what this unprivileged user manager could apply.

This was corrected without restarting the soak. Acquisition parent and child
processes remain at 200, all eight worker parent and child processes were moved
to 500, and the API parent and child were moved to 400. Direct reads of every
live `/proc/<pid>/oom_score_adj` verified the ordering. Throwaway user-systemd
units separately verified that requested 200/400/500 values are applied as
observed, and persistent definitions now use those values. CPU and IO
scheduling remain correctly differentiated: acquisition uses weights 600/600
and best-effort IO priority 2; workers use weights 25/25, nice 10, and idle IO
priority 4.

`systemctl show` retains the transient units' original declarative value after
the live process adjustment, so final evidence must use both persistent unit
text and the authoritative live `/proc` values. Installed-unit restart behavior
remains a separate outstanding gate below.

### Duty and inter-capture latency needed external gates (`RESOLVED`)

The observed duty was 79.849%, substantially above the user's originally
expected 10–50% operating range, but the immutable policy has no minimum duty
field and `maximum_inter_capture_gap_seconds` is null. Its largest observed gap
at the earlier snapshot was 17.671 seconds. Therefore `passed=true` alone would
not prove the qualitative phrase "can approach 100% duty."

Commit `e377883` resolved this before completion by predeclaring external
production thresholds: at least 50% sample-derived duty, no gap above 30
seconds, soak-origin pending plus leased below 1,000 after inherited work
drains, and soak-cohort completions at least equal to arrivals over the final
six active hours. The first three thresholds were satisfied at the follow-up;
the six-hour window cannot be evaluated until late in the run.

### Restart and final capacity evidence remain outstanding

The persistent definitions and timer syntax validate statically, and the live
transient services run, but this audit found no target-host evidence that the
installed persistent acquisition unit has actually restarted/resumed the soak
or survived a reboot. Conduct a controlled post-soak restart/resume test without
rewriting this run's immutable trial evidence.

The resync ETA was roughly five days. The existing writer and worker numbers
are deliberately conservative degraded-state measurements. As required by the
runbook, rerun sustained writer and worker-capacity tuning after resync before
fixing production worker count or declaring the complete R-032 capacity gate.

## Interim requirement verdict

- **R-006:** in progress; capture health is strong, but duration is incomplete
  and cohort-specific queue boundedness is unproven. Loss non-observability is
  now explicitly and honestly accepted by the amended gate.
- **R-030:** in progress; CPU/IO and live OOM ordering are proved, but
  installed-unit restart behavior is not.
- **R-032:** pending; it requires all preceding gates, the terminal 24-hour
  summary, drain/capacity evidence, the restart campaign, post-resync tuning,
  and the separately pending scientific parity requirement.

Do not mark WP10 or these requirements complete until the terminal summary says
`status=complete`, `completion_reason=duration`, and `passed=true` **and** the
independent gaps above have either been closed or explicitly resolved through
reviewed requirement change control.
