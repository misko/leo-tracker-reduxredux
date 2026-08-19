# Remaining-requirements audit

Snapshot: 2026-08-19 04:15-04:17 UTC  
Repository head: `a09f737`  
Production soak: `production-24h-20260819-01`

This is an independent, read-only audit of the requirements that are not yet
`DONE` in `plan.md`. It did not restart acquisition, processing workers, or the
API, and it did not read from or write to `/mnt/qnap01`. The live database and
qualification files were queried read-only.

## Verdict

The current plan statuses are correct: WP5 and WP10 remain `IN PROGRESS`, and
R-006, R-018, R-030, and R-032 remain `PENDING`. No terminal evidence available
at this snapshot supports promoting any of those rows.

The live system is healthy enough to continue qualifying. At 04:15:32 UTC the
soak had committed 22 of 22 trials, captured 1,320 sample-derived seconds in
1,655.857 active seconds (79.717% duty), and reported no failed/degraded trial,
invalid digest, false-complete result, admission rejection, callback failure,
reported gap, reported overflow, or policy violation. The largest observed
inter-capture gap was 18.758 seconds and minimum estimated overlap fraction was
0.999401. These are interim observations, not terminal acceptance.

The PostgreSQL soak cohort then contained 575 succeeded jobs, 77 pending jobs,
and eight leased jobs for 22 runs, with no failed job. All eight live worker
parent/child process pairs had `/proc/<pid>/oom_score_adj=500`, the API pair had
400, and acquisition had 200. All live units reported `NRestarts=0`. The
declarative `systemctl show` value remains 200 for the transient subordinate
units; the authoritative live values are the direct `/proc` readings, as
already explained by the independent soak audit.

## Exact remaining gates

### Post-audit closure: generated storage/fault campaign

Commit `beceb39` subsequently closed the generated isolated portion of the
storage-pressure/fault campaign identified below. Its report is
`docs/qualification/2026-08-19-isolated-storage-pressure-fault-campaign.md`:
18/18 focused checks passed on the target host, exact 75%/80% boundaries and
atomic-publication-to-catalog recovery gained direct coverage, disposable
PostgreSQL schemas were removed, live PIDs/restart counts stayed unchanged, and
QNAP was not accessed. The campaign deliberately simulated utilization rather
than filling the RAID, so it does not replace post-resync capacity evidence.

### R-006: terminal acquisition and processing-rate evidence

The immutable summary still says `status=running`, `complete=false`,
`completion_reason=running`, and `passed=false`. R-006 therefore still needs:

1. a terminal summary with `status=complete`, `completion_reason=duration`,
   `passed=true`, and 86,400 active seconds;
2. independent verification of every trial document and referenced bundle
   digest, with no unexplained loss where observable and explicit
   non-observability otherwise;
3. final external checks of duty at least 50% and maximum inter-capture gap at
   most 30 seconds;
4. soak-cohort pending plus leased below 1,000 after inherited work drained;
5. soak-cohort completion rate at least the arrival rate over the final six
   active hours, followed by a measured drain to zero after acquisition stops;
6. final RSS, cgroup page-cache/anonymous-memory, service restart-count, and
   storage/admission evidence.

The aggregate summary's queue field cannot prove items 4-5 because its baseline
included 278 inherited jobs. The final report must join `analysis_run` and
`processing_job` by the soak session prefix and use run/job timestamps. Trial
files provide capture and callback timestamps, and PostgreSQL currently retains
`created_at` and `updated_at`, so this evidence is collectable.

Pluto exposes no device sample counter in this path. Every live claim must
retain `sample_loss_observable=false`, `guaranteed_overlap_ns=0`, and the
degraded synchronization grade. Zero host-reported gaps/overflows is not proof
of zero device-side sample loss.

### R-018: J1 parity evidence is unavailable

RETRO parity is reproduced, but the exact J1 IQ window and frozen calibration
identified by the historical report are unavailable. The bounded recovery
audit in `docs/j1_recovery_audit.md` found neither required IQ digest nor the
required calibration digest. Derived JSON/PNG output is not a substitute for
the bytes.

