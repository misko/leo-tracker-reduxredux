"""Two bounded sequential dataset workers, preserving every stage outcome."""

import concurrent.futures
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
environment_script = HERE.parent / "2026_09_28_ds89_baseline_transfer/environment.py"
environment = json.loads(
    subprocess.check_output(["sudo", "-n", PYTHON, str(environment_script)], text=True)
)
for name, module in environment["modules"].items():
    source = Path(module["path"])
    content = subprocess.check_output(["sudo", "-n", "cat", str(source)])
    assert hashlib.sha256(content).hexdigest() == module["sha256"]
    archived = HERE / "runtime-sources" / (name + ".py")
    archived.parent.mkdir(exist_ok=True)
    assert not archived.exists()
    archived.write_bytes(content)
    module["archived_path"] = str(archived.relative_to(ROOT))
(HERE / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
(HERE / "validated").mkdir(exist_ok=False)
plan = json.loads((HERE / "plan.json").read_text())


def hashes(paths):
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
    }


def worker(dataset):
    deadline = time.monotonic() + 1800
    outcomes = []
    worker_dir = HERE / "workers" / dataset
    worker_dir.mkdir(parents=True, exist_ok=False)
    sources = [
        HERE / n
        for n in (
            "PROTOCOL.md",
            "plan.json",
            "input-seal.json",
            "run_stage.py",
            "launch.py",
            "environment.json",
        )
    ]
    sources += [
        ROOT / "tools" / n
        for n in (
            "ds7_export_baseline.py",
            "ds7_fast_baseline_adapter.py",
            "ds7_baseline_adapter.py",
        )
    ]
    sources += [
        environment_script,
        ROOT / "tests/research/test_ds7_baseline_export.py",
        *list((HERE / "runtime-sources").glob("*.py")),
    ]
    for row in (r for r in plan["captures"] if r["dataset_id"] == dataset):
        unit = row["unit_id"]
        receipt = HERE / "receipts" / unit
        receipt.mkdir(parents=True, exist_ok=False)
        folder = HERE / "exports" / unit
        folder.mkdir(parents=True, exist_ok=True)
        state, stages = "complete", []
        sequence = (
            [("validate", 30)]
            if row["reused_input"]
            else [("observations", 60), ("banks", 240), ("validate", 30)]
        )
        bound = sources + [ROOT / row["dataset_manifest_path"]]
        if row["reused_input"]:
            bound += [Path(a["path"]) for a in row["reused_input"]["artifacts"]]
        if dataset == "DS9":
            bound.append(
                ROOT / "reports/2026_09_28_ds9_post_ds8/analysis" / (row["session_id"] + ".json")
            )
        for stage, cap in sequence:
            remaining = deadline - time.monotonic() - 5
            if remaining <= 0:
                state = "pending_worker_deadline"
                break
            stage_dir = receipt / stage
            stage_dir.mkdir()
            inputs = bound + [p for p in folder.rglob("*") if p.is_file()]
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
            bindings = hashes(inputs)
            (stage_dir / "launch.json").write_text(
                json.dumps({"command": command, "sha256": bindings}, indent=2)
            )
            print(unit, stage, "starting", flush=True)
            with (stage_dir / "terminal.log").open("x") as stream:
                completed = subprocess.run(
                    command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT
                )
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
        (worker_dir / "status.json").write_text(json.dumps(outcomes, indent=2))
    return outcomes


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(worker, ds) for ds in ("DS7", "DS8", "DS9")]
    outcomes = [future.result() for future in futures]
(HERE / "outcomes.json").write_text(json.dumps(outcomes, indent=2) + "\n")
print("workers complete", flush=True)
