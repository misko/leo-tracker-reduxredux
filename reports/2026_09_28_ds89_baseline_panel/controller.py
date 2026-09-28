"""One dataset worker: bounded sequential exports, validation and fits."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / "2026_09_28_ds89_baseline_transfer"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def units(plan, dataset):
    rows = [r for r in plan["captures"] if r["dataset_id"] == dataset]
    if [r["unit_id"] for r in rows] != [f"{dataset}-{i:03d}" for i in range(1, 9)]:
        raise ValueError("frozen panel membership/order changed")
    if len({r["session_id"] for r in rows}) != 8:
        raise ValueError("duplicate session")
    return rows[1:]


def hashes(paths):
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("DS8", "DS9"))
    dataset = parser.parse_args().dataset
    deadline = time.monotonic() + 1200
    worker = HERE / "workers" / dataset
    worker.mkdir(parents=True, exist_ok=False)
    plan = json.loads((PREFLIGHT / "plan.json").read_text())
    rows = units(plan, dataset)
    prior_seal = json.loads((PREFLIGHT / "evidence-sha256.json").read_text())
    for name, expected in prior_seal.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    environment = subprocess.check_output(
        ["sudo", "-n", PYTHON, str(PREFLIGHT / "environment.py")], text=True
    )
    (worker / "environment.json").write_text(environment)
    sources = [
        Path(__file__),
        HERE / "run_stage.py",
        HERE / "PROTOCOL.md",
        PREFLIGHT / "plan.json",
        PREFLIGHT / "environment.py",
        PREFLIGHT / "solver" / f"{dataset}-001/request.json",
        ROOT / "tools/ds7_export_baseline.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]
    frozen_sources = hashes(sources)
    outcomes = []
    for row in rows:
        unit = row["unit_id"]
        if time.monotonic() >= deadline - 5:
            outcomes.append({"unit_id": unit, "state": "pending_worker_deadline"})
            continue
        receipt = HERE / "receipts" / unit
        export = HERE / "exports" / unit
        solver = HERE / "solver" / unit
        for path in (receipt, export, solver):
            path.mkdir(parents=True, exist_ok=False)
        state = "complete"
        stages = []
        for stage, cap in [("observations", 60), ("banks", 120), ("freeze", 30), ("fit", 180)]:
            remaining = deadline - time.monotonic() - 5
            if remaining <= 0:
                state = "pending_worker_deadline"
                break
            assert hashes(sources) == frozen_sources
            limit = min(float(cap), remaining)
            stage_dir = receipt / stage
            stage_dir.mkdir()
            inputs = [
                p for directory in (export, solver) for p in directory.rglob("*") if p.is_file()
            ]
            command = [
                "sudo",
                "-n",
                "/usr/bin/time",
                "-v",
                "-o",
                str(stage_dir / "resources.txt"),
                "timeout",
                "--kill-after=5s",
                f"{limit:.3f}s",
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
            with (stage_dir / "launch.json").open("x") as stream:
                json.dump(
                    {"command": command, "sha256": {**frozen_sources, **hashes(inputs)}},
                    stream,
                    indent=2,
                )
            print(json.dumps({"unit_id": unit, "stage": stage, "state": "starting"}), flush=True)
            with (stage_dir / "terminal.log").open("x") as stream:
                result = subprocess.run(
                    command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False
                )
            (stage_dir / "exit-code.txt").write_text(str(result.returncode) + "\n")
            stages.append({"stage": stage, "exit_code": result.returncode})
            print(
                json.dumps({"unit_id": unit, "stage": stage, "exit_code": result.returncode}),
                flush=True,
            )
            if result.returncode:
                state = "failed_" + stage
                break
        files = sources + [
            p
            for directory in (receipt, export, solver)
            for p in directory.rglob("*")
            if p.is_file()
        ]
        with (solver / "fit-seal.json").open("x") as stream:
            json.dump(
                {"stage": "before_geographic_scoring", "state": state, "sha256": hashes(files)},
                stream,
                indent=2,
            )
        outcomes.append({"unit_id": unit, "state": state, "stages": stages})
        (worker / "status.json").write_text(json.dumps(outcomes, indent=2))
    (worker / "status.json").write_text(json.dumps(outcomes, indent=2))
    print(json.dumps({"dataset": dataset, "outcomes": outcomes}), flush=True)


if __name__ == "__main__":
    main()
