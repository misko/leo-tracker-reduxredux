# Exact evaluation receipt archive

Run packaging **after** the final combined RF ledger and its passing independent audit are sealed. The helper requires joined combined/component workers, terminal worker rows, exact component hashes, and a passing `review/combined_audit.json` bound to the same `evaluation/combined_results.json` bytes. Any started or completed later wave missing from that combined ledger causes refusal. Terminal deadline fallbacks are preserved finished decisions; checkpoint files can legitimately retain their earlier `running` snapshots.

```text
/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_generalized_corrections/publish_receipts.py
```

The outputs are [evaluation_receipts.tar.gz](evaluation_receipts.tar.gz) and [evaluation_receipts.manifest.json](evaluation_receipts.manifest.json). Existing outputs are never overwritten. Originals are never removed or rewritten, and packaging does not stage files.

## Membership

- Exact original, wave2/wave3 and combined result ledgers, for the chronological components in the final combined packet.
- Evaluation input roster, execution receipts, eligibility plans, preflight and wave-seal JSON; independent review JSON; applicable report-root JSON receipts and bindings.
- All files beneath each component's `cases/` tree, including raw numerical cells, checkpoints, partial JSON temporary files and arbitrary attempt-marker files, except runtime payloads listed below.
- Every case directory, including empty engine/context/cache directories. These preserve existence-based start evidence even when their runtime payload is excluded.

Runtime context/cache directory payloads, pickle/NumPy cache files, logs and Python bytecode are excluded. Their original path, type, size and SHA256 remain in `original_case_tree` in the external manifest. `result.json`, deadline checkpoints, `*.rf.json`, `*.checkpoint.json` and `*.json.tmp*` files are protected receipts and remain archived even inside a runtime directory. The manifest lists every archived file's report-relative path, size and SHA256 and every archived directory.

Small source files and protocol/configuration files publish directly. The explicit configuration exclusions are `protocol.json`, `execution_protocol.json`, `coverage_protocol.json`, `prelaunch_amendment.json` and `evaluation/proposed_configuration.json`; existing ones are separately hash-listed in the manifest. The archive does not recursively package scientific figures, source, or runtime contexts outside the evaluation case trees.

Gzip has an empty filename and timestamp zero. Tar members are sorted, use timestamp zero, uid/gid zero, empty owner/group names and normalized permissions. The manifest records the archive's size and SHA256. Neither original timestamps nor wall-clock packaging time affect archive bytes.

## Verify and restore

The helper checks every archived byte against its manifest before publishing, then rechecks original receipt hashes and the full case-tree inventory for concurrent changes. Tests use synthetic temporary reports and do not package the live evaluation.

```text
PYTHONPATH=reports/2026_11_02_generalized_corrections /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python -m pytest -q reports/2026_11_02_generalized_corrections/test_publish_receipts.py
```

To verify a downloaded archive, load the manifest and call `publish_receipts.verify_archive(archive_path, manifest)`; compare the archive SHA256 to `manifest["archive"]["sha256"]` as well. `files` inventories all regular tar members; `directories` inventories all directory members. The manifest remains outside the tar to avoid a self-hash cycle.

Unpack **into the report root**, alongside the directly published source/config files. Tar names start with paths such as `evaluation/cases/…`, `evaluation/wave2/cases/…`, and `review/…`, so extraction recreates the original audit paths without rewriting scientific receipts. The original numerical corpus and causal TLE inputs remain external read-only dependencies; this archive preserves evaluation evidence rather than redistributing that corpus. Rerun the combined audit with the restored report and those inputs available.
