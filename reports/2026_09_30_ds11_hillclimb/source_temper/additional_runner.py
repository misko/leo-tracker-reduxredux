"""Append-only exposed additional-12 runner for frozen source_alpha050."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
ADDITIONAL = HILL / "additional"
PLAN = ADDITIONAL / "plan.json"
BASELINE_RUNS = ADDITIONAL / "runs"
IDENTITIES = ADDITIONAL / "catalogue_identities.json"
OUTPUT = HERE / "runs" / "additional"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
WRAPPER_PATH = HERE / "additional_wrapper.py"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_wrapper():
    spec = importlib.util.spec_from_file_location("source_temper_additional_live", WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fit_one(index):
    import numpy as np
    from scipy.optimize import minimize

    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as baseline

    baseline.baseline.profile = baseline.profile
    started = time.monotonic()
    plan = json.loads(PLAN.read_text())
    entry = plan["inputs"][index]
    for artifact in entry["artifacts"]:
        assert "sha256:" + digest(artifact["path"]) == artifact["sha256"]
    documents = baseline.load_documents({"config": plan["config"], "inputs": [entry]})
    incumbent_path = BASELINE_RUNS / f"{index:02d}_iid.json"
    incumbent_record = json.loads(incumbent_path.read_text())
    incumbent = incumbent_record["selected"]
    sources = [Path(__file__), WRAPPER_PATH, HERE / "model.py", HERE / "ADDITIONAL_PROTOCOL.md",
               HILL / "source_balance" / "additional_adapter.py",
               HILL / "source_balance" / "model.py", PLAN, IDENTITIES,
               incumbent_path, BASELINE_RUNS / f"{index:02d}_iid.receipt.json",
               ROOT / "tools/ds7_baseline_adapter.py", ROOT / "tools/ds7_fast_baseline_adapter.py"]
    if incumbent is None:
        record = {
            "family": "source_temper", "variant": "source_alpha050", "index": index,
            "stage": "additional", "session": entry["session_id"], "starts": [],
            "selected": None, "reason": "original_same_scan_iid_unqualified",
            "metadata": {"additional_panel_status": "exposed exploratory follow-through"},
            "elapsed_s": time.monotonic() - started,
            "sources": {str(path): digest(path) for path in sources},
        }
        with (OUTPUT / f"source_alpha050_{index:02d}.json").open("x") as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
        return

    wrapper = load_wrapper()
    model = wrapper.build_additional_model(
        documents, plan["config"], index=index, plan_path=PLAN,
        runs_dir=BASELINE_RUNS, identity_sidecar_path=IDENTITIES,
    )
    bounds = [(-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0)]
    seeds = [incumbent["x"]] + [[east, 0.0, 0.0] for east in (-2.0, 0.0, 2.0)]
    starts = []
    for seed in seeds:
        def objective(x):
            result = model.evaluate(x, gradient=True)
            return -float(result["score"]), -np.asarray(result["gradient"])

        fit = minimize(objective, seed, jac=True, method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": 100, "maxfun": 160, "ftol": 1e-13,
                                "gtol": 1e-6, "maxls": 25})
        discrepancies = []
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            delta = np.eye(3)[axis] * step
            numerical = (
                model.evaluate(fit.x + delta, gradient=False)["score"]
                - model.evaluate(fit.x - delta, gradient=False)["score"]
            ) / (2 * step)
            discrepancies.append(abs(numerical + fit.jac[axis]))
        audit = float(max(discrepancies))
        boundary = any(min(value - lo, hi - value) < 0.001
                       for value, (lo, hi) in zip(fit.x, bounds, strict=True))
        maximum = float(max(abs(fit.jac)))
        finite = all(math.isfinite(float(value)) for value in
                     [*fit.x, *fit.jac, audit, -fit.fun])
        qualified = bool(fit.success and finite and not boundary and
                         maximum <= 0.01 and audit <= 0.02)
        starts.append({
            "seed": list(seed), "x": fit.x.tolist(), "score": float(-fit.fun),
            "success": bool(fit.success), "message": str(fit.message),
            "gradient": maximum, "audit": audit, "boundary": boundary,
            "qualified": qualified, "nfev": int(fit.nfev), "nit": int(fit.nit),
        })
    valid = [row for row in starts if row["qualified"]]
    selected = dict(max(valid, key=lambda row: row["score"])) if valid else None
    if selected:
        geometry = baseline.Stationary(documents[0], plan["config"])
        x = np.asarray(selected["x"])
        selected["estimate_deg"] = list(geometry.coordinates(x))

        def iid_scores(point):
            train_total = held_total = 0.0
            for track in documents[0]["tracks"]:
                prediction, visible = geometry.prediction(track, np.asarray(point))
                train, joint, audits, _ = baseline.profile(
                    track["y"][None, :] - prediction, track["mask"]
                )
                assert all(audit["converged"] for audit in audits)
                train_normal = np.logaddexp.reduce(np.where(visible, train, -np.inf))
                joint_normal = np.logaddexp.reduce(np.where(visible, joint, -np.inf))
                train_total += float(train_normal - math.log(track["catalogue_size"]))
                held_total += float(joint_normal - train_normal)
            return {"train": train_total, "held": held_total}

        selected["common_iid"] = iid_scores(x)
        selected["incumbent_common_iid"] = iid_scores(incumbent["x"])
    record = {
        "family": "source_temper", "variant": "source_alpha050", "index": index,
        "stage": "additional", "session": entry["session_id"], "bounds": bounds,
        "starts": starts, "selected": selected, "metadata": model.metadata,
        "elapsed_s": time.monotonic() - started,
        "sources": {str(path): digest(path) for path in sources},
    }
    with (OUTPUT / f"source_alpha050_{index:02d}.json").open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)


def batch():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for index in range(12):
        base = OUTPUT / f"source_alpha050_{index:02d}"
        receipt = base.with_suffix(".receipt.json")
        if receipt.exists():
            continue
        if base.with_suffix(".log").exists() or base.with_suffix(".json").exists():
            raise RuntimeError("unreceipted additional attempt requires audit")
        command = ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
                   "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n",
                   "19", PYTHON, str(Path(__file__).resolve()), "fit", str(index)]
        started = time.monotonic()
        with base.with_suffix(".log").open("x") as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        row = {"family": "source_temper", "variant": "source_alpha050", "index": index,
               "exit_code": completed.returncode, "wall_s": time.monotonic() - started,
               "command": command, "runner_sha256": digest(__file__)}
        with receipt.open("x") as stream:
            json.dump(row, stream, indent=2)
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        fit_one(int(sys.argv[2]))
    elif sys.argv[1] == "batch":
        batch()
    else:
        raise ValueError(sys.argv[1])
