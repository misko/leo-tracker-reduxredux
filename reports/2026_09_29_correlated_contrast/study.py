"""Freeze correlated contrasts with/without soft40 and run bounded audited fits."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONTRAST = HERE.parent / "2026_09_29_frequency_contrast"
TREND = HERE.parent / "2026_09_29_unassociated_trend"
CONE = HERE.parent / "2026_09_29_cone_trend"
SCORES = HERE.parent / "2026_09_29_hard_cone_scoring_v2"
GEOMETRY = HERE.parent / "2026_09_29_rx_cone_position"
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


def execution_paths():
    return [
        HERE / n
        for n in (
            "PROTOCOL.md",
            "density.py",
            "correlated_trend.py",
            "test_correlated.py",
            "study.py",
            "plan.json",
        )
    ] + [
        TREND / "trend_mixture.py",
        TREND / "test_trend_mixture.py",
        CONTRAST / "contrast_position.py",
        CONTRAST / "test_contrast_position.py",
        GEOMETRY / "cones.py",
        CONE / "cone_trend.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
    ]


def prepare():
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
        "test_correlated.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as stream:
        outcome = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    save(HERE / "test-receipt.json", {"command": command, "exit_code": outcome.returncode})
    assert outcome.returncode == 0
    original = read(SCORES / "plan.json")
    evidence = read(SCORES / "evidence-sha256.json")["sha256"]
    verify(evidence)
    groups, units, paths = [], [], []
    for arm, width in (("corr10", None), ("corr10_c40", 40)):
        for old in original["units"]:
            key = old["unit_id"]
            group = old["group"]
            count = len(group["session_ids"])
            groups.append({**group, "dataset_id": key + "_" + arm, "base_unit_id": key, "arm": arm})
            starts = [
                {"source_dataset": name, "x": [e, n] + [0.0] * count}
                for name, e, n in (("origin", 0, 0), ("east_south", 3, -3), ("west_north", -3, 3))
            ] + [{"source_dataset": "no_cone", "x": old["x"]}]
            units.append(
                {
                    "unit_id": key + "_" + arm,
                    "base_unit_id": key,
                    "arm": arm,
                    "session_ids": group["session_ids"],
                    "starts": starts,
                    "half_angle_deg": width,
                    "background_probability": 0.2,
                    "decay_s": 10.0,
                }
            )
            paths += [ROOT / old[n] for n in ("selection", "baseline_held")]
            paths += [Path(a["path"]) for i in group["inputs"] for a in i["artifacts"]]
            paths += [ROOT / group["manifest_path"]]
    for path in paths:
        name = str(path.relative_to(ROOT))
        # Dataset manifests are bound by the earlier consecutive panel study.
        donor = evidence.get(name)
        if donor is None:
            donor = read(BASE / "input-seal.json")["sha256"].get(name)
        assert donor == digest(path), name
    save(
        HERE / "plan.json",
        {
            "config": original["config"],
            "groups": groups,
            "units": units,
            "model": "correlated_normalized_contrast_trend_t4",
            "noise_scale_hz": 100,
            "slope_scale_hz_per_s": 2000,
            "kernel_nugget": 0.2,
        },
    )
    paths += execution_paths() + [SCORES / "plan.json", SCORES / "evidence-sha256.json"]
    paths += [HERE / n for n in ("tests.log", "test-receipt.json")]
    bindings = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    save(
        HERE / "input-seal.json",
        {
            "sha256": bindings,
            "execution_source_paths": [str(p.relative_to(ROOT)) for p in execution_paths()],
        },
    )
    print("Frozen", len(units), "units", len(bindings), "bindings", flush=True)


def child(unit_id, stage, start_id):
    import numpy as np
    from scipy.optimize import minimize

    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(CONTRAST))
    import ds7_fast_baseline_adapter as baseline
    from correlated_trend import CorrelatedTrendPosition

    sys.path.insert(0, str(CONE))
    from cone_trend import ConeTrendPosition

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
    model = CorrelatedTrendPosition(
        documents,
        plan["config"],
        baseline.Stationary,
        half_angle_deg=unit["half_angle_deg"],
        background_probability=unit["background_probability"],
        decay_s=unit["decay_s"],
    )
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
        for row in evaluation["rows"]:
            weights = np.asarray(row["candidate_responsibilities"])
            assert np.isfinite(weights).all() and np.all(weights >= 0)
            assert abs(weights.sum() + row["background_responsibility"] - 1) < 1e-10
            assert abs(weights.sum() - row["signal_responsibility"]) < 1e-10
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
        old = ConeTrendPosition(
            documents, plan["config"], baseline.Stationary, half_angle_deg=unit["half_angle_deg"]
        ).evaluate(x, held=True)
        neutral_model = CorrelatedTrendPosition(
            documents,
            plan["config"],
            baseline.Stationary,
            half_angle_deg=unit["half_angle_deg"],
            decay_s=0,
        )
        neutral_result = neutral_model.evaluate(x, held=True)
        neutral = {
            "candidate_weight_max_error": max(
                float(
                    np.max(
                        np.abs(
                            np.asarray(a["candidate_responsibilities"])
                            - b["candidate_responsibilities"]
                        )
                    )
                )
                for a, b in zip(neutral_result["rows"], old["rows"], strict=True)
            ),
            "score_error": abs(neutral_result["score"] - old["score"]),
            "gradient_max_error": float(
                np.max(np.abs(neutral_result["gradient"] - old["gradient"]))
            ),
            "held_max_error": max(
                abs(a["held_log_score"] - b["held_log_score"])
                for a, b in zip(neutral_result["rows"], old["rows"], strict=True)
            ),
            "signal_responsibility_max_error": max(
                abs(a["signal_responsibility"] - b["signal_responsibility"])
                for a, b in zip(neutral_result["rows"], old["rows"], strict=True)
            ),
        }
        passed = passed and all(v < 1e-7 for v in neutral.values())
        responsibilities = np.array([r["signal_responsibility"] for r in evaluation["rows"]])
        result = {
            "zero_decay_replay": neutral,
            "signal_responsibility_sum": float(responsibilities.sum()),
            "signal_responsibility_quantiles": np.quantile(
                responsibilities, [0, 0.25, 0.5, 0.75, 1]
            ).tolist(),
            "tracks_signal_above_half": int((responsibilities > 0.5).sum()),
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
    seal = read(HERE / "input-seal.json")
    plan = read(HERE / "plan.json")
    group = next(g for g in plan["groups"] if g["dataset_id"] == unit_id)
    names = list(seal["execution_source_paths"]) + [group["manifest_path"]]
    for item in group["inputs"]:
        names += [str(Path(a["path"]).relative_to(ROOT)) for a in item["artifacts"]]
    names += [
        str((TREND / "runs" / (group["base_unit_id"] + "_q020") / n).relative_to(ROOT))
        for n in ("selection.json", "held/result.json")
    ]
    bindings = {name: seal["sha256"][name] for name in names}
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
    elif sys.argv[1] == "all":
        verify(read(HERE / "input-seal.json")["sha256"])
        for unit in read(HERE / "plan.json")["units"]:
            run(unit["unit_id"])
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        raise ValueError("Expected prepare, child or run")
