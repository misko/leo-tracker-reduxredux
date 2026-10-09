# Iteration89: prepared metadata-only newer-data inventory

The UTC clock cutoff was frozen at **2026-10-09 15:46:15 UTC before any live
inventory**. Proposed window: `[2026-10-09T02:02:21Z,2026-10-09T15:46:15Z)`.
Identity: POST18-NEWER-20261009, parent POST18-RESERVE. No DS16/17/18 renaming.
The eleven existing reserved outcomes remain closed.

This preparation reads only previously sealed parent metadata, mint source and
runtime selectors/source files. It inventories no new recording, opens no
localization outcome and launches no analysis or RF acquisition. Parent authority,
DS18 SHA256, source/runtime closure, grouping seed and exposure policy are frozen
in [protocol.json](protocol.json). The parent must commit/publish that protocol
before authorizing the read-only mint below. The unchanged metadata mint uses
public read-only `AdaptiveHopIqStore` ports and firmware interchange manifests.

All sealed whole recordings in the window qualify, including unpublished archives;
no analysis-readiness or quality filter. Exclusions and unsealed partials stay
explicit. No retention hold is created. Both receivers remain together. Metadata
grouping and randomized reserve assignment use the rule in protocol.json and the
[newer-data plan](../2026_10_09_position_error_iter88/NEWER_DATA_PLAN.md).
The already inspected live diagnostic scan-fw-7ebf76971ca06c00 is consumed and its
group is development if present. Exact identity exposure searches return only
filenames/tokens, not localization lines. No registry match is not unseen proof.

The commands are prepared and **not yet executed**:

```bash
sudo -n -u leo env PYTHONPATH=/opt/leo-b7/aa296fd94-r1/api/src:/opt/leo-v060-adaptive/a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b/src \
  /opt/leo-tracker/current-api/.venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/mint.py mint \
  --dataset-id POST18-NEWER-20261009 --parent-dataset POST18-RESERVE \
  --parent /home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local \
  --start 2026-10-09T02:02:21+00:00 --end 2026-10-09T15:46:15+00:00 \
  --output /home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter89/local
```

Verification repeats the same command with `verify` in place of `mint`. A new
nonexistent local directory must be writable by service account leo through the
report parent. Freeze verification hashes again immediately before invocation;
if they differ, stop and report rather than silently changing the source. Record
inventory begin/end, seal verification, full membership, all exclusions/partials,
disjointness by session/IQ digest and exposure limitations. Development and reserve
assignments are metadata-only and committed before any new outcome access.

Future candidate evaluation retains every assigned member, including input and
fit failures, with matched c0/fitted-c comparisons and separate frequency/position
effects. Reference coordinates remain evaluation-only. No existing reserve
outcome is opened by this inventory.
