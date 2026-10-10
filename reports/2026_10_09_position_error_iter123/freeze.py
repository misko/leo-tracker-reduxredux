"""Explicit metadata-only preparation; parent must authorize actual freeze."""

import hashlib
import json
from pathlib import Path

from retained_adapter import admitted_original

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEARCH = ROOT / "reports/2026_10_09_position_error_iter116"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    parent = json.loads((SEARCH / "protocol.json").read_text())
    terminal_path = SEARCH / "results/DS18-022/result.json"
    terminal = json.loads(terminal_path.read_text())
    if terminal["status"] != "complete" or terminal["point_failure_count"] != 0:
        raise ValueError("search not sealed without exceptions")
    sources = dict(parent["source_sha256"])
    inputs = dict(parent["input_sha256"])
    for path in (SEARCH / "protocol.json", terminal_path):
        inputs[str(path.relative_to(ROOT))] = sha(path)
    imported = json.loads((SEARCH / "coarse-import.json").read_text())
    seeds = {tuple(r["point"]): r["receipt"]["result"]["bootstrap"] for r in imported["records"]}
    wanted = {
        tuple((r["east_km"], r["north_km"]))
        for policy in ("native", "fixed")
        for r in terminal["searches"][f"fitted-c:{policy}"]["regions"]
    }
    fits = {}
    for path in sorted((terminal_path.parent / "points").glob("*.json")):
        if path.name.endswith(".claim.json"):
            continue
        row = json.loads(path.read_text())
        key = row["key"]
        point = tuple(key[1]) if key[0] == "bootstrap" else tuple(key[1:3])
        if point not in wanted:
            continue
        if row["status"] != "complete" or row["protocol_sha256"] != terminal["protocol_sha256"]:
            raise ValueError("foreign/incomplete retained point source")
        if key[0] == "bootstrap":
            if point in seeds and seeds[point] != row["value"]:
                raise ValueError("bootstrap conflict")
            seeds[point] = row["value"]
        elif key[0] == "point" and key[3] == "fitted-c":
            value = row["value"]
            if abs(value["fit"]["objective"] - value["scores"]["native"]["objective"]) > 1e-6:
                raise ValueError("native objective mismatch")
            fits[point] = value["fit"]
        else:
            continue
        inputs[str(path.relative_to(ROOT))] = sha(path)
    branches = {}
    for policy in ("native", "fixed"):
        regions = terminal["searches"][f"fitted-c:{policy}"]["regions"]
        branches[policy] = [
            dict(
                point=[r["east_km"], r["north_km"]],
                discovery_score=r["score"],
                spacing_km=r["spacing_km"],
                original=admitted_original(
                    [r["east_km"], r["north_km"]],
                    seeds[(r["east_km"], r["north_km"])],
                    fits[(r["east_km"], r["north_km"])],
                    len(imported["bank_numbers"]),
                ),
            )
            for r in regions
        ]
    for path in list(HERE.glob("*.py")) + [HERE / "README.md"]:
        if not path.name.startswith("test_"):
            sources[str(path.relative_to(ROOT))] = sha(path)
    for group in (sources, inputs):
        for name, expected in group.items():
            if sha(ROOT / name) != expected:
                raise ValueError("closure changed: " + name)
    return dict(
        binding=parent["binding"],
        identity=parent["identity"],
        branches=branches,
        source_sha256=sources,
        input_sha256=inputs,
        search_protocol_digest=terminal["protocol_sha256"],
        policy=dict(
            discovery_arm="fitted-c",
            regions=3,
            separation_km=12.5,
            symmetric_direct_calibration=True,
            coarse_recovery="off",
            final_arms=["zero-c", "fitted-c"],
            local_radius_km=25,
            maximum_slices_per_branch=6,
            slice_seconds=500,
            maximum_workers=2,
            threads=1,
            fallback="none",
            qualification_rounds=2,
            qualification_evaluations=100,
            association_seconds=60,
            final_seconds=20,
            final_iterations=600,
            joint_stage_seconds=90,
            joint_stage_iterations=600,
        ),
        scope="consumed conditional matched research control; zero discovery deferred",
    )


if __name__ == "__main__":
    value = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
