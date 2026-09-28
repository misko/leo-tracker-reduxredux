"""Freeze complete manifest membership and archive reusable cached bank bytes."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
bindings = {}


def bind(path):
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    name = str(path.relative_to(ROOT))
    assert name not in bindings or bindings[name] == value
    bindings[name] = value
    return value


def read(path):
    bind(path)
    return json.loads(path.read_text())


full = read(HERE.parent / "2026_09_27_ds7_full88/solver/joint-v1/full88/request.json")
combined = read(HERE.parent / "2026_09_28_combined30/plan.json")
assert full["config"] == combined["config"]
known = {i["session_id"]: i for i in full["inputs"]}
known.update({i["session_id"]: i for g in combined["models"][0]["groups"] for i in g["inputs"]})
rows, archives = [], []
for ds, folder, count in (
    ("DS7", "2026_09_27_ds7_post_ds6", 88),
    ("DS8", "2026_09_28_ds8_post_ds7", 65),
    ("DS9", "2026_09_28_ds9_post_ds8", 105),
):
    path = HERE.parent / folder / "manifest.json"
    manifest = read(path)
    captures = sorted(
        manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
    )
    assert len(captures) == count
    for index, capture in enumerate(captures, 1):
        sid = capture["session_id"]
        unit = f"{ds}-F{index:03d}"
        pose = path.parent / "pose" / (sid + ".json")
        assert "sha256:" + bind(pose) == capture["pose_file_sha256"]
        row = {
            "unit_id": unit,
            "dataset_id": ds,
            "session_id": sid,
            "manifest_sha256": capture["manifest_sha256"],
            "sample_rate_hz": capture["sample_rate_hz"],
            "capture_start_utc_ns": capture["capture_start_utc_ns"],
            "ordinal": index,
            "dataset_manifest_path": str(path.relative_to(ROOT)),
            "dataset_sha256": "sha256:" + bindings[str(path.relative_to(ROOT))],
            "pose_path": str(pose.relative_to(ROOT)),
            "pose_sha256": capture["pose_file_sha256"],
            "mint_analysis_evidence_sha256": capture.get("analysis_evidence_sha256"),
            "reused_input": None,
        }
        if sid in known:
            item = json.loads(json.dumps(known[sid]))
            assert item["manifest_sha256"] == row["manifest_sha256"]
            for artifact in item["artifacts"]:
                source = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
                    == artifact["sha256"]
                )
                if str(source.relative_to(ROOT)).startswith(".leo/"):
                    dest = HERE / "exports" / unit / "banks" / source.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    assert not dest.exists()
                    shutil.copyfile(source, dest)
                    assert "sha256:" + bind(dest) == artifact["sha256"]
                    archives.append(
                        {
                            "original_path": str(source.relative_to(ROOT)),
                            "archived_path": str(dest.relative_to(ROOT)),
                            "sha256": artifact["sha256"],
                        }
                    )
                    artifact["path"] = str(dest)
                else:
                    bind(source)
            row["reused_input"] = item
        rows.append(row)
assert len(rows) == len({r["session_id"] for r in rows}) == 258
for name in ("prepare.py", "PROTOCOL.md"):
    bind(HERE / name)
with (HERE / "plan.json").open("x") as stream:
    json.dump({"config": combined["config"], "captures": rows}, stream, indent=2)
(HERE / "input-archive-map.json").write_text(json.dumps(archives, indent=2) + "\n")
(HERE / "input-seal.json").write_text(json.dumps({"sha256": bindings}, indent=2) + "\n")
print(
    json.dumps(
        {
            "records": len(rows),
            "reused": sum(r["reused_input"] is not None for r in rows),
            "new_exports": sum(r["reused_input"] is None for r in rows),
            "archived": len(archives),
        }
    )
)
