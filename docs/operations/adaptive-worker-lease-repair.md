# Adaptive worker lease repair

Status: DEPLOYED, long-running production verification in progress. This is a queue correctness priority independent of memory optimization or concurrency tuning.

## Problem and evidence

The adaptive worker claims a 20-minute lease and blocks in `subprocess.run` without renewing it. Tracking jobs observed on October 5, 2026 took 30–33 minutes. Workers 10, 11, and 17 raised `LeaseLostError` when recording completion. Processes can continue consuming resources after lease expiry, while the queue API and admission control exclude their expired leases. Consequently, configured capacity is not a reliable bound on actual running work.

Evidence: systemd journals for `leo-adaptive-analysis-worker@10`, `@11`, and `@17` around 15:20–15:23 America/Los_Angeles; deployed runner `/opt/leo-top-glrt/f69c55264c75/worker/src/leo/cli/adaptive_processing_queue.py`. Resource snapshots are at `/home/mouse9911/release-evidence/queue-memory-20261005/profile.json`.

## Implementation checklist

- [ ] Add lease supervision spanning claim, existing-result checks, child execution, validation, follow-up enqueue, and completion. Reuse the catalog's `heartbeat_job` port and extract shared lifecycle code where appropriate; do not import a private implementation from another component.
- [ ] Renew every 60 seconds with the existing 20-minute lease. Use monotonic scheduling and bounded database calls. Ownership must be checked against the database, including the attempt identity where needed to prevent stale attempts using a reused worker ID.
- [ ] Supervise a separate subprocess group. On confirmed lease loss, terminate and reap the entire group, escalating after a bounded grace period. Never complete or yield a job now owned by another attempt. On database outages, do not continue beyond the last confirmed safe lease deadline.
- [ ] Coordinate heartbeat and terminal updates so a heartbeat cannot race with successful completion and falsely report lease loss. Keep renewal alive during expensive validation. Handle SIGINT/SIGTERM through the same cleanup path.
- [ ] Preserve independent execution budgets and checkpoints. A renewable lease is not evidence that scientific work is progressing and must not turn a hung child into an immortal job.
- [ ] Reclaim expired attempts through the catalog. Reuse completed products only after validating the full input/configuration binding and every required artifact; a result directory alone is insufficient. Apply this to partial-band analysis, standard analysis, and tracking with all required position products.
- [ ] Expose expired/stale ownership separately from genuinely running work in operational diagnostics. Do not inflate live queue counts by treating all historical expired attempts as active.

## Safe rollout and recovery

- [ ] Pause new job claims and drain healthy work where feasible. Identify expired attempts and their actual process groups. Stop legacy processes before reclaiming their jobs; changing catalog state alone does not stop computation.
- [ ] Deploy the tested worker supervision. Reclaim affected attempts using the catalog and retain original attempt history. Do not directly mark expired jobs successful or discard saved scientific products.
- [ ] Start a canary worker, verify fresh heartbeats and result reuse, then restore the configured pool: 20 signal-analysis slots and 3 tracking slots, served by 23 workers.

## Acceptance criteria

- [ ] Component tests cover execution beyond an initial lease, renewal failure, database outage, stale attempt ownership, full child-group termination, shutdown, and heartbeat/completion races. PostgreSQL tests are explicitly marked.
- [ ] Recovery tests prove valid matching results are reused, mismatched/incomplete products are not accepted, and follow-up work is idempotent.
- [ ] A real tracking job remains visibly leased beyond 20 minutes, publishes required products, and records successful completion without `LeaseLostError`.
- [ ] No expired attempt retains a running process group after the termination grace period. Actual processes and queue capacity accounting agree.
- [ ] Record deployment revision, test results, recovered job IDs, and a verified long-running completion here before changing status to CLOSED.

No new RF collection is needed. Scientific algorithms, precision, candidate sets, and persisted product contracts need not change for this repair.

## Deployment evidence

PR: https://github.com/misko/leo-tracker-reduxredux/pull/59

On October 5, 2026, all legacy worker processes were stopped before the canary started at 15:55 America/Los_Angeles. The canary reclaimed jobs 47987, 48066, 48068, 48071, 48072, 48073, and 48075. The first four were completed using existing validated artifacts; the last three resumed processing. All 23 workers subsequently held fresh leases with no expired active rows or restarts during initial observation.

The immutable deployment is `/opt/leo-adaptive-lease/01dca90b1/src`. The initial canary used `e498f0297`; its lease-supervision module is byte-identical. The final revision additionally preserves existing PostgreSQL session options while adding connection and query timeouts. The configured pool remains 20 signal-analysis and 3 tracking slots.

Evidence directory: `/home/mouse9911/release-evidence/queue-lease-repair`. `before.json` records prior ownership, `recovered.json` records recovery, and `observation.jsonl` follows the three live tracking jobs. A real completion beyond the original 20-minute lease remains the final acceptance gate.
