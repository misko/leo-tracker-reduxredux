"""Bound and seal each timing fit/audit, preserving unsuccessful outcomes."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
phase = sys.argv[1]
strength = sys.argv[2]
assert strength in ("c20", "c30", "c40", "c50")
assert phase in ("fit", "held")
for unit in plan["units"]:
    if unit["strength"] != strength:
        continue
    parent = HERE / "runs" / unit["unit_id"]
    starts = [s["label"] for s in unit["starts"]]
    if phase == "held":
        runs = []
        for start in starts:
            folder = parent / "fit" / start
            code = int((folder / "exit-code.txt").read_text())
            runs.append(
                {
                    "start": start,
                    "exit_code": code,
                    "result": json.loads((folder / "result.json").read_text())
                    if code == 0
                    else None,
                }
            )
        eligible = [r["result"] for r in runs if r["result"] and r["result"]["qualified"]]
        selected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        with (parent / "selection.json").open("x") as stream:
            json.dump(
                {"runs": runs, "qualified_starts": len(eligible), "selected": selected},
                stream,
                indent=2,
            )
        if selected is None:
            print(unit["unit_id"], "no qualified timing refit", flush=True)
            continue
        starts = ["selected"]
    for start in starts:
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(mem["MemAvailable"].split()[0]) * 1024
        assert available >= 5 * 1024**3, "Insufficient headroom; process not launched"
        folder = parent / "fit" / start if phase == "fit" else parent / "held"
        folder.mkdir(parents=True, exist_ok=False)
        paths = [
            HERE / n
            for n in (
                "PROTOCOL.md",
                "prepare.py",
                "plan.json",
                "input-seal.json",
                "run.py",
                "launch.py",
                "cone_position.py",
                "cones.py",
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
        if phase == "held":
            paths.append(parent / "selection.json")
        for item in unit["group"]["inputs"]:
            for artifact in item["artifacts"]:
                path = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                )
                paths.append(path)
        bindings = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
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
            unit["unit_id"],
            phase,
            start,
        ]
        (folder / "launch.json").write_text(
            json.dumps(
                {"command": command, "sha256": bindings, "available_bytes": available}, indent=2
            )
        )
        with (folder / "terminal.log").open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
        for path in folder.iterdir():
            if path.is_file():
                bindings[str(path.relative_to(ROOT))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
        print(unit["unit_id"], phase, start, result.returncode, flush=True)
