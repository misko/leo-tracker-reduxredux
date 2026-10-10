# Result-storage relocation review

Source-only operational review; no result files were moved, copied, removed or
evaluated. Relocation is suitable **after both batch-0 shard handles have exited,
their terminal receipts have been verified, and no child writer remains**. Keep
the repository-facing `results` path unchanged as a symlink to
`/srv/bulk/leo/research/position-error-iter164-results`.

The supplied capacity estimate is about 24 GB of eventual raw results against
35 GB free on root and about 12 TB free on bulk; this review did not independently
measure those sizes. Filesystem metadata confirms bulk is a local XFS mount
(`/dev/mapper/vg_bulk-bulk`), distinct from the root ext4 mount. The bulk research
parent is owned by `mouse9911`; the current result directory is owned by root.
This is not a QNAP operation and must not touch `/mnt/qnap01`.

## Why the scientific identity survives

- [164 execute.py](execute.py) obtains the output directory from `--output`,
  defaulting to `HERE/results`. Its source, input and runtime verification does
  not incorporate that output directory into the protocol digest.
- [164 ports.py](ports.py) adapts the frozen
  [129 search](../2026_10_09_position_error_iter129/search.py) and
  [continuation](../2026_10_09_position_error_iter129/continuation.py). The two
  discovery-arm point keys, physical case identities, stage keys and protocol
  digests depend on inputs and scientific state, not output absolute paths.
  Search points, stage claims, slice accounting and traces are located beneath
  the caller's output directory.
- [116 DurableCache and append](../2026_10_09_position_error_iter116/driver.py)
  address points by canonical scientific key and verify the protocol digest.
  `append` writes a temporary file beside the destination, fsyncs it, then uses
  an exclusive hard link in that same directory. Following the result-directory
  symlink leaves both temporary and destination files on bulk, so this does not
  require a cross-filesystem hard link.
- [164 batch.py](batch.py) reads prior batch claims and terminal receipts through
  the same output path. Copying **every** file preserves no-retry and accumulated
  budget semantics; moving just final results would not.
- [164 evaluation.py](evaluation.py) hashes relative receipt paths. The inherited
  [129 report reader](../2026_10_09_position_error_iter129/report_cohort.py) also
  records lexical path strings for timing and receipt provenance. Continuing to
  pass the original repository-facing path preserves those strings. Do not
  rewrite existing receipts to replace paths, and do not switch future commands
  to a different `--output` spelling.

No output-location binding was found in the frozen numerical/evaluation protocol
configuration. This is a source-level conclusion, not permission to regenerate
either protocol or any scientific receipt. Error text can incidentally contain
a path; retain its bytes unchanged.

## Smallest safe procedure

1. Wait for authoritative terminal process handles and verify both batch-0
   receipts/claims and all their expected member phases. Confirm there are no
   live descendants or other writers. Suspend subsequent batch launches through
   the entire copy and cutover. Preserve failed/orphan evidence as-is; do not
   convert it into an automatic retry.
2. Enumerate the original tree without following interior symlinks. Record a
   sorted manifest of every relative path, entry type, regular-file byte length
   and SHA256, and any symlink target; include hidden files and empty directories.
   Reject unexpected special files or unresolved temporary writes for manual
   investigation. Record permissions/ownership separately for operational checks.
3. Copy into a new, explicitly named bulk staging directory without deleting
   anything at the source. Preserve file bytes and relevant permissions. Audit
   the copied tree independently against the manifest: exact path/type set,
   sizes, hashes and symlink targets. Recheck the source manifest unchanged.
   Preserve the audit manifests outside both trees. No checksum mismatch is
   repairable by changing a receipt or accepting a subset.
4. Rename the verified staging directory to the final bulk destination on the
   bulk filesystem. With writers still stopped, rename the original local
   directory to a clearly named backup on root; create the original `results`
   path as a symlink to the verified bulk destination. This cutover need not
   pretend to be a single atomic operation: no process may run during the gap.
5. Verify the complete tree once more through the original repository-facing
   symlink, confirm pinned-runtime user access and the target filesystem's
   ordinary same-directory exclusive-create/hard-link behavior using a separate
   disposable probe outside scientific receipts. Record destination, manifest
   digest, original path, counts/bytes, and completed cutover checks in an
   operational receipt. Verify frozen source/protocol hashes remain unchanged.
6. Retain the first-checkpoint local backup through initial resumption. Future
   output growth occurs on bulk, so keeping this small checkpoint backup does
   not incur the projected full-cohort growth on root. If later cleanup is
   necessary, remove only that exact byte-verified backup, with a guarded path
   and no symlink traversal; never remove the sole copy of evidence. Retain the
   bulk copy and manifests. Resume ordinary batches with the original command
   paths, unchanged claims and unchanged resource caps.

If bulk becomes unavailable, stop rather than recreating an empty repository
`results` directory. The frozen no-retry rules and terminal gates still apply.
Raw results now depend on external local storage; the symlink alone is not a
portable publication artifact. Future archival/publication should identify the
storage relocation and retain content hashes, as already required by the raw
evidence publication policy.
