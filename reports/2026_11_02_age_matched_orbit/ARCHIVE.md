# Exact evaluation receipt archive

[evaluation_receipts.tar.gz](evaluation_receipts.tar.gz) preserves the exact result ledger and case evidence. Its external [manifest](evaluation_receipts.manifest.json) records the archive SHA256 and every member's report-relative path, size and SHA256. Originals remain intact; packaging does not stage or commit anything.

The archive contains `evaluation/results.json`, all case result/raw/checkpoint/temporary-marker files, evaluation JSON metadata and independent-review JSON receipts. Runtime context/cache, log and bytecode payloads are excluded. Their paths, sizes and hashes remain in the original case-tree inventory; empty directory markers remain archived. Protected `*.rf.json`, `*.checkpoint.json`, result/deadline receipts and JSON temporary markers are retained even inside a runtime directory. Small source, protocol and scientific-report files publish directly.

Packaging requires joined workers, terminal rows/cells, the matching sealed completion receipt, and a passing final audit bound to the exact result/protocol/roster hashes. It checks all 402 frozen scientific-source hashes. Existing publication outputs are never overwritten. Tar members are sorted with mtime/uid/gid zero, empty owner/group names and safe relative paths; gzip has timestamp zero and no embedded filename.

Every member is byte-verified and then extracted into a temporary directory for a restore/hash check before publication. Original receipt trees and frozen source hashes are checked again afterward. The temporary restore never touches the original case tree.

Reproduce from the worktree root:

```text
/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_age_matched_orbit/publish_receipts.py
```

Verify the published archive independently, including a fresh temporary extraction:

```text
/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_age_matched_orbit/publish_receipts.py --verify
```

To restore for an audit, extract **into this report root**, alongside the directly published source and protocol. Member names begin `evaluation/…` or `review/…`, recreating the original report-relative audit paths. The external numerical corpus, previous sealed report and causal TLE history remain read-only dependencies; they are not redistributed here. Restoring those external dependencies is unnecessary for the archive's own hash/restore verification.

Synthetic tests cover exact byte preservation, deterministic compression/metadata, safe relative paths and directory markers, protected receipt files, exclusions, restore corruption, refusal of unfinished/stale seals and scientific changes, and no overwriting originals.
