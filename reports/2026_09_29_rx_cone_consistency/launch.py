"""Execute immutable, sequential cone audits with resource and input receipts."""

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
    assert available >= 5 * 1024**3
    folder = HERE / "runs" / unit["unit_id"]
    folder.mkdir(parents=True, exist_ok=False)
    paths = [
        HERE / n
        for n in (
            "PROTOCOL.md",
            "prepare.py",
            "cones.py",
            "run.py",
            "launch.py",
            "plan.json",
            "input-seal.json",
        )
    ]
    paths += [
        ROOT / "tools" / n for n in ("ds7_baseline_adapter.py", "ds7_fast_baseline_adapter.py")
    ]
    paths.append(ROOT / unit["baseline_audit"])
    for item in unit["group"]["inputs"]:
        for artifact in item["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
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
        unit["unit_id"],
    ]
    (folder / "launch.json").write_text(
        json.dumps({"command": command, "available_bytes": available, "sha256": bindings}, indent=2)
    )
    with (folder / "terminal.log").open("x") as f:
        result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for p in folder.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(unit["unit_id"], result.returncode, flush=True)
