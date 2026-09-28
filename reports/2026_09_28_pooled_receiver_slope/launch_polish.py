"""Bound the separately declared numerical completion for one pooled dataset."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
dataset = sys.argv[1]
for arm in ("control", "receiver_slope"):
    out = HERE / "polished" / dataset / arm
    out.mkdir(parents=True, exist_ok=False)
    source = HERE / "results" / dataset / arm / "fit-seal.json"
    bindings = json.loads(source.read_text())["sha256"] if source.exists() else {}
    for name, sha in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    paths = [Path(__file__), HERE / "polish.py", HERE / "POLISHING-PROTOCOL.md", HERE / "plan.json"]
    if source.exists():
        paths.append(source)
    for p in paths:
        bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(out / "resources.txt"),
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
        str(HERE / "polish.py"),
        dataset,
        arm,
    ]
    with (out / "launch.json").open("x") as f:
        json.dump({"command": command, "sha256": bindings}, f, indent=2)
    with (out / "terminal.log").open("x") as f:
        result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
    (out / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for name, sha in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    for p in out.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (out / "fit-seal.json").open("x") as f:
        json.dump({"stage": "before_geographic_scoring", "sha256": bindings}, f, indent=2)
    print(
        json.dumps({"dataset_id": dataset, "arm": arm, "exit_code": result.returncode}), flush=True
    )
