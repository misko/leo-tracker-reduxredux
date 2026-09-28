"""Bound and seal each source/target fit without automatic retries."""

import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())


def selection(parent, stage, starts):
    runs = []
    for start in starts:
        folder = parent / (stage + "_fit") / start
        code = int((folder / "exit-code.txt").read_text())
        runs.append(
            {
                "start_id": start,
                "exit_code": code,
                "result": json.loads((folder / "result.json").read_text()) if code == 0 else None,
            }
        )
    eligible = [r["result"] for r in runs if r["result"] is not None and r["result"]["qualified"]]
    chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    path = parent / (stage + "-selection.json")
    with path.open("x") as stream:
        json.dump(
            {"runs": runs, "qualified_starts": len(eligible), "selected": chosen}, stream, indent=2
        )
    return chosen


def launch(spec, unit, stage, start):
    decay = spec["decay_s"]
    parent = HERE / f"t{decay}" / unit["unit_id"]
    target = parent / stage / start if stage.endswith("fit") else parent / stage
    target.mkdir(parents=True, exist_ok=False)
    groups = [
        g
        for g in spec["groups"]
        if (
            g["dataset_id"] == unit["excluded_dataset"]
            if stage.startswith("target")
            else g["dataset_id"] in unit["source_datasets"]
        )
    ]
    paths = [
        HERE / n for n in ("PROTOCOL.md", "plan.json", "run.py", "launch.py", "input-seal.json")
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
    paths += [
        ROOT / "tests/research" / n
        for n in (
            "test_ds789_covariance_position.py",
            "test_ds789_correlated_residual.py",
            "test_ds789_pool_plan.py",
        )
    ]
    if stage != "source_fit":
        paths.append(parent / "source-selection.json")
    if stage == "target_held":
        paths.append(parent / "target-selection.json")
    for group in groups:
        paths.append(ROOT / group["input_validation_path"])
        for item in group["inputs"]:
            for artifact in item["artifacts"]:
                path = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                )
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
        str(decay),
        unit["unit_id"],
        stage,
        start,
    ]
    (target / "launch.json").write_text(
        json.dumps({"command": command, "sha256": bindings}, indent=2)
    )
    with (target / "terminal.log").open("x") as stream:
        run = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (target / "exit-code.txt").write_text(str(run.returncode) + "\n")
    for p in target.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (target / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(decay, unit["unit_id"], stage, start, run.returncode, flush=True)
    return run.returncode


phase = sys.argv[1]
jobs = []
for spec in plan["models"]:
    for unit in spec["units"]:
        parent = HERE / f"t{spec['decay_s']}" / unit["unit_id"]
        if phase == "source":
            jobs.extend((spec, unit, "source_fit", s["source_dataset"]) for s in unit["starts"])
        elif phase == "transfer":
            chosen = selection(parent, "source", [s["source_dataset"] for s in unit["starts"]])
            if chosen:
                jobs.append((spec, unit, "source_held", "selected"))
                if unit["excluded_dataset"] is not None:
                    jobs.extend((spec, unit, "target_fit", start) for start in ("0", "-2", "2"))
        else:
            assert phase == "target_held"
            if (
                unit["excluded_dataset"] is not None
                and json.loads((parent / "source-selection.json").read_text())["selected"]
                is not None
            ):
                chosen = selection(parent, "target", ["0", "-2", "2"])
                if chosen:
                    jobs.append((spec, unit, "target_held", "selected"))
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(launch, *job) for job in jobs]
    outcomes = [f.result() for f in futures]
print(phase, len(jobs), outcomes, flush=True)
