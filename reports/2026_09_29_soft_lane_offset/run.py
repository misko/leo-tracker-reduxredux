import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from model import PERIOD, SoftOffsetPosition
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent / "2026_09_29_unassociated_trend")]
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def main(key, width):
    started = time.monotonic()
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(plan_path.read_text())
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    paths = [plan_path, HERE / "model.py", HERE / "run.py", HERE / "PROTOCOL.md"]
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    cached_path = HERE.parent / "2026_09_29_sparse_waveform_position" / f"{key}.json"
    paths.append(cached_path)
    cached = json.loads(cached_path.read_text())["arms"]["cached"]["selected"]
    base = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    original = base.evaluate(cached["x"], gradient=False, held=True)
    assert abs(original["score"] - cached["score"]) < 1e-7
    model = SoftOffsetPosition(docs, plan["config"], baseline.Stationary, 0.2, width=width)
    x = np.r_[cached["x"], np.zeros(len(model.lanes))]
    means = {i: [] for i in model.lanes.values()}
    rows = iter(original["rows"])
    for di, (doc, local_model) in enumerate(zip(docs, model.models, strict=True)):
        for ti, track in enumerate(doc["tracks"]):
            row = next(rows)
            prediction, _ = local_model.prediction(track, np.array([x[0], x[1], x[di + 2]]))
            candidate = np.argmax(row["weights_given_signal"])
            residual = track["y"][track["mask"]] - prediction[candidate, track["mask"]]
            means[model.lane_index[di, ti]].append(float(residual.mean() * track["rf_hz"] / 11.2e9))
    for i, values in means.items():
        x[i] = (
            np.angle(np.mean(np.exp(2j * np.pi * np.array(values) / PERIOD)))
            * PERIOD
            / (2 * np.pi * 1000)
        )
    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * len(docs) + [(None, None)] * len(model.lanes)

    scaling = np.r_[np.ones(2), np.full(len(docs), 0.1), np.full(len(model.lanes), width / 1000)]

    def objective(z):
        out = model.evaluate(z * scaling)
        return -out["score"], -out["gradient"] * scaling

    fit = minimize(
        objective,
        x / scaling,
        jac=True,
        method="L-BFGS-B",
        bounds=[
            (None if lo is None else lo / s, None if hi is None else hi / s)
            for (lo, hi), s in zip(bounds, scaling, strict=True)
        ],
        options=dict(maxiter=300, maxfun=400, ftol=1e-13, gtol=1e-6, maxls=25, maxcor=30),
    )
    fit.x *= scaling
    fit.jac /= scaling
    g = fit.jac.copy()
    boundary = False
    for i, (lo, hi) in enumerate(bounds[: 2 + len(docs)]):
        boundary |= min(fit.x[i] - lo, hi - fit.x[i]) < 0.001
        if (fit.x[i] <= lo + 1e-8 and g[i] > 0) or (fit.x[i] >= hi - 1e-8 and g[i] < 0):
            g[i] = 0
    pg = float(max(abs(g)))
    out = model.evaluate(fit.x, held=True)
    differences = []
    for i in range(len(x)):
        step = 1e-5 if 2 <= i < 2 + len(docs) else 1e-4
        p, m = fit.x.copy(), fit.x.copy()
        p[i] += step
        m[i] -= step
        numerical = (
            model.evaluate(p, gradient=False)["score"] - model.evaluate(m, gradient=False)["score"]
        ) / (2 * step)
        differences.append(abs(numerical - out["gradient"][i]))
    model.order = 128
    audit = model.evaluate(fit.x, held=True)
    qscore = abs(audit["score"] - out["score"])
    qgrad = float(max(abs(audit["gradient"] - out["gradient"])))
    held_score = sum(r["held_log_score"] for r in out["rows"])
    qheld = abs(sum(r["held_log_score"] for r in audit["rows"]) - held_score)
    qualified = (
        fit.success
        and pg <= 0.01
        and not boundary
        and max(differences) <= 0.02
        and qscore <= 0.01
        and qgrad <= 0.01
        and qheld <= 0.01
    )
    output = dict(
        unit=key,
        width=width,
        lanes=len(model.lanes),
        x=fit.x.tolist(),
        initial_x=x.tolist(),
        success=bool(fit.success),
        message=str(fit.message),
        iterations=int(fit.nit),
        evaluations=int(fit.nfev),
        projected_gradient=pg,
        boundary=bool(boundary),
        qualified=bool(qualified),
        score=float(out["score"]),
        gradient_audit=max(differences),
        quadrature_score_difference=qscore,
        quadrature_gradient_difference=qgrad,
        quadrature_held_difference=qheld,
        held_score=held_score,
        baseline_held_score=sum(r["held_log_score"] for r in original["rows"]),
        estimate_deg=list(model.models[0].coordinates(fit.x[:3])),
        baseline_estimate_deg=cached["estimate_deg"],
        tracks=sum(len(d["tracks"]) for d in docs),
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}_{int(width)}.json").write_text(
        json.dumps(output, indent=2, allow_nan=False) + "\n"
    )
    print(key, width, qualified, pg, qscore, qheld, output["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))
