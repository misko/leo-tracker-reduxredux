"""Three short read-only diagnostic workers with bound numerical inputs."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CROSS = HERE.parent / "2026_09_28_cross_dataset_position"
plan = json.loads((CROSS / "plan.json").read_text())
for dataset in ("DS7", "DS8", "DS9"):
    group = next(g for g in plan["groups"] if g["dataset_id"] == dataset)
    target = HERE / dataset
    target.mkdir(exist_ok=False)
    paths = [HERE / n for n in ("PROTOCOL.md", "run.py", "launch.py")]
    paths += [
        CROSS / "plan.json",
        CROSS / "all24/source-selection.json",
        CROSS / "all24/source_held/result.json",
        CROSS / f"exclude_{dataset}/target-selection.json",
        CROSS / f"exclude_{dataset}/target_held/result.json",
        ROOT / group["source_point_path"],
    ]
    paths += [
        ROOT / "tools" / n
        for n in (
            "ds789_transfer_audit.py",
            "ds7_fast_baseline_adapter.py",
            "ds7_baseline_adapter.py",
            "ds7_residual_audit.py",
        )
    ]
    paths += [ROOT / "tests/research/test_ds789_transfer_audit.py"]
    for item in group["inputs"]:
        for artifact in item["artifacts"]:
            path = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(path)
    bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(target / "resources.txt"),
        "timeout",
        "--kill-after=5s",
        "90s",
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
    ]
    with (target / "launch.json").open("x") as stream:
        json.dump({"command": command, "sha256": bindings}, stream, indent=2)
    with (target / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (target / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for p in target.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (target / "seal.json").open("x") as stream:
        json.dump({"sha256": bindings}, stream, indent=2)
    print(dataset, result.returncode, flush=True)
