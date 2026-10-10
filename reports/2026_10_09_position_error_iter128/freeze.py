"""Metadata/source freeze only. Does not open an IQ reader or evaluate a model."""

import json
from pathlib import Path

from run import digest, write_new

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    inventory = json.loads((HERE / "inventory.json").read_text())
    assert inventory["status"] == "metadata-complete" and inventory["total_observations"] == 35206
    paths = set(
        ROOT.glob("src/**/*.py")
    )  # Conservative runtime closure, including read-only storage.
    paths.update(HERE.glob("*.py"))
    paths.update(
        [HERE / "inventory.json", HERE / "PROTOCOL.md", ROOT / inventory["authority_path"]]
    )
    old = HERE.parent / "2026_10_09_position_error_iter125"
    paths.add(HERE / "resources.json")
    paths.add(old / "refine.py")
    paths.add(old / "protocol.json")
    prior = json.loads((old / "protocol.json").read_text())
    paths.update(ROOT / name for name in prior["source_sha256"])
    for member in inventory["members"]:
        path = ROOT / member["metadata_path"]
        if digest(path) != member["metadata_sha256"]:
            raise ValueError("metadata changed")
        paths.add(path)
    plan = {
        "schema": "iter128-original-iq-v1",
        "members": inventory["members"],
        "scorer": "original-python-conditioned-scorer-all-members",
        "data_root": "/srv/bulk/leo",
        "maximum_case_seconds": 1200,
        "maximum_visit_bytes": 32 * 1024**2,
        "maximum_chunk_bytes": 64 * 1024**2,
        "global_worker_limit": 2,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)},
    }
    write_new(HERE / "protocol.json", plan)


if __name__ == "__main__":
    main()
