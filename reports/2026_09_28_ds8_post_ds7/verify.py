"""Offline verification of the sealed DS8 membership and DS7 boundary."""

import hashlib
import json
from pathlib import Path


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main():
    folder = Path(__file__).parent
    parent_path = folder.parent / "2026_09_27_ds7_post_ds6/manifest.json"
    parent = json.loads(parent_path.read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert digest((folder / relative).read_bytes()) == "sha256:" + expected
    assert manifest["parent_manifest_sha256"] == digest(parent_path.read_bytes())
    rows = manifest["captures"]
    for key in ("session_id", "manifest_sha256"):
        assert len({r[key] for r in rows}) == len(rows)
        assert not {r[key] for r in rows} & {r[key] for r in parent["captures"]}
    assert len(rows) == manifest["counts"]["recordings"]
    for key in ("visits", "compressed_bytes"):
        assert sum(r[key] for r in rows) == manifest["counts"][key]
    for row in rows:
        assert not row["exclusion_reasons"]
        assert row["capture_start_earliest_utc_ns"] > manifest["after_parent_capture_end_utc_ns"]
        assert row["capture_end_utc_ns"] <= manifest["inventory_cutoff_utc_ns"]
        assert row["finalized_utc_ns"] <= manifest["inventory_cutoff_utc_ns"]
        payload = (folder / "pose" / (row["session_id"] + ".json")).read_bytes()
        assert digest(payload) == row["pose_file_sha256"]
        pose = json.loads(payload)
        assert pose["session_id"] == row["session_id"]
        assert pose["manifest_sha256"] == row["manifest_sha256"]
    print(f"Verified {len(rows)} DS8 recordings; DS7 + DS8 = {len(rows) + len(parent['captures'])}")


if __name__ == "__main__":
    main()
