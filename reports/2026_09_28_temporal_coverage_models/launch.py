"""One sequential model worker per explicitly validated dataset panel."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "2026_09_28_temporal_coverage_inputs"
dataset, phase = sys.argv[1:]
plan = json.loads((INPUT / "plan.json").read_text())
captures = [r for r in plan["captures"] if r["dataset_id"] == dataset]
assert len(captures) == 8
paths = []
inputs = []
for row in captures:
    validation = INPUT / "validated" / (row["unit_id"] + ".json")
    seal = INPUT / "receipts" / row["unit_id"] / "validate/seal.json"
    assert (seal.parent / "exit-code.txt").read_text().strip() == "0"
    validated = json.loads(validation.read_text())
    assert validated["session_id"] == row["session_id"]
    inputs.extend(validated["request"]["inputs"])
    paths += [validation, seal]
    for artifact in validated["request"]["inputs"][0]["artifacts"]:
        path = Path(artifact["path"])
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        paths.append(path)
request = {"config": plan["config"], "inputs": inputs}
base = HERE / dataset
if phase == "fit":
    base.mkdir(exist_ok=False)
    (base / "request.json").write_text(json.dumps(request, indent=2) + "\n")
else:
    assert phase == "held"
    assert request == json.loads((base / "request.json").read_text())
paths += [
    base / "request.json",
    INPUT / "plan.json",
    HERE / "PROTOCOL.md",
    HERE / "launch.py",
    HERE / "run.py",
]
paths += [
    ROOT / "tools" / n
    for n in (
        "ds7_baseline_adapter.py",
        "ds7_fast_baseline_adapter.py",
        "ds789_covariance_position.py",
        "ds789_correlated_residual.py",
    )
]
for family in ("iid", "shared", "correlated"):
    parent = base / family
    if phase == "fit":
        stages = ["fit0", "fit1", "fit2"]
        chosen = None
    else:
        runs = []
        for stage in ("fit0", "fit1", "fit2"):
            folder = parent / stage
            code = int((folder / "exit-code.txt").read_text())
            runs.append(
                {
                    "stage": stage,
                    "exit_code": code,
                    "result": json.loads((folder / "result.json").read_text())
                    if code == 0
                    else None,
                }
            )
        eligible = [
            r["result"] for r in runs if r["result"] is not None and r["result"]["qualified"]
        ]
        chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        with (parent / "selection.json").open("x") as stream:
            json.dump(
                {"runs": runs, "selected": chosen, "qualified_starts": len(eligible)},
                stream,
                indent=2,
            )
        stages = ["held"] if chosen is not None else []
    for stage in stages:
        folder = parent / stage
        folder.mkdir(parents=True, exist_ok=False)
        bound = paths + ([parent / "selection.json"] if stage == "held" else [])
        bindings = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in bound
        }
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(folder / "resources.txt"),
            "timeout",
            "--kill-after=5s",
            "180s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python",
            str(HERE / "run.py"),
            dataset,
            family,
            stage,
        ]
        (folder / "launch.json").write_text(
            json.dumps({"command": command, "sha256": bindings}, indent=2)
        )
        print(dataset, family, stage, "starting", flush=True)
        with (folder / "terminal.log").open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
        for p in folder.iterdir():
            if p.is_file():
                bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
        print(dataset, family, stage, result.returncode, flush=True)
