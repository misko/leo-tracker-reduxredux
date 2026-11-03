import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REUSED = HERE.parent / "2026_09_29_receiver_holdout/run.py"
spec = importlib.util.spec_from_file_location("receiver_runner", REUSED)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
sys.path.insert(0, str(HERE.parent / "2026_09_29_marginal_timing_fit"))
from timing_model import training_scores  # noqa: E402


def optimize(model, x):
    def objective(z):
        r = model.evaluate(z)
        return -r["score"], -r["gradient"]

    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * (len(x) - 2)
    fit = minimize(
        objective,
        x,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25),
    )
    pg = float(max(abs(fit.jac)))
    boundary = any(min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x, bounds, strict=True))
    return dict(
        x=fit.x.tolist(),
        initial=x.tolist(),
        score=-float(fit.fun),
        success=bool(fit.success),
        message=str(fit.message),
        boundary=boundary,
        projected_gradient=pg,
        optimizer_qualified=bool(fit.success and not boundary and pg <= 0.01),
    )


def main(key):
    started = time.monotonic()
    manifest_path = HERE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    unit = next(u for u in manifest["sets"] if u["unit"] == key)
    assert unit["count"] != 8
    inputs = [r["input"] for r in unit["scans"]]
    hashes = {}
    for entry in inputs:
        for artifact in entry["artifacts"]:
            path = Path(artifact["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert "sha256:" + digest == artifact["sha256"]
            hashes[str(path.relative_to(ROOT))] = digest
    docs = helper.baseline.load_documents(dict(config=manifest["config"], inputs=inputs))
    model = helper.TrendMixturePosition(docs, manifest["config"], helper.baseline.Stationary, 0.2)
    singles = [
        helper.TrendMixturePosition([d], manifest["config"], helper.baseline.Stationary, 0.2)
        for d in docs
    ]
    grid = np.array(manifest["config"]["timing_grid_s"])
    starts = []
    replay = 0.0
    for family in ("cold", "timing_grid"):
        for east in (-2.0, 0.0, 2.0):
            x = np.zeros(2 + len(docs))
            x[0] = east
            if family == "timing_grid":
                for di, one in enumerate(singles):
                    scores, _ = training_scores(one, x[:2], grid)
                    k = int(np.argmax(scores))
                    x[di + 2] = grid[k]
                    scalar = one.evaluate([east, 0.0, grid[k]], gradient=False)["score"]
                    replay = max(replay, abs(scores[k] - scalar))
            assert replay < 1e-7
            starts.append(dict(optimize(model, x), family=family))
    valid = sorted([r for r in starts if r["optimizer_qualified"]], key=lambda r: -r["score"])
    selected, audits = None, []
    for r in valid:
        z = np.array(r["x"])
        gradient = model.evaluate(z)["gradient"]
        differences = []
        for i, step in enumerate([1e-4, 1e-4] + [1e-5] * len(docs)):
            p, m = z.copy(), z.copy()
            p[i] += step
            m[i] -= step
            numerical = (
                model.evaluate(p, gradient=False)["score"]
                - model.evaluate(m, gradient=False)["score"]
            ) / (2 * step)
            differences.append(abs(numerical - gradient[i]))
        audit = float(max(differences))
        audits.append(dict(x=r["x"], gradient_audit=audit, passed=bool(audit <= 0.02)))
        if audit <= 0.02:
            scored = model.evaluate(z, gradient=False, held=True)
            selected = dict(
                r,
                gradient_audit=audit,
                qualified=True,
                estimate_deg=list(model.models[0].coordinates(z[:3])),
                held_score=sum(t["held_log_score"] for t in scored["rows"]),
            )
            break
    paths = [
        manifest_path,
        HERE / "run.py",
        REUSED,
        HERE.parent / "2026_09_29_marginal_timing_fit/timing_model.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
    ]
    hashes.update(
        {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    )
    result = dict(
        unit=key,
        dataset=unit["dataset"],
        count=unit["count"],
        fold=unit["fold"],
        sessions=[d["session_id"] for d in docs],
        start_span_hours=unit["start_span_hours"],
        starts=starts,
        selection_audits=audits,
        selected=selected,
        scalar_replay_error=replay,
        tracks=sum(len(d["tracks"]) for d in docs),
        observations=sum(len(t["y"]) for d in docs for t in d["tracks"]),
        elapsed_seconds=time.monotonic() - started,
        hashes=hashes,
    )
    (HERE / f"{key}.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(key, selected is not None, result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
