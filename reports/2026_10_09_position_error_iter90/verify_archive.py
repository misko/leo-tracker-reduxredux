"""Archive and independently verify all frozen diagnostic receipts; no new fits."""

import hashlib
import json
import subprocess
import tarfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_bytes())
    digest = sha(protocol)
    for name, expected in plan["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    expected = {b["member"]["inventory_label"]: b["member"] for b in plan["members"]}
    paths = {p.stem: p for p in (HERE / "results").glob("*.json")}
    assert len(expected) == 148 and set(paths) == set(expected)
    statuses, deltas, raw_hashes = Counter(), [], {}
    for label, path in paths.items():
        receipt = json.loads(path.read_bytes())
        assert receipt["protocol_sha256"] == digest and receipt["member"] == expected[label]
        statuses[receipt["status"]] += 1
        if receipt["status"] == "complete":
            for arm in ("fitted-c", "zero-c"):
                delta = receipt["objective_checks"][arm]["delta"]
                assert abs(delta) <= 1e-6
                deltas.append(delta)
        raw_hashes["results/" + path.name] = sha(path)
    archive = HERE / "receipts.tar.zst"
    subprocess.run(["tar", "--zstd", "-cf", str(archive), "-C", str(HERE), "results"], check=True)
    stream = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    verified = {}
    try:
        with tarfile.open(fileobj=stream.stdout, mode="r|") as tar:
            for entry in tar:
                if not entry.isfile():
                    continue
                assert entry.name in raw_hashes
                data = tar.extractfile(entry).read()
                verified[entry.name] = hashlib.sha256(data).hexdigest()
    finally:
        stream.stdout.close()
    assert stream.wait() == 0
    assert verified == raw_hashes
    receipt = dict(
        protocol_sha256=digest,
        frozen_closure_files_verified=len(plan["source_sha256"]),
        members=148,
        statuses=dict(statuses),
        objectives_checked=len(deltas),
        exact_zero_objective_deltas=sum(delta == 0 for delta in deltas),
        maximum_absolute_objective_delta=max(map(abs, deltas), default=None),
        archive_sha256=sha(archive),
        archive_bytes=archive.stat().st_size,
        archived_receipt_sha256=raw_hashes,
        no_new_position_fit=True,
        reserves_unopened=True,
    )
    (HERE / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in receipt.items() if k != "archived_receipt_sha256"}, indent=2)
    )


if __name__ == "__main__":
    main()
