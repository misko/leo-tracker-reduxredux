"""Seal bounded covariance jobs and select using training-only qualification."""

import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan_path = HERE.parent / "2026_09_28_cross_dataset_position/plan.json"
plan = json.loads(plan_path.read_text())


def launch(dataset, decay, stage):
    group = next(g for g in plan["groups"] if g["dataset_id"] == dataset)
    target = HERE / dataset / f"t{decay}" / stage
    target.mkdir(parents=True, exist_ok=False)
    paths = [HERE / n for n in ("PROTOCOL.md", "run.py", "launch.py")]
    paths += [
        plan_path,
        ROOT / group["source_point_path"],
        HERE.parent / f"2026_09_28_correlated_residual_shadow/{dataset}/result.json",
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
    paths += [ROOT / "tests/research/test_ds789_covariance_position.py"]
    if stage == "diagnostic":
        paths.append(target.parent / "selection.json")
    for item in group["inputs"]:
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
        dataset,
        str(decay),
        stage,
    ]
    (target / "launch.json").write_text(
        json.dumps({"command": command, "sha256": bindings}, indent=2)
    )
    with (target / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (target / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for p in target.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (target / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(dataset, decay, stage, result.returncode, flush=True)
    return result.returncode


phase = sys.argv[1]
jobs = []
for dataset in ("DS7", "DS8", "DS9"):
    for decay in (0, 10):
        parent = HERE / dataset / f"t{decay}"
        if phase == "fit":
            assert (parent / "preflight/exit-code.txt").read_text().strip() == "0"
            jobs.extend((dataset, decay, stage) for stage in ("fit_original", "fit_origin"))
        elif phase == "diagnostic":
            fits = []
            for stage in ("fit_original", "fit_origin"):
                path = parent / stage
                if (path / "exit-code.txt").read_text().strip() == "0":
                    fit = json.loads((path / "result.json").read_text())
                    if fit["qualified"]:
                        fits.append(fit)
            selection = {
                "qualified_starts": len(fits),
                "selected": max(fits, key=lambda f: f["training_log_score"]) if fits else None,
            }
            with (parent / "selection.json").open("x") as stream:
                json.dump(selection, stream, indent=2)
            if fits:
                jobs.append((dataset, decay, "diagnostic"))
        else:
            assert phase == "preflight"
            jobs.append((dataset, decay, "preflight"))
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(launch, *job) for job in jobs]
    outcomes = [f.result() for f in futures]
print("phase", phase, "jobs", len(jobs), "outcomes", outcomes, flush=True)
