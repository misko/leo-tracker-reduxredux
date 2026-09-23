"""Export only the frozen validation cohort with four read-only workers."""

import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = Path("/tmp/leo-frozen-validation-cache")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = json.loads((HERE / "freeze.json").read_text())
    for relative, expected in frozen["sources"].items():
        assert digest(ROOT / relative) == expected
    exporter = ROOT / frozen["exporter"]
    ids = frozen["session_ids"]
    assert len(ids) == 124 and len(set(ids)) == 124
    manifest = json.loads((ROOT / frozen["cohort"]).read_text())["partitions"]
    assert ids == manifest["validation"]["session_ids"]
    for split in ("train", "test"):
        assert not set(ids).intersection(manifest[split]["session_ids"])
    CACHE.mkdir(exist_ok=True, mode=0o777)
    CACHE.chmod(0o777)

    def one(sid):
        folder = CACHE / sid
        if not folder.exists():
            process = subprocess.run(
                [
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    sys.executable,
                    str(exporter),
                    "--session-id",
                    sid,
                    "--output",
                    str(folder),
                ],
                capture_output=True,
                text=True,
            )
            if process.returncode:
                return {"session_id": sid, "failure": process.stderr[-1500:]}
        try:
            receipt_path, cache_path = folder / "cache_receipt.json", folder / "state_cache.npz"
            receipt = json.loads(receipt_path.read_text())
            assert receipt["session_id"] == sid
            assert receipt["bindings"]["export_tool"] == digest(exporter)
            cache_hash = digest(cache_path)
            assert receipt["bindings"]["state_cache"] == cache_hash
            return {"session_id": sid, "receipt": digest(receipt_path), "cache": cache_hash}
        except Exception as exc:
            return {"session_id": sid, "failure": repr(exc)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = []
        for row in pool.map(one, ids):
            rows.append(row)
            print(json.dumps(row), flush=True)
    output = {"rows": rows, "freeze": digest(HERE / "freeze.json"), "tool": digest(Path(__file__))}
    (HERE / "cache_receipts.json").write_text(json.dumps(output, indent=2) + "\n")
    if any("failure" in row for row in rows):
        raise RuntimeError("validation export incomplete; preserve all failures")


if __name__ == "__main__":
    main()
