"""Run and seal bounded diagnostics sequentially, without retries."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
for unit in plan["units"]:
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(mem["MemAvailable"].split()[0]) * 1024
    assert available >= 5 * 1024**3, "Insufficient headroom; no diagnostic launched"
    folder = HERE / "runs" / unit["unit_id"]
    folder.mkdir(parents=True, exist_ok=False)
    paths = [
        HERE / n
        for n in (
            "PROTOCOL.md",
            "prepare.py",
            "run.py",
            "launch.py",
            "plan.json",
            "input-seal.json",
        )
    ]
    paths += [
        ROOT / "tools" / n
        for n in (
            "ds789_covariance_position.py",
            "ds789_correlated_residual.py",
            "ds7_fast_baseline_adapter.py",
            "ds7_baseline_adapter.py",
        )
    ]
    paths.append(ROOT / unit["held_audit_path"])
    for item in unit["inputs"]:
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
        unit["unit_id"],
    ]
    (folder / "launch.json").write_text(
        json.dumps({"command": command, "sha256": bindings, "available_bytes": available}, indent=2)
    )
    with (folder / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for path in folder.iterdir():
        if path.is_file():
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(unit["unit_id"], result.returncode, flush=True)
