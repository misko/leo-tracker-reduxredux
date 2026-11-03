# NVMe staging and permanent RAID publication

Capture was paused at the operator's request on 2026-10-23. Capture authority
generation 305 records both desired and observed state as `paused`. The
`leo-v052-adaptive.timer` timer is stopped and disabled. Do not resume RF collection
as part of archive maintenance.

## Cause and deployed flow

Fast capture wrote IQ to `/srv/postgres-nvme/fast-scan-recordings`, but had no
archive step. Analysis completion never retired those recordings. This accumulated
about 1.3 TiB. Legacy adaptive spools and analysis scratch accounted for another
approximately 486 GiB. Recent supported adaptive imports did reach RAID; an older
15 MS/s archive and partial/unsupported captures remained in the old spool.

The permanent fast recording root is now `/srv/bulk/leo/fast-scan-recordings`.
`leo-fast-scan-archive.timer` runs a bounded batch of up to eight stopped or failed
recordings, then waits 15 seconds. Its time budget stops it starting another
recording after five minutes; an individual copy may finish beyond that budget.
Running captures are excluded. Analysis discovers only published RAID recordings.
The original source aliases preserve historical manifest paths and input digests.

Each recording is copied into a hidden RAID staging directory, hashed while
reading the source, independently SHA-256 checked on RAID, and fsynced. A durable
receipt precedes destination publication and atomic source-path replacement.
Only the recorded original directory inode is then retired from NVMe. Interrupted
copies and publication can resume from receipts; failed verification retains the
original. The service runs as root to preserve mixed historical ownership and
setgid directory modes, with writable paths restricted to its two storage roots.
Writers and readers caching resolved source paths must be quiescent during a move.

Adaptive capture will use fresh temporary staging at
`/srv/postgres-nvme/leo-scanner-staging/v052-adaptive`. The existing adaptive transfer
timer publishes supported sealed captures to its existing RAID stores. It now
uses this fresh staging root, separating old unsupported evidence from production
transfer attempts. Native 10 MS/s capture settings remain in effect for a future
explicit resumption.

`leo-nvme-legacy-archive.service` preserves the entire quiescent old
`leo-scanner-spool` and `leo-analysis-scratch` directories under
`/srv/bulk/leo/nvme-archive`, including partial and failed evidence. It leaves
compatibility links at their old paths. This service resumes on failure and is
enabled for restart after a reboot. NVMe space from each legacy directory becomes
available only after that whole directory has verified and published.

The same one-time service also explicitly queues the older radio experiment and
activity-followup directories listed in its unit. Their newest files predate
2026-10-11, their entries are regular files/directories, and no open descriptors
or memory mappings from active processes were found in them. The fixed list
avoids sweeping unrelated future work into this historical migration.

Six historical incomplete fast folders were explicitly preserved with the same
archiver while capture was paused; their checkpoint contents were not rewritten.
The PostgreSQL data directory and unrelated firmware build workspace remain on
NVMe. Neither archiver traverses or mutates `/mnt/qnap01`.

## Deployment and validation

Archive runtime: `/opt/leo-shared-scans/raid-archive-dacd9022244ea6bb`.
Capture config: `/opt/leo-shared-scans/staging-to-raid-b7d03364d3fded75/capture-config.json`.
The repository contains the archiver, its CLI, component tests, and the installed
systemd templates and overrides. The immutable runtime has a file-hash deployment
manifest; deployed analysis continues using its existing scientific runtime.

The first real-disk pilot moved 533,619,371 bytes in 11.23 seconds. All 6,760
windows replayed through the historical input manifest after publication, with
their original manifest and IQ digests valid. The focused storage, CLI, and
scheduling checks passed: 35 tests, including failed-hash preservation, crash
recovery, source mutation refusal, empty directories, and setgid mode preservation.
The production backlog also successfully archived older mixed-owner directories.
The fresh adaptive transfer completed without failed or unsupported imports.

A native 10 MS/s recording, `fast8-auto-20261023-153658-32e602ef-1-lower`, then
published and retired 8,172,021,459 bytes in 92.18 seconds. All 6,772 windows replayed
through its existing immutable `fast-47f408a86f2066421da8e7c7f7339f2d` input manifest
in 25.88 seconds, preserving both input identity and scientific digests. All 355
archive-runtime files matched the deployment manifest. The fast scan reports and
automatic-status API endpoints both returned HTTP 200 after deployment.

## Operations

```sh
df -h /srv/postgres-nvme /srv/bulk
sudo journalctl -u leo-fast-scan-archive.service -u leo-nvme-legacy-archive.service -n 30 --no-pager
systemctl status leo-fast-scan-archive.timer leo-nvme-legacy-archive.service
systemctl is-active leo-v052-adaptive.timer
```

Receipts are in `.archive-control` beneath each permanent archive root. A
`copying` receipt reports verified files but does not mean NVMe has been freed;
`complete` means publication, aliasing, and source retirement finished. Do not
manually delete source or staging directories to accelerate a pending copy.

The separately diagnosed 10 MS/s analysis failures exceeded the 600-second GLRT
job budget. Archival is independent of that failure and does not claim to fix it.
