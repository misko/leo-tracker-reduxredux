"""Freeze existing-panel unions and source-only starts before model execution."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
from ds789_pool_plan import layout  # noqa: E402

bindings = {}


def read(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


old = read(REPORTS / "2026_09_28_cross_dataset_position/plan.json")
coverage = read(REPORTS / "2026_09_28_temporal_coverage_inputs/plan.json")
models = []
membership = {}
for decay, family in ((0, "shared"), (10, "correlated")):
    groups = []
    for historical in old["groups"]:
        ds = historical["dataset_id"]
        broad_root = REPORTS / "2026_09_28_temporal_coverage_models" / ds
        broad = read(broad_root / "request.json")
        assert broad["config"] == old["config"]
        broad_selection_path = broad_root / family / "selection.json"
        broad_fit = read(broad_selection_path)["selected"]
        historical_fit = read(
            REPORTS / "2026_09_28_covariance_position" / ds / f"t{decay}/selection.json"
        )["selected"]
        assert broad_fit["qualified"] and historical_fit["qualified"]
        historical_inputs = {i["session_id"]: i for i in historical["inputs"]}
        broad_inputs = {i["session_id"]: i for i in broad["inputs"]}
        assert len(historical_inputs) == len(broad_inputs) == 8
        assert len(historical_inputs.keys() & broad_inputs.keys()) == 1
        for session in historical_inputs.keys() & broad_inputs.keys():

            def artifacts(item):
                return sorted((a["kind"], a["sha256"]) for a in item["artifacts"])

            assert artifacts(historical_inputs[session]) == artifacts(broad_inputs[session])
        by_session = {**historical_inputs, **broad_inputs}
        authority = next(c for c in coverage["captures"] if c["dataset_id"] == ds)
        manifest_path = ROOT / authority["dataset_manifest_path"]
        manifest = read(manifest_path)
        assert (
            "sha256:" + bindings[str(manifest_path.relative_to(ROOT))]
            == authority["dataset_sha256"]
        )
        ordered = sorted(
            manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
        )
        captures = [c for c in ordered if c["session_id"] in by_session]
        sessions = [c["session_id"] for c in captures]
        assert len(sessions) == len(by_session) == 15
        times = dict(zip(historical["session_ids"], historical_fit["x"][2:], strict=True))
        times.update(zip(broad_inputs, broad_fit["x"][2:], strict=True))
        rows = []
        for capture in captures:
            item = by_session[capture["session_id"]]
            assert item["manifest_sha256"] == capture["manifest_sha256"]
            for artifact in item["artifacts"]:
                path = Path(artifact["path"])
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                assert "sha256:" + sha == artifact["sha256"]
                bindings[str(path.relative_to(ROOT))] = sha
            pose_path = manifest_path.parent / "pose" / (capture["session_id"] + ".json")
            pose_sha = hashlib.sha256(pose_path.read_bytes()).hexdigest()
            assert "sha256:" + pose_sha == capture["pose_file_sha256"]
            rows.append(
                {
                    "session_id": capture["session_id"],
                    "capture_start_utc_ns": capture["capture_start_utc_ns"],
                    "sample_rate_hz": capture["sample_rate_hz"],
                    "ordinal": ordered.index(capture) + 1,
                    "historical": capture["session_id"] in historical_inputs,
                    "broad": capture["session_id"] in broad_inputs,
                    "pose_path": str(pose_path.relative_to(ROOT)),
                    "pose_sha256": pose_sha,
                }
            )
        if ds in membership:
            assert membership[ds] == rows
        membership[ds] = rows
        groups.append(
            {
                "dataset_id": ds,
                "session_ids": sessions,
                "inputs": [by_session[s] for s in sessions],
                "point": broad_fit["x"][:2] + [times[s] for s in sessions],
                "historical_position": historical_fit["x"][:2],
                "covariance_selection_path": str(broad_selection_path.relative_to(ROOT)),
                "manifest_path": str(manifest_path.relative_to(ROOT)),
            }
        )
    units = []
    for group in groups:
        units.append(
            {
                "unit_id": "single_" + group["dataset_id"],
                "excluded_dataset": None,
                "source_datasets": [group["dataset_id"]],
                "session_ids": group["session_ids"],
                "starts": [
                    {"source_dataset": label, "x": position + group["point"][2:]}
                    for label, position in (
                        ("broad", group["point"][:2]),
                        ("historical", group["historical_position"]),
                        ("origin", [0, 0]),
                    )
                ],
            }
        )
    units += [
        {
            "unit_id": "all45" if omitted is None else "exclude_" + omitted,
            "excluded_dataset": omitted,
            **layout(groups, omitted),
        }
        for omitted in (None, "DS7", "DS8", "DS9")
    ]
    models.append({"decay_s": decay, "groups": groups, "units": units})
for path in (HERE / "prepare.py", HERE / "PROTOCOL.md", ROOT / "tools/ds789_pool_plan.py"):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(
        {"models": models, "config": old["config"], "membership": membership}, stream, indent=2
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
