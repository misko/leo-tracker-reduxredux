"""Freeze and execute bounded geographic drift-allocation fits."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_drift_position"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def save(p, value):
    with p.open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(bindings):
    for name, value in bindings.items():
        assert digest(ROOT / name) == value, name


def prepare():
    evidence = read(PRIOR / "evidence-sha256.json")["sha256"]
    verify(evidence)
    command = [
        "sudo",
        "-n",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        PYTHON,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_model.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        outcome = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", {"command": command, "exit_code": outcome.returncode})
    assert outcome.returncode == 0
    old = read(PRIOR / "fixed-plan.json")
    units = []
    for arm in ("symmetric", "rx0_anchor", "rx1_anchor"):
        for prior in old["units"]:
            n = len(prior["group"]["session_ids"])
            starts = [
                {"name": name, "x": [e, north] + [0.0] * n}
                for name, e, north in (
                    ("origin", 0, 0),
                    ("east_south", 3, -3),
                    ("west_north", -3, 3),
                )
            ]
            starts.append({"name": "q020", "x": prior["x"]})
            units.append(
                {
                    **prior,
                    "base_unit_id": prior["unit_id"],
                    "unit_id": prior["unit_id"] + "_" + arm,
                    "arm": arm,
                    "starts": starts,
                }
            )
    plan = {"config": old["config"], "coherence": old["coherence"], "units": units}
    save(HERE / "plan.json", plan)
    sources = [
        HERE / n for n in ("study.py", "model.py", "test_model.py", "PROTOCOL.md", "plan.json")
    ]
    external = [
        PRIOR / "correction.py",
        PRIOR / "test_correction.py",
        HERE.parent / "2026_09_29_rx_alignment/align.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_unassociated_trend/test_trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        HERE.parent / "2026_09_29_frequency_contrast/test_contrast_position.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / old["coherence"],
    ]
    for p in external:
        assert evidence[str(p.relative_to(ROOT))] == digest(p)
    names = [str(p.relative_to(ROOT)) for p in sources + external]
    bindings = {str(p.relative_to(ROOT)): digest(p) for p in sources + external}
    for u in units:
        paths = [ROOT / u[k] for k in ("selection", "baseline_held")]
        paths += [PRIOR / "fixed-runs" / u["base_unit_id"] / "result.json"]
        paths += [Path(a["path"]) for i in u["group"]["inputs"] for a in i["artifacts"]]
        for p in paths:
            key = str(p.relative_to(ROOT))
            assert evidence[key] == digest(p), key
            bindings[key] = digest(p)
    for p in (HERE / "tests.log", HERE / "test-receipt.json", PRIOR / "evidence-sha256.json"):
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", {"sha256": bindings, "execution_sources": names})
    print("Frozen", len(units), "units and", len(bindings), "bindings", flush=True)


def child(key, stage, start):
    import numpy as np
    from scipy.optimize import minimize

    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as baseline
    from model import build

    plan = read(HERE / "plan.json")
    u = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents({"config": plan["config"], "inputs": u["group"]["inputs"]})
    assert [d["session_id"] for d in docs] == u["group"]["session_ids"]
    assert sum(len(d["tracks"]) for d in docs) == u["group"]["tracks"]
    assert (
        sum(int(t["mask"].sum()) for d in docs for t in d["tracks"])
        == u["group"]["training_observations"]
    )
    assert (
        sum(int((~t["mask"]).sum()) for d in docs for t in d["tracks"])
        == u["group"]["held_observations"]
    )
    scans = {s["session_id"]: s for s in read(ROOT / plan["coherence"])["scans"]}
    model, receipts = build(docs, scans, plan["config"], baseline.Stationary, u["arm"])
    parent = HERE / "runs" / key
    folder = parent / "fit" / start if stage == "fit" else parent / "held"
    if stage == "fit":
        initial = next(s["x"] for s in u["starts"] if s["name"] == start)
        bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(docs)
        fit = minimize(
            model.value_gradient,
            np.asarray(initial),
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 140, "maxfun": 200, "ftol": 1e-14, "gtol": 1e-8, "maxls": 30},
        )
        boundary = any(
            min(abs(v - a), abs(v - b)) < 0.001 for v, (a, b) in zip(fit.x, bounds, strict=True)
        )
        result = {
            "initial": initial,
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
        result = model.evaluate(x, held=True)
        checks = []
        for axis in range(len(x)):
            for step in (0.001, 0.0005) if axis < 2 else (0.0000625, 0.00003125):
                delta = np.eye(len(x))[axis] * step
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2 * step)
                crossing = bool(
                    axis >= 2 and np.floor((x[axis] - step) * 4) != np.floor((x[axis] + step) * 4)
                )
                checks.append(
                    dict(
                        axis=axis,
                        step=step,
                        numerical=numerical,
                        absolute_difference=abs(numerical - result["gradient"][axis]),
                        crosses_grid_node=crossing,
                    )
                )
        agreement = [
            abs(checks[2 * a]["numerical"] - checks[2 * a + 1]["numerical"])
            for a in range(2, len(x))
        ]
        replay = abs(result["score"] - selected["training_log_score"])
        fixed = read(PRIOR / "fixed-runs" / u["base_unit_id"] / "result.json")["arms"][u["arm"]]
        at_old = model.evaluate(np.asarray(u["x"]), held=True)
        old_error = max(
            abs(at_old["score"] - fixed["training_log_score"]),
            max(
                abs(a["held_log_score"] - b["held_log_score"])
                for a, b in zip(at_old["rows"], fixed["rows"], strict=True)
            ),
        )
        assert receipts == fixed["corrections"]
        passed = (
            replay < 1e-7
            and old_error < 1e-7
            and all(c["absolute_difference"] < 0.002 and not c["crosses_grid_node"] for c in checks)
            and all(v < 0.002 for v in agreement)
        )
        for row in result["rows"]:
            assert abs(sum(row["weights_given_signal"]) - 1) < 1e-10
            assert 0 <= row["signal_responsibility"] <= 1 + 1e-10
        result = {
            "audit_passed": bool(passed),
            "training_replay_error": replay,
            "old_position_replay_error": old_error,
            "training_log_score": result["score"],
            "held_log_score": sum(r["held_log_score"] for r in result["rows"]),
            "rows": result["rows"],
            "gradient": result["gradient"].tolist(),
            "gradient_checks": checks,
            "timing_step_agreement": agreement,
            "corrections": receipts,
        }
    result.update(unit_id=key, stage=stage, start_id=start)
    save(folder / "result.json", result)


def launch(u, stage, start):
    frozen = read(HERE / "input-seal.json")
    names = list(frozen["execution_sources"])
    names += [
        str(Path(a["path"]).relative_to(ROOT)) for i in u["group"]["inputs"] for a in i["artifacts"]
    ]
    names += [str((PRIOR / "fixed-runs" / u["base_unit_id"] / "result.json").relative_to(ROOT))]
    bindings = {n: frozen["sha256"][n] for n in names}
    bindings[str((HERE / "input-seal.json").relative_to(ROOT))] = digest(HERE / "input-seal.json")
    parent = HERE / "runs" / u["unit_id"]
    if stage == "held":
        bindings[str((parent / "selection.json").relative_to(ROOT))] = digest(
            parent / "selection.json"
        )
    verify(bindings)
    available = (
        int(
            next(
                s.split()[1]
                for s in Path("/proc/meminfo").read_text().splitlines()
                if s.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    assert available >= 5 * 1024**3
    folder = parent / "fit" / start if stage == "fit" else parent / "held"
    folder.mkdir(parents=True, exist_ok=False)
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
        PYTHON,
        str(HERE / "study.py"),
        "child",
        u["unit_id"],
        stage,
        start,
    ]
    save(
        folder / "launch.json",
        {"command": command, "sha256": bindings, "available_bytes": available},
    )
    with (folder / "terminal.log").open("x") as f:
        outcome = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(folder / "exit.json", {"exit_code": outcome.returncode})
    verify(bindings)
    for p in folder.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(folder / "seal.json", {"sha256": bindings})
    print(u["unit_id"], stage, start, "exit", outcome.returncode, flush=True)
    return read(folder / "result.json") if outcome.returncode == 0 else None


def batch(arm, offset):
    verify(read(HERE / "input-seal.json")["sha256"])
    units = [u for u in read(HERE / "plan.json")["units"] if u["arm"] == arm]
    assert offset in (0, 6, 12) and len(units) == 18
    for u in units[offset : offset + 6]:
        runs = [launch(u, "fit", s["name"]) for s in u["starts"]]
        eligible = [r for r in runs if r is not None and r["qualified"]]
        selected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        save(
            HERE / "runs" / u["unit_id"] / "selection.json",
            {"runs": runs, "qualified_starts": len(eligible), "selected": selected},
        )
        if selected:
            launch(u, "held", "selected")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "child":
        child(*sys.argv[2:])
    elif sys.argv[1] == "batch":
        batch(sys.argv[2], int(sys.argv[3]))
    else:
        raise ValueError("Expected prepare, child or batch")
