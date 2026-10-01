# Recovery of interrupted adaptive imports

The firmware importer previously reserved a RAID session directory before
copying IQ. A timeout left an unpublished directory. Every retry failed with
`FileExistsError`, and the same failed items consumed the bounded transfer
batch. A failed batch also exited with status zero. On October 1 the NVMe
held about 1.7 TB in 172 sealed firmware archives, plus partial/older spools.

The storage port now preserves an abandoned destination under a hidden
`.incomplete-<session>-<unique-id>` name and allows a fresh import. Recovery
locks the destination directory and refuses active writers, symlinked paths,
and any destination with a published manifest, even an invalid manifest.
Partial destinations remain on RAID as evidence; this does not delete raw
source captures. Sealed source IQ still passes compressed and raw digest checks
during import. A previously published same-ID recording must match the source
receipt and aggregate IQ digest, and its chunks must be readable, before the
source can be retired on retry.

An internal `.adaptive-spool-attempts.v1.json` checkpoint records attempts before
workers start. Less-attempted items take priority, so failed or killed jobs do
not monopolize the queue. The existing success ledger contract is unchanged.
A success recorded before interrupted source retirement is reverified on the
next run. Import failures now produce exit status 1 as well as JSON details.

The recovery service drop-in selects an immutable source-tree-addressed build
through `PYTHONPATH`; Python module paths must be checked at deployment. Each
run processes at most two firmware archives concurrently. The recovery timer
runs 60 seconds after a batch finishes to drain the existing backlog. The
30-minute per-import timeout remains; the unit has a 35-minute outer bound.
This timer transfers existing recordings and does not authorize RF acquisition.

Unsealed capture partials and archives unsupported by the scientific contracts
remain preserved and require separate review. Repeated failures remain visible;
this repair does not claim to resolve every throughput or input-data problem.
Existing dataset manifests are not changed. Dataset references to an NVMe
archive may need resolving to the same session in the published RAID store
after normal source retirement; snapshots are not raw-payload retention holds.

Validation: 130 tests passed across firmware import, transfer scheduling,
adaptive storage, queued storage, host-adaptive storage and history. The tests
cover an abandoned destination followed by successful import, preservation of
partial bytes, rejection of live/published/symlinked destinations, mismatched
same-ID sources, retry fairness, interrupted retirement and nonzero failure exit.

## Production validation

The bounded `leo-spool-recovery-canary.service` ran from 01:43:25 to 01:45:00 UTC
on October 1 and successfully published `scan-fw-e548a92bfe29a8bc` (2,216 visits).
Its aggregate raw-IQ digest matches DS12's frozen archive metadata. The partial
RAID directory was retained under a `.incomplete-...` name. The source was retired
only after publication and ledger checkpoint; NVMe available space rose from
2,576,326,656 to 6,295,003,136 bytes (about 3.7 GB recovered).

The recovery timer was resumed with two-item batches. The next blocked recording
was observed actively copying chunks. The backlog is not yet fully drained;
unsealed partials and unsupported captures remain outside automatic recovery.

The operator's earlier RF restart request is configured with equal 2.5/10 MS/s
selection and 120/120 ms dwells, plus a tested free-space guard. At 01:48:07 UTC
the first attempt deferred before RF access: 6,295,003,136 bytes available versus
26,147,483,648 required for the selected 10 MS/s rate. The capture timer is stopped
automatically at 02:11:07 UTC, with a hard timer/service stop at 02:18:07 UTC.
The capture timer is still disabled for boot activation. Fifteen capture-policy
and preflight tests passed; no change of rate is made merely to fit free space.