R-018 cannot be completed by rerunning current code. It needs either exact-byte
recovery under the acceptance rule in that audit, or explicit reviewed change
control that revises the requirement without claiming J1 recovery, calibrated
parity, or specificity. No such change should be inferred from absence.

### R-030: target-host production deployment and restart are unproved

Resource priority is demonstrated live, and persistent user-unit definitions
validate statically. Runtime deployment evidence remains incomplete:

- the active acquisition, workers, and API are transient units under
  `/run/user/1000/systemd/transient`;
- same-name persistent API/soak files and templated persistent workers are
  installed below `~/.config/systemd/user` and linked from `default.target`,
  but the live transient units shadow them;
- no installed persistent unit has resumed this soak after a real service
  restart or reboot;
- the canonical continuous-production templates in `deploy/systemd`
  (`leo-acquisition.service`, `leo-worker@.service`, and `leo-api.service`) are
  not installed as target-host system services. The current persistent soak
  unit is a bounded resumable qualification command, not continuous production
  acquisition.

After the terminal soak, conduct a controlled restart/resume test that preserves
the immutable completed evidence, verify process-level 200/400/500 OOM ordering
and CPU/IO weights after restart, and prove committed-bundle, expired-job, and
current-run recovery. Then select and install the actual production topology.
If user units replace the canonical system-unit topology, record that as an
explicit deployment decision and include a continuous acquisition unit; do not
treat the one-off soak unit as the production acquisition service.

### R-032/WP10: remaining production campaign and operational evidence

R-032 also depends on every preceding gate, so R-018 alone prevents closure.
Independent of that dependency, these WP10 deliverables lack target-host
acceptance evidence:

1. **Storage-pressure and fault-recovery campaign (`CLOSED` after this
   snapshot).** Commit `beceb39` now supplies the committed target-host report
   and integrated generated-data coverage described in the post-audit closure
   above. Real storage-fill throughput remains part of the separate post-resync
   capacity gate, not this functional campaign.
2. **Nightly/release corpus plus Chromium execution.** CI configuration exists,
   including a fail-closed self-hosted `real-corpus` job and production-path
   Playwright. This checkout has no Git remote, no Actions runner service was
   found on the host, and no CI run artifact is committed. The deployed
   `leo-qualification.timer` template runs bounded radio acquisition only; it
   does not run the detector corpus or Chromium. Record one complete release
   execution and provide an operational scheduled path for the recurring lane.
3. **Post-resync capacity and tuning.** `/proc/mdstat` showed healthy `[UUUU]`
   RAID6 members but only 8.1% resync completion at about 50.3 MB/s. Existing
   writer/worker figures are deliberately degraded-state evidence. After
   resync, rerun sustained 128 MiB-shard writer and Standard worker benchmarks,
   record compression/throughput/RSS and safe concurrency, and configure worker
   count, admission reserve, and expected duty thresholds from those results.
4. **Final traceability report.** Re-run all mandatory repository gates and
   production HTTP/CLI/Chromium checks against the final code/deployment, then
   map each exact acceptance item to immutable evidence. A clean test suite is
   necessary but cannot substitute for the long-duration, restart, storage,
   scientific, and post-resync host gates above.

## Evidence that should not be strengthened

- `summary.passed=false` is expected while the soak is running; it is not a
  failure, and interim health is not a pass.
- Estimated overlap is not guaranteed overlap, phase coherence, or proof of
  device-side continuity.
- The current 50 MB/s RAID-rebuild state is a degraded baseline, not final
  production capacity.
- The J1 reports and plots prove historical provenance only; they do not prove
  recoverable IQ or calibration.
- Static unit verification and enablement symlinks do not prove restart or
  reboot behavior.

## Safe work while the soak continues

Without touching live recordings, the production catalog, active services, or
QNAP, the generated isolated storage-pressure/fault campaign was executed and
documented in commit `beceb39`; the final release corpus/Chromium command can
also be prepared. The terminal soak calculations, installed-unit restart, and
post-resync tuning must wait for their respective external conditions.
