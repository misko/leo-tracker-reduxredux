# Isolated storage-pressure and fault campaign — 2026-08-19

## Result

**PASS for the generated-data campaign: 18/18 checks passed in 6.48 seconds.**

This campaign ran on the production host at repository revision
`9de3879914521ed781dff90deff89553c0cee528` with Python 3.12.14,
PostgreSQL 18.4, and Linux 7.0.0-29-generic. It exercised the production
retention planner, catalog fencing, local purge executor, RecordingStore
publication, and reconciliation implementations. It did not use mocks for the
filesystem or catalog.

This was deliberately an **isolated functional fault campaign**, not a real
47 TB filesystem-fill or I/O-capacity test. Storage utilization was supplied to
the planner as generated `StorageUsage` values. No live catalog row or live
recording was used or mutated, and no production service was restarted.

## Isolation and scope

- All generated filesystem data was confined to
  `/srv/bulk/leo/qualification/storage-fault-campaign.GSCmlt` (368 KiB after
  the run). The final pytest base directory was
  `/srv/bulk/leo/qualification/storage-fault-campaign.GSCmlt/final-pytest`.
- Catalog-backed checks created, migrated, used, and dropped a fresh PostgreSQL
  schema per test. The observed schema names in a supplementary lifecycle run
  were `leo_test_5583229a23aa47e8a21075d01aee1073` and
  `leo_operations_4942b73766f8499386eae8241b391af6`. A post-run query returned
  `<none>` for both temporary-schema prefixes.
- PostgreSQL `public` remained the live catalog. The campaign never selected it
  as a test search path. Public counts rose from 139 to 141 capture sessions,
  140 to 142 analysis runs, and 4,114 to 4,174 processing jobs while the live
  soak continued; the exact +2/+2/+60 shape is normal soak progress. Public
  retention events remained zero.
- `/mnt/qnap01` was never listed, opened, resolved, read, written, moved,
  renamed, or deleted. The campaign intentionally excluded
  `test_qnap_mount_can_never_be_configured_as_a_destructive_root`. Its only
  similarly named path was generated beneath the isolated pytest root:
  `.../test_purge_rejects_qnap_other_0/mnt/qnap01`.
- A static source audit confirmed that `_validated_local_bulk_root` rejects both
  lexical and resolved descendants of `/mnt/qnap01`, while every stage,
  restore, and discard path also passes a strict-descendant check.

## Behaviors proved

### Watermarks and safety

- 69.9% does not start retention; exactly 70% does.
- Selection is oldest-first and continues until predicted utilization is at or
  below the exact 65% target (the generated example reached 64%).
- Warning is false at 74.9% and true at exactly 75%.
- With unreclaimable pressure, admission remains allowed at 79.9% and stops at
  exactly 80%.
- Held, `TEST`, active-work, uncommitted, unreconciled, and already-purging units
  are ineligible.
- Catalog candidate selection excludes held and TEST sessions, sessions with
  active work, and the product belonging to the current analysis run. A
  superseded product is eligible. Raw session retention remains intentionally
  independent of “current analysis”: accepted analysis makes raw data eligible
  unless a TEST or operator hold protects it.
- A hold created after staging but before the catalog purge commit wins the
  fence, restores the bundle, and leaves the catalog committed.

### Publication, reconciliation, and recovery

- Interruptions after manifest fsync or manifest rename remain partial spool
  state and are not reported as committed.
- Interruptions after the atomic session rename or parent-directory fsync are
  reported as valid committed bundles.
- The added integration check interrupts publication immediately after the
  atomic session rename, verifies that the catalog is initially missing the
  session, runs production reconciliation, and verifies that the valid bundle
  is registered as committed.
- Reconciliation ignores incomplete spool content and automatically creates a
  durable hold for a committed TEST bundle.
- A process death after a purge stage is recovered by restoring the original
  recording and releasing the claim.
- A completed purge commit leaves a catalog tombstone; asynchronous recovery
  discards only the journaled trash entry and records reclaimed bytes.
- Session and artifact purges use exact, journaled targets. Escape attempts and
  symlinked content fail closed.

## Exact campaign command and output

```bash
TMPDIR=/srv/bulk/leo/qualification/storage-fault-campaign.GSCmlt uv run pytest -vv --durations=20 --basetemp=/srv/bulk/leo/qualification/storage-fault-campaign.GSCmlt/final-pytest tests/operations/test_retention.py::test_retention_starts_at_70_and_selects_oldest_until_65 tests/operations/test_retention.py::test_warning_and_admission_stop_boundaries_are_exact tests/operations/test_retention.py::test_protected_candidates_are_never_selected_and_80_can_stop_admission tests/operations/test_retention.py::test_purge_stages_restores_and_discards_only_local_recording tests/operations/test_retention.py::test_artifact_purge_is_exact_journaled_and_recoverable tests/operations/test_retention.py::test_purge_rejects_qnap_other_roots_and_symlinked_content tests/catalog/test_retention_repository.py::test_candidates_exclude_holds_test_active_work_and_current_product tests/catalog/test_retention_repository.py::test_product_purge_is_fenced_and_marks_availability tests/storage/test_recording_store.py::test_publication_faults_are_unambiguously_partial_or_committed tests/operations/test_catalog_retention.py::test_stage_commit_tombstone_then_async_discard tests/operations/test_catalog_retention.py::test_process_death_after_stage_is_recovered_by_restore tests/operations/test_catalog_retention.py::test_concurrent_pin_receipt_wins_before_purge_commit tests/operations/test_catalog_retention.py::test_reconciliation_registers_only_committed_public_bundles_and_test_hold tests/operations/test_catalog_retention.py::test_reconciliation_recovers_publication_interrupted_after_atomic_commit tests/operations/test_catalog_retention.py::test_hold_crash_windows_remain_fail_safe
```

Result:

```text
collected 18 items
18 passed in 6.48s
```

The supplementary schema-lifecycle observation ran two representative checks
while polling only PostgreSQL namespace metadata. It returned:

```text
2 passed in 1.26s
leo_operations_4942b73766f8499386eae8241b391af6
leo_test_5583229a23aa47e8a21075d01aee1073
<none>
```

## Live-service continuity evidence

Read-only snapshots bracketed the campaign at 04:20:07Z and 04:22:00Z.
Throughout both snapshots:

- `leo-soak-production-24h-20260819-01.service` was active/running with PID
  384640 and zero restarts;
- `leo-api-production.service` was active/running with PID 482118 and zero
  restarts;
- all eight soak workers were active/running with unchanged PIDs and zero
  restarts; and
- the live public catalog recorded zero retention events.

The campaign therefore proves the specified functional boundaries and recovery
paths on the target host without claiming real storage-pressure capacity. A
separate post-RAID-resync benchmark remains necessary for production throughput
and concurrency sizing.
