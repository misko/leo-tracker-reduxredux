"""Disjoint DS8/DS9 input batches with memory-headroom and stage guards."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from batch_lock import acquire_locks

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
environment_script = HERE.parent / "2026_09_28_ds89_baseline_transfer/environment.py"
locks = acquire_locks(HERE, sys.argv[1])
assert (HERE / "environment.json").exists(), "Initialize runtime with the serial launcher first"
(HERE / "validated").mkdir(exist_ok=True)
plan = json.loads((HERE / "plan.json").read_text())
mode = sys.argv[1]
assert mode in ("DS8", "DS9")
batch = int(sys.argv[2])
missing = [r for r in plan["captures"] if r["dataset_id"] == mode and r["reused_input"] is None]
assert 0 <= batch < (len(missing) + 4) // 5
captures = missing[5 * batch : 5 * (batch + 1)]
mode += f"-batch{batch}"
worker = HERE / "workers" / (mode + "-" + str(time.time_ns()))
worker.mkdir(parents=True, exist_ok=False)
deadline = time.monotonic() + 1800
outcomes = []


def hashes(paths):
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
    }


sources = [
    HERE / n
    for n in (
        "PROTOCOL.md",
        "plan.json",
        "input-seal.json",
        "run_stage.py",
        "launch.py",
        "launch_parallel.py",
        "batch_lock.py",
        "test_batch_lock.py",
        "PARALLEL_PROTOCOL.md",
        "environment.json",
    )
]
sources += [
    ROOT / "tools" / n
    for n in ("ds7_export_baseline.py", "ds7_fast_baseline_adapter.py", "ds7_baseline_adapter.py")
]
sources += [
    environment_script,
    ROOT / "tests/research/test_ds7_baseline_export.py",
    *list((HERE / "runtime-sources").glob("*.py")),
]
for row in captures:
    unit = row["unit_id"]
    folder = HERE / "exports" / unit
    bound = sources + [ROOT / row["dataset_manifest_path"], ROOT / row["pose_path"]]
    if row["reused_input"]:
        bound += [Path(a["path"]) for a in row["reused_input"]["artifacts"]]
    if row["dataset_id"] == "DS9":
        bound.append(
            ROOT / "reports/2026_09_28_ds9_post_ds8/analysis" / (row["session_id"] + ".json")
        )
    sequence = (
        [("validate", 30, 1)]
        if row["reused_input"]
        else [("observations", 60, 1.5), ("banks", 240, 2), ("validate", 30, 1)]
    )
    state, stages = "complete", []
    for stage, cap, headroom in sequence:
        headroom += 1
        stage_dir = HERE / "receipts" / unit / stage
        if stage_dir.exists():
            seal = json.loads((stage_dir / "seal.json").read_text())["sha256"]
            assert all(
                hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h for n, h in seal.items()
            )
            code = int((stage_dir / "exit-code.txt").read_text())
            stages.append({"stage": stage, "exit_code": code, "previously_completed": True})
            if code:
                state = "failed_" + stage
                break
            continue
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(mem["MemAvailable"].split()[0]) * 1024
        remaining = deadline - time.monotonic() - 5
        if remaining <= 0 or available < headroom * 1024**3:
            state = "pending_deadline" if remaining <= 0 else "pending_headroom"
            stages.append(
                {
                    "stage": stage,
                    "not_started": True,
                    "available_bytes": available,
                    "required_bytes": int(headroom * 1024**3),
                }
            )
            break
        folder.mkdir(parents=True, exist_ok=True)
        stage_dir.mkdir(parents=True, exist_ok=False)
        inputs = bound + [p for p in folder.rglob("*") if p.is_file()]
        bindings = hashes(inputs)
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(stage_dir / "resources.txt"),
            "timeout",
            "--kill-after=5s",
            f"{min(cap, remaining):.3f}s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            PYTHON,
            str(HERE / "run_stage.py"),
            unit,
            stage,
        ]
        (stage_dir / "launch.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "sha256": bindings,
                    "available_bytes": available,
                    "required_bytes": int(headroom * 1024**3),
                },
                indent=2,
            )
        )
        print(unit, stage, "starting", flush=True)
        with (stage_dir / "terminal.log").open("x") as stream:
            completed = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (stage_dir / "exit-code.txt").write_text(str(completed.returncode) + "\n")
        assert hashes(inputs) == bindings
        outputs = [p for p in stage_dir.iterdir() if p.is_file()] + [
            p for p in folder.rglob("*") if p.is_file()
        ]
        validation = HERE / "validated" / (unit + ".json")
        if validation.exists():
            outputs.append(validation)
        bindings.update(hashes(outputs))
        (stage_dir / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
        stages.append({"stage": stage, "exit_code": completed.returncode})
        print(unit, stage, completed.returncode, flush=True)
        if completed.returncode:
            state = "failed_" + stage
            break
    outcomes.append({"unit_id": unit, "state": state, "stages": stages})
    (worker / "status.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    if state.startswith("pending"):
        break
print(mode, "finished", len(outcomes), "of", len(captures), flush=True)
locks.close()
