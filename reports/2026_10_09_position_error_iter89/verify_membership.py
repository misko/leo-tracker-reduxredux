"""Independent metadata-only checks of seal, coverage and frozen random assignment."""

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = read(HERE / "protocol.json")
    data = read(HERE / "membership.json")
    manifest = read(HERE / "local/manifest.json")
    seal = read(HERE / "local/seal.json")
    for name, expected in seal["files"].items():
        assert "sha256:" + sha(HERE / "local" / name) == expected, name
    for name, expected in plan["source_sha256"].items():
        assert sha(Path(name)) == expected, name
    assert data["manifest_sha256"] == sha(HERE / "local/manifest.json")
    rows = manifest["captures"]
    assert len(rows) == len(data["members"]) == manifest["counts"]["recordings"]
    assert sum(r["visits"] for r in rows) == manifest["counts"]["visits"]
    assert sum(r["compressed_bytes"] for r in rows) == manifest["counts"]["compressed_bytes"]
    lo, hi = [int(datetime.fromisoformat(t).timestamp()) * 10**9 for t in data["window"]]
    assert all(lo <= r["capture_start_utc_ns"] < hi and r["finalized_utc_ns"] <= hi for r in rows)
    lookup = {r["session_id"]: r for r in rows}
    groups = data["grouping"]["groups"]
    sessions = [sid for group in groups for sid in group["session_ids"]]
    assert len(sessions) == len(set(sessions)) == len(rows)
    assert set(sessions) == set(lookup)
    for group in groups:
        identities = sorted(
            sid
            + "|"
            + lookup[sid]["recording_manifest_sha256"]
            + "|"
            + lookup[sid]["uncompressed_sha256"]
            for sid in group["session_ids"]
        )
        expected = hashlib.sha256(
            (plan["random_seed"] + "\n" + "\n".join(identities)).encode()
        ).hexdigest()
        assert expected == group["random_rank"]
        if group["consumed"]:
            assert group["assignment"] == "development"
    eligible = sorted([g for g in groups if not g["consumed"]], key=lambda g: g["random_rank"])
    expected_reserve = max(1, math.floor(0.2 * len(eligible))) if len(eligible) >= 5 else 0
    assert data["grouping"]["reserve_count"] == expected_reserve
    assert [g["assignment"] for g in eligible] == ["closed_reserve"] * expected_reserve + [
        "development"
    ] * (len(eligible) - expected_reserve)
    assignment = {sid: g["assignment"] for g in groups for sid in g["session_ids"]}
    assert assignment["scan-fw-7ebf76971ca06c00"] == "development"
    receipt = dict(
        status="verified",
        membership=len(rows),
        seal_files=len(seal["files"]),
        frozen_closure_files=len(plan["source_sha256"]),
        groups=len(groups),
        group_counts=dict(Counter(g["assignment"] for g in groups)),
        recording_counts=dict(Counter(assignment.values())),
        manifest_sha256=data["manifest_sha256"],
        metadata_archive_sha256=sha(HERE / "metadata.tar.zst"),
        no_outcome_access=True,
    )
    (HERE / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
