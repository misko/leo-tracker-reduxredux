"""Seal separate bounded fixed-point step studies; never overwrite old audits."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
for unit in plan["units"]:
    old = HERE / "runs" / unit["unit_id"]
    assert (old / "held/seal.json").exists()
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(mem["MemAvailable"].split()[0]) * 1024
    assert available >= 5 * 1024**3
    folder = HERE / "gradient-review" / unit["unit_id"]
    folder.mkdir(parents=True, exist_ok=False)
    bindings = json.loads((old / "held/seal.json").read_text())["sha256"]
    for name, h in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    for path in [HERE / n for n in ("GRADIENT-REVIEW.md", "review_run.py", "review_launch.py")] + [
        old / "held/seal.json"
    ]:
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
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
        str(HERE / "review_run.py"),
        unit["unit_id"],
    ]
    (folder / "launch.json").write_text(
        json.dumps({"command": command, "available_bytes": available, "sha256": bindings}, indent=2)
    )
    with (folder / "terminal.log").open("x") as stream:
        r = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (folder / "exit-code.txt").write_text(str(r.returncode) + "\n")
    for path in folder.iterdir():
        if path.is_file():
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(unit["unit_id"], "review", r.returncode, flush=True)
