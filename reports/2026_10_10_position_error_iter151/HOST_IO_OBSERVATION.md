# Live host I/O observation

Read-only observation around 2026-10-10 05:18 UTC. No worker, scientific budget,
durability policy or host setting was changed; no process was restarted.

Both active search children were single-threaded. Around elapsed 6m54s for
DS16-058 and 5m19s for DS16-054, `ps` reported accumulated CPU times of 3m55s and
3m30s respectively. Both were observed in uninterruptible sleep, and privileged
reads of `/proc/<pid>/wchan` reported `jbd2_log_wait_commit` for each. Host I/O
pressure reported `some avg10=64.57` and `full avg10=60.54`; CPU pressure was
`some avg10=0.05`. These are point-in-time host observations, not full-run averages
or a measurement of all delay causes.

At that check, DS16-058 had approximately 13.35 MB physical reads and 9.33 MB
physical writes; DS16-054 had approximately 12.99 MB reads and 7.42 MB writes.
Small byte totals do not imply negligible journal wait latency. The frozen 116
durable writer calls `os.fsync` before publishing each JSON receipt by exclusive
hard-link creation. That source
behavior is consistent with the observed journal wait, but does not identify
which other host workload, device state or journal activity caused the pressure.

The filesystem had approximately 40 GB free. Completed member directories were
133 MB and 125 MB; the pilot results occupied 262 MB at the earlier size check.
No cleanup or QNAP mutation was performed or proposed.

Report recorded invocation wall times truthfully. Do not present them as pure
optimizer CPU costs or a cold embedded-platform benchmark. Wall-clock budgets
remain frozen; any later exhaustion must stay visible, with host contention
noted as a possible contributor rather than silently extending or restarting it.

## Follow-up: automatic Git repacking

Free space later fell to approximately 21 GB, then 18 GB. Pilot results had only
grown to 276 MB. A read-only process audit identified background automatic Git
maintenance in the shared repository: PID 1616345 (`git gc --auto`) supervised
1616346 (`git repack`), whose initial pack-objects child 1616347 wrote about
20.48 GB. Its temporary reachable-object pack measured 20,479,366,434 bytes.
The initial child exited naturally before any intervention; a subsequent cruft
pack child 1621947 was then observed. No process was signaled, no pack/object was
removed manually, and no Git configuration was changed.

This is a substantial concurrent writer and a plausible contributor to the
observed journal pressure, not proof that it caused every delay. At the latter
check I/O pressure had already fallen to `some avg10=1.72`, `full avg10=1.71`,
and both research children were running. Space reclamation remained pending.
Let the existing repack finish and verify disk space afterwards. Future report
commit/merge/push commands in this session should use per-command
`git -c gc.auto=0 -c maintenance.auto=false` to avoid initiating another large
maintenance job during the numerical comparison. This does not change scientific
sources, worker budgets, or repository-wide configuration.

At approximately 39 minutes after the pilot launch, GC/repack PIDs 1616345 and
1616346 were no longer present and filesystem free space had recovered to about
45 GB. Both research children were observed running. This resolves the temporary
space-pressure observation; the earlier wall-time effects remain part of the
experiment record. No manual cleanup, process interruption or global setting
change was needed.
