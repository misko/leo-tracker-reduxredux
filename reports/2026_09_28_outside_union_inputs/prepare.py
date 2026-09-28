"""Materialize frozen coverage membership and archive reusable bank bytes."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
proposal_path = HERE.parent / "2026_09_28_union_panels/outside-union-proposal.json"
cross_path = HERE.parent / "2026_09_28_cross_dataset_position/plan.json"
full_path = HERE.parent / "2026_09_27_ds7_full88/solver/joint-v1/full88/request.json"
proposal = json.loads(proposal_path.read_text())
cross = json.loads(cross_path.read_text())
full = json.loads(full_path.read_text())
old_inputs = {i["session_id"]: i for i in full["inputs"]}
old_inputs.update({i["session_id"]: i for g in cross["groups"] for i in g["inputs"]})
bindings = {}


def bind(path):
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    bindings[str(path.relative_to(ROOT))] = sha
    return sha


for p in (proposal_path, cross_path, full_path, HERE / "PROTOCOL.md", HERE / "prepare.py"):
    bind(p)
rows, archive_map = [], []
for panel in proposal["groups"]:
    path = ROOT / panel["dataset_manifest_path"]
    assert "sha256:" + bind(path) == panel["dataset_sha256"]
    manifest = json.loads(path.read_text())
    by_id = {c["session_id"]: c for c in manifest["captures"]}
    assert len(panel["captures"]) == 15
    assert not set(panel["excluded_union_sessions"]).intersection(
        c["session_id"] for c in panel["captures"]
    )
    for index, selected in enumerate(panel["captures"], 1):
        capture = by_id[selected["session_id"]]
        assert capture["capture_start_utc_ns"] == selected["capture_start_utc_ns"]
        unit = f"{panel['dataset_id']}-V{index:02d}"
        row = {
            "unit_id": unit,
            "dataset_id": panel["dataset_id"],
            "session_id": capture["session_id"],
            "manifest_sha256": capture["manifest_sha256"],
            "sample_rate_hz": capture["sample_rate_hz"],
            "capture_start_utc_ns": capture["capture_start_utc_ns"],
            "ordinal": selected["ordinal"],
            "dataset_manifest_path": panel["dataset_manifest_path"],
            "dataset_sha256": panel["dataset_sha256"],
            "mint_analysis_evidence_sha256": capture.get("analysis_evidence_sha256"),
            "reused_input": None,
        }
        if row["session_id"] in old_inputs:
            old = json.loads(json.dumps(old_inputs[row["session_id"]]))
            assert old["manifest_sha256"] == row["manifest_sha256"]
            for artifact in old["artifacts"]:
                path = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                )
                if str(path.relative_to(ROOT)).startswith(".leo/"):
                    new = HERE / "exports" / unit / "banks" / path.name
                    new.parent.mkdir(parents=True, exist_ok=True)
                    assert not new.exists()
                    shutil.copyfile(path, new)
                    assert "sha256:" + bind(new) == artifact["sha256"]
                    archive_map.append(
                        {
                            "original_path": str(path.relative_to(ROOT)),
                            "archived_path": str(new.relative_to(ROOT)),
                            "sha256": artifact["sha256"],
                        }
                    )
                    artifact["path"] = str(new)
                else:
                    bind(path)
            row["reused_input"] = old
        rows.append(row)
assert len(rows) == len({r["session_id"] for r in rows}) == 45
with (HERE / "plan.json").open("x") as stream:
    json.dump({"config": cross["config"], "captures": rows}, stream, indent=2)
(HERE / "input-archive-map.json").write_text(json.dumps(archive_map, indent=2) + "\n")
(HERE / "input-seal.json").write_text(json.dumps({"sha256": bindings}, indent=2) + "\n")
print(
    json.dumps(
        {
            "records": len(rows),
            "reused": sum(r["reused_input"] is not None for r in rows),
            "new_exports": sum(r["reused_input"] is None for r in rows),
            "archived_files": len(archive_map),
        }
    )
)
