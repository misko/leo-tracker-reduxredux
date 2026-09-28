"""One bounded unit; run at most two such launchers concurrently."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
unit_id = sys.argv[1]
plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == unit_id)
folder = HERE / unit_id
folder.mkdir(exist_ok=False)
bindings = dict(json.loads((HERE / "input-seal.json").read_text())["sha256"])
paths = [HERE / n for n in ("plan.json", "input-seal.json", "PROTOCOL.md", "run.py", "launch.py")]
paths += [
    ROOT / "tools" / n
    for n in (
        "ds7_baseline_adapter.py",
        "ds7_fast_baseline_adapter.py",
        "ds7_pooled_receiver_slope.py",
        "ds7_shared_slope_shadow.py",
        "ds7_slope_identifiability.py",
        "ds789_pool_plan.py",
    )
]
paths += [ROOT / "tests/research/test_ds789_pool_plan.py"]
for p in paths:
    bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha


def execute(stage, start_id, limit):
    out = folder / stage
    if stage.endswith("fit"):
        out = out / start_id
    out.mkdir(parents=True, exist_ok=False)
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(out / "resources.txt"),
        "timeout",
        "--kill-after=5s",
        f"{limit}s",
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
        unit_id,
        stage,
        start_id,
    ]
    launch_bindings = dict(bindings)
    for p in folder.glob("*-selection.json"):
        launch_bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (out / "launch.json").open("x") as stream:
        json.dump({"command": command, "sha256": launch_bindings}, stream, indent=2)
    with (out / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (out / "exit-code.txt").write_text(str(result.returncode) + "\n")
    terminal = dict(launch_bindings)
    for p in out.iterdir():
        if p.is_file():
            terminal[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (out / "seal.json").open("x") as stream:
        json.dump({"stage": "before_geographic_scoring", "sha256": terminal}, stream, indent=2)
    print(unit_id, stage, start_id, result.returncode, flush=True)
    p = out / "result.json"
    return json.loads(p.read_text()) if result.returncode == 0 and p.exists() else None


def selection(stage, runs):
    successful = [r for r in runs if r is not None and r["success"]]
    selected = max(successful, key=lambda r: r["training_log_score"]) if successful else None
    with (folder / f"{stage}-selection.json").open("x") as stream:
        json.dump({"selected": selected, "runs": runs}, stream, indent=2)
    return selected


runs = [execute("source_fit", s["source_dataset"], 180) for s in unit["starts"]]
selected = selection("source", runs)
if selected is not None:
    execute("source_held", "selected", 90)
    if unit["excluded_dataset"] is not None:
        runs = [execute("target_fit", str(t), 120) for t in (0, -2, 2)]
        if selection("target", runs) is not None:
            execute("target_held", "selected", 90)
print(unit_id, "terminal", flush=True)
