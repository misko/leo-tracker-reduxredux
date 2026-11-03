import concurrent.futures
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def profile(hessian, gradient):
    if hessian[2, 2] <= 0:
        return None
    cross = hessian[:2, 2] / hessian[2, 2]
    return hessian[:2, :2] - np.outer(cross, hessian[2, :2]), gradient[:2] - cross * gradient[2]


def curvature(model, x, scale):
    columns = []
    for axis, step in enumerate(np.array([0.001, 0.001, 0.0001]) * scale):
        plus, minus = x.copy(), x.copy()
        plus[axis] += step
        minus[axis] -= step
        columns.append(
            -(model.evaluate(plus)["gradient"] - model.evaluate(minus)["gradient"]) / (2 * step)
        )
    raw = np.array(columns).T
    asym = float(np.linalg.norm(raw - raw.T) / max(np.linalg.norm(raw), 1e-12))
    return (raw + raw.T) / 2, asym


def prepare():
    source = read(REPORTS / "2026_09_29_information_selection/manifest.json")
    paths = [ROOT / p for p in source["hashes"]]
    paths.extend([HERE / "study.py", HERE / "PROTOCOL.md", HERE / "test_study.py"])
    paths.extend(
        REPORTS / f"2026_09_29_information_selection/{ds}.json" for ds in ("DS7", "DS8", "DS9")
    )
    with (HERE / "manifest.json").open("x") as f:
        json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), f, indent=2)


def run(ds):
    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    spec = importlib.util.spec_from_file_location(
        "receiver", REPORTS / "2026_09_29_receiver_holdout/run.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    docs = helper.baseline.load_documents(
        dict(config=manifest["config"], inputs=[s["input"] for s in pool["scans"]])
    )
    assert [d["session_id"] for d in docs] == prior["sessions"]
    x = np.array(prior["selected"]["x"])
    whole = helper.TrendMixturePosition(docs, manifest["config"], helper.baseline.Stationary, 0.2)
    original = whole.evaluate(x)
    rows = []
    replay = np.zeros_like(x)
    for i, doc in enumerate(docs):
        one = helper.TrendMixturePosition(
            [doc], manifest["config"], helper.baseline.Stationary, 0.2
        )
        local = np.array([*x[:2], x[i + 2]])
        out = one.evaluate(local)
        h, asym = curvature(one, local, 1.0)
        audit, audit_asym = curvature(one, local, 0.5)
        discrepancy = float(np.linalg.norm(h - audit) / max(np.linalg.norm(h), 1e-12))
        profiled = profile(h, out["gradient"])
        qualified = profiled is not None and max(discrepancy, asym, audit_asym) < 0.01
        replay[:2] += out["gradient"][:2]
        replay[i + 2] = out["gradient"][2]
        rows.append(
            dict(
                index=i,
                session_id=doc["session_id"],
                window=pool["scans"][i]["window"],
                score=out["score"],
                gradient=out["gradient"].tolist(),
                hessian=h.tolist(),
                asymmetry=asym,
                half_step_asymmetry=audit_asym,
                half_step_discrepancy=discrepancy,
                qualified=bool(qualified),
                profiled_hessian=None if profiled is None else profiled[0].tolist(),
                profiled_gradient=None if profiled is None else profiled[1].tolist(),
            )
        )
    score_replay = abs(sum(r["score"] for r in rows) - original["score"])
    gradient_replay = float(max(abs(replay - original["gradient"])))
    assert score_replay < 1e-7 and gradient_replay < 1e-7
    selected = read(REPORTS / f"2026_09_29_information_selection/{ds}.json")
    subsets = [("information", selected["selected_indices"], selected["selected"]["x"][:2])]
    for i in range(3):
        old = read(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_balanced_{i}.json")
        subsets.append(
            (
                f"balanced{i}",
                [prior["sessions"].index(s) for s in old["sessions"]],
                old["selected"]["x"][:2],
            )
        )
    comparisons = []
    for label, indices, point in subsets:
        rr = [rows[i] for i in indices]
        qualified = all(r["qualified"] for r in rr)
        case = dict(
            label=label,
            indices=indices,
            qualified=qualified,
            windows={w: sum(r["window"] == w for r in rr) for w in ("early", "middle", "late")},
            actual_shift_km=(np.array(point) - x[:2]).tolist(),
        )
        if qualified:
            h = sum(np.array(r["profiled_hessian"]) for r in rr)
            g = sum(np.array(r["profiled_gradient"]) for r in rr)
            eigen = np.linalg.eigvalsh(h)
            case.update(gradient=g.tolist(), curvature_eigenvalues=eigen.tolist())
            if eigen[0] > 0:
                delta = np.linalg.solve(h, g)
                actual = np.array(point) - x[:2]
                case.update(
                    predicted_shift_km=delta.tolist(),
                    predicted_norm_m=float(np.linalg.norm(delta) * 1000),
                    actual_norm_m=float(np.linalg.norm(actual) * 1000),
                    cosine=float(delta @ actual / (np.linalg.norm(delta) * np.linalg.norm(actual))),
                    vector_error_m=float(np.linalg.norm(delta - actual) * 1000),
                )
        comparisons.append(case)
    result = dict(
        dataset=ds,
        rows=rows,
        comparisons=comparisons,
        score_replay=score_replay,
        gradient_replay=gradient_replay,
        elapsed_seconds=time.monotonic() - started,
        manifest_sha256=sha(HERE / "manifest.json"),
    )
    with (HERE / f"{ds}.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(ds, time.monotonic() - started, flush=True)


def worker(ds):
    try:
        r = subprocess.run(
            [sys.executable, str(HERE / "study.py"), ds],
            capture_output=True,
            text=True,
            timeout=180,
        )
        receipt = dict(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
    except subprocess.TimeoutExpired:
        receipt = dict(exit_code=None, timed_out=True)
    with (HERE / f"{ds}.receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2)
    print(ds, receipt, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "batch":
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(worker, ("DS7", "DS8", "DS9")))
    else:
        run(sys.argv[1])
