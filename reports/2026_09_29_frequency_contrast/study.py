"""Freeze and execute the predeclared consecutive-panel contrast control."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "2026_09_29_consecutive_panels"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(bindings):
    for name, expected in bindings.items():
        assert digest(ROOT / name) == expected, name


def prepare():
    original = read(BASE / "plan.json")
    bindings = read(BASE / "input-seal.json")["sha256"]
    verify(bindings)
    paths = [BASE / "plan.json", BASE / "input-seal.json"]
    paths += [
        HERE / n
        for n in ("PROTOCOL.md", "contrast_position.py", "test_contrast_position.py", "study.py")
    ]
    paths += [
        ROOT / "tools" / n for n in ("ds7_baseline_adapter.py", "ds7_fast_baseline_adapter.py")
    ]
    for unit in original["models"][0]["units"]:
        paths += [
            BASE / "t0" / unit["unit_id"] / n
            for n in ("source-selection.json", "source_held/result.json")
        ]
    command = [
        "sudo",
        "-n",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        PYTHON,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_contrast_position.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as stream:
        outcome = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    save(HERE / "test-receipt.json", {"command": command, "exit_code": outcome.returncode})
    assert outcome.returncode == 0
    plan = {
        "config": original["config"],
        "groups": original["models"][0]["groups"],
        "units": original["models"][0]["units"],
        "model": "frequency_contrast_t4_scale100",
    }
    save(HERE / "plan.json", plan)
    paths += [HERE / n for n in ("tests.log", "test-receipt.json", "plan.json")]
    for path in paths:
        name = str(path.relative_to(ROOT))
        value = digest(path)
        assert name not in bindings or bindings[name] == value
        bindings[name] = value
    save(HERE / "input-seal.json", {"sha256": bindings})
    print("Frozen", len(plan["units"]), "panels;", len(bindings), "bindings", flush=True)


def child(unit_id, stage, start_id):
    import numpy as np
    from scipy.optimize import minimize

    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as baseline
    from contrast_position import ContrastPosition

    plan = read(HERE / "plan.json")
    group = next(g for g in plan["groups"] if g["dataset_id"] == unit_id)
    unit = next(u for u in plan["units"] if u["unit_id"] == unit_id)
    documents = baseline.load_documents({"config": plan["config"], "inputs": group["inputs"]})
    assert [d["session_id"] for d in documents] == unit["session_ids"]
    assert sum(len(d["tracks"]) for d in documents) == group["tracks"]
    assert (
        sum(int(t["mask"].sum()) for d in documents for t in d["tracks"])
        == group["training_observations"]
    )
    assert (
        sum(int((~t["mask"]).sum()) for d in documents for t in d["tracks"])
        == group["held_observations"]
    )
    model = ContrastPosition(documents, plan["config"], baseline.Stationary)
    parent = HERE / "runs" / unit_id
    folder = parent / stage / start_id if stage == "fit" else parent / stage
    if stage == "fit":
        initial = np.asarray(
            next(s["x"] for s in unit["starts"] if s["source_dataset"] == start_id)
        )
        bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)
        fit = minimize(
            model.value_gradient,
            initial,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 140, "maxfun": 200, "ftol": 1e-14, "gtol": 1e-8, "maxls": 30},
        )
        boundary = any(
            min(abs(v - a), abs(v - b)) < 0.001 for v, (a, b) in zip(fit.x, bounds, strict=True)
        )
        result = {
            "initial": initial.tolist(),
            "x": fit.x.tolist(),
            "success": bool(fit.success),
            "message": str(fit.message),
            "boundary_hit": boundary,
            "gradient": (-fit.jac).tolist(),
            "training_log_score": -float(fit.fun),
            "evaluations": int(fit.nfev),
            "iterations": int(fit.nit),
            "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
            "estimate": dict(
                zip(("latitude_deg", "longitude_deg"), model.coordinates(fit.x), strict=True)
            ),
        }
    else:
        selected = read(parent / "selection.json")["selected"]
        x = np.asarray(selected["x"])
        evaluation = model.evaluate(x, gradient=True, held=True)
        replay_error = abs(evaluation["score"] - selected["training_log_score"])
        checks = []
        for axis in range(len(x)):
            steps = (0.001, 0.0005) if axis < 2 else (0.0000625, 0.00003125)
            for step in steps:
                delta = np.eye(len(x))[axis] * step
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2 * step)
                crossing = bool(
                    axis >= 2 and np.floor((x[axis] - step) * 4) != np.floor((x[axis] + step) * 4)
                )
                checks.append(
                    {
                        "axis": axis,
                        "step": step,
                        "numerical": numerical,
                        "implemented": float(evaluation["gradient"][axis]),
                        "absolute_difference": abs(numerical - evaluation["gradient"][axis]),
                        "crosses_grid_node": crossing,
                    }
                )
        timing_agreement = [
            abs(checks[2 * a]["numerical"] - checks[2 * a + 1]["numerical"])
            for a in range(2, len(x))
        ]
        passed = (
            replay_error < 1e-7
            and all(c["absolute_difference"] < 0.002 and not c["crosses_grid_node"] for c in checks)
            and all(v < 0.002 for v in timing_agreement)
        )
        result = {
            "audit_passed": bool(passed),
            "training_replay_error": replay_error,
            "training_log_score": evaluation["score"],
            "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
            "rows": evaluation["rows"],
            "gradient_checks": checks,
            "timing_step_agreement": timing_agreement,
            "full_training_gradient": evaluation["gradient"].tolist(),
        }
    result.update(unit_id=unit_id, stage=stage, start_id=start_id, session_ids=unit["session_ids"])
    save(folder / "result.json", result)
    print(unit_id, stage, start_id, "complete", flush=True)


def launch(unit_id, stage, start):
    bindings = read(HERE / "input-seal.json")["sha256"]
    verify(bindings)
    memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(memory["MemAvailable"].split()[0]) * 1024
    assert available >= 5 * 1024**3, "Insufficient headroom; no process launched"
    parent = HERE / "runs" / unit_id
    folder = parent / stage / start if stage == "fit" else parent / stage
    folder.mkdir(parents=True, exist_ok=False)
    paths = [HERE / "input-seal.json"]
    if stage == "held":
        paths.append(parent / "selection.json")
    for path in paths:
        bindings[str(path.relative_to(ROOT))] = digest(path)
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
        PYTHON,
        str(HERE / "study.py"),
        "child",
        unit_id,
        stage,
        start,
    ]
    save(
        folder / "launch.json",
        {"command": command, "sha256": bindings, "available_bytes": available},
    )
    with (folder / "terminal.log").open("x") as stream:
        outcome = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (folder / "exit-code.txt").write_text(str(outcome.returncode) + "\n")
    verify(bindings)
    for path in folder.iterdir():
        if path.is_file():
            bindings[str(path.relative_to(ROOT))] = digest(path)
    save(folder / "seal.json", {"sha256": bindings})
    print(unit_id, stage, start, "exit", outcome.returncode, flush=True)
    return read(folder / "result.json") if outcome.returncode == 0 else None


def run(unit_id):
    unit = next(u for u in read(HERE / "plan.json")["units"] if u["unit_id"] == unit_id)
    runs = [launch(unit_id, "fit", s["source_dataset"]) for s in unit["starts"]]
    eligible = [r for r in runs if r is not None and r["qualified"]]
    selected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    save(
        HERE / "runs" / unit_id / "selection.json",
        {"runs": runs, "qualified_starts": len(eligible), "selected": selected},
    )
    if selected:
        launch(unit_id, "held", "selected")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "child":
        child(*sys.argv[2:])
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        raise ValueError("Expected prepare, child or run")
