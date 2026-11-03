# DS12: all adaptive recordings after DS11

DS12 contains **160 sealed recordings**, **353,291 retained IQ visits**, and
**42,394.92 seconds (11.7764 hours) of retained IQ per receiver**. It references
1,837,292,826,840 compressed bytes (1.837 TB) in the existing stores. One interrupted
partial capture is inventoried separately, with 113 files and 817,859,801 stored
bytes; it is not a sealed or evaluable recording.

| Property | Frozen value |
|---|---|
| Lower boundary: last admitted DS11 capture end | 2026-09-30 01:10:41.428265 UTC |
| Request cutoff | 2026-10-01 00:39:51 UTC |
| First admitted capture start | 2026-09-30 01:12:44.957105 UTC |
| Last sealed capture end | 2026-09-30 20:52:36.239369 UTC |
| Published recordings / sealed firmware archives | 84 / 76 |
| Complete bound production analysis by cutoff | 84 |
| Archives containing skipped visits without IQ | 10 |
| 2.5 / 5 / 7.5 / 10 MS/s recordings | 34 / 25 / 23 / 78 |
| Chronological groups of eight / remainder | 20 / 0 |

The authority is [local/manifest.json](local/manifest.json).
[local/source-inventory.json](local/source-inventory.json) records both source
inventories and the partial capture; [local/evaluation-units.json](local/evaluation-units.json)
provides full membership and the 84-recording analysis-ready view.
[local/SHA256SUMS](local/SHA256SUMS) seals membership, source metadata, analysis
responses, collection code and tests. Raw IQ remains referenced in place.

Unlike DS11, **analysis readiness does not gate DS12 membership**. All discovered
sealed adaptive recordings in the time window are included. Ten firmware archives
have skipped visits; their quality flags are preserved and only retained IQ
contributes to visit/sample/byte totals. Firmware archives use host begin/terminal
brackets, not an asserted qualified first-sample timestamp. They require publication
and analysis before use in the existing production analysis workflow. Membership
does not imply DS11-equivalent scientific admission.

## DS11 review

DS11's existing checksum seal and semantic verifier passed unchanged; all 17
DS11 admission tests passed. Its 87 recordings contain 192,676 visits and 6.4236
hours of valid IQ per receiver. Of its six excluded candidates, two occur after
its final admitted capture and are included in DS12. The other four occur within
DS11's earlier time span and remain outside this post-DS11 snapshot. DS12 is
disjoint from admitted DS11 by session ID and raw uncompressed IQ digest.

## Capture pause and missing coverage

The adaptive capture timer and active service were stopped at approximately
2026-10-01 00:40:02 UTC. The service has no running process; its retained systemd
result is `failed/signal` because it was interrupted. The timer is inactive but
still enabled, so this is a temporary pause and a reboot can reactivate it.
No capture was restarted. Existing publication and analysis services were left running.

[capture-stop-state.txt](capture-stop-state.txt) records the service state.
[capture-journal.log](capture-journal.log) preserves the capture history through
the stop, including 59 ENOSPC errors beginning at 2026-09-30 20:45:32 UTC. The
NVMe spool filesystem was 100% full at inspection. The last sealed recording
ended at 20:52:36 UTC, so the dataset does not imply continuous coverage to cutoff.
The interrupted `scan-fw-bd44c8b22412686d` partial began writing before cutoff
and has file timestamps through the stop; it has no sealed timing authority.

[publication-journal.log](publication-journal.log) records repeated publication
failures (`FileExistsError`) for the newest archives. DS12 preserves those archive
references without changing or repairing their payloads. This task did not delete,
move, republish, decompress or rehash raw IQ, nor collect new RF.

## Verification and limits

Eight DS12-owned tests pass, covering time boundaries, inclusion with pending
analysis, source deduplication and IQ binding, seal tampering, and skipped-IQ
accounting. Offline checksum and semantic verification passed. Archive chunk
presence and lengths were checked; metadata is copied into the snapshot, but raw
payload digests were not recalculated. Published metadata was validated through
the installed read-only storage port. All 84 published recordings had complete
bound GLRT/tracking products with tracking creation before cutoff; API responses
were observed during inventory, not in an atomic database snapshot.

This is a local metadata snapshot, not a raw-data backup or retention hold.
Source availability can change independently. Pose companions were not collected.

To verify offline from the repository root:

```sh
python3 reports/2026_10_01_ds12_post_ds11/mint.py verify
.venv/bin/python -m pytest reports/2026_10_01_ds12_post_ds11/test_mint.py -q
```
