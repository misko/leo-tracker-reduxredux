"""Fit one full eight-scan panel with physically bracketed relative timing."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from model import bounds, chain, projected_gradient, unpack
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def main(key):
    started = time.monotonic()
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    timing_path = HERE.parent / "2026_09_29_timing_authority/results.json"
    plan = json.loads(plan_path.read_text())
    timing = json.loads(timing_path.read_text())
    for name, digest in timing["hashes"].items():
        assert hashlib.sha256((timing_path.parent / name).read_bytes()).hexdigest() == digest
    u = next(u for u in plan["units"] if u["unit_id"] == key)
    ts = {r["session_id"]: r for r in timing["rows"]}
    hashes = {}
    for entry in u["group"]["inputs"]:
        for a in entry["artifacts"]:
            p = Path(a["path"])
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            assert "sha256:" + h == a["sha256"]
            hashes[str(p.relative_to(ROOT))] = h
    docs = baseline.load_documents(dict(config=plan["config"], inputs=u["group"]["inputs"]))
    m = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    x = np.asarray(u["x"])
    control = m.evaluate(x, gradient=True, held=True)
    assert abs(control["score"] - u["training_score"]) < 1e-7
    posterior_path = ROOT / u["posterior"]
    prior = json.loads(posterior_path.read_text())["rows"]
    assert len(prior) == len(control["rows"])
    old = {(r["session_id"], r["track_id"]): r for r in prior}
    for r in control["rows"]:
        assert (
            abs(r["held_log_score"] - old[r["session_id"], r["track_id"]]["held_log_score"]) < 1e-7
        )
    lower = np.array([ts[d["session_id"]]["lower_offset_s"] for d in docs])
    upper = np.array([ts[d["session_id"]]["upper_offset_s"] for d in docs])
    limits = bounds(lower, upper)

    def objective(z):
        out = m.evaluate(unpack(z), gradient=True)
        return -out["score"], -chain(out["gradient"])

    starts = []
    for shift in (-0.25, 0, 0.25):
        b = float(np.clip(np.median(x[2:]) + shift, *limits[2]))
        z = np.r_[x[:2], b, np.clip(x[2:] - b, lower, upper)]
        fit = minimize(
            objective,
            z,
            jac=True,
            method="L-BFGS-B",
            bounds=limits,
            options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25),
        )
        pg = projected_gradient(fit.x, fit.jac, limits)
        outer_boundary = any(
            min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x[:3], limits[:3], strict=True)
        )
        starts.append(
            dict(
                initial=z.tolist(),
                z=fit.x.tolist(),
                x=unpack(fit.x).tolist(),
                success=bool(fit.success),
                message=str(fit.message),
                score=-float(fit.fun),
                projected_gradient=pg,
                outer_boundary=outer_boundary,
                qualified=bool(fit.success and pg <= 0.01 and not outer_boundary),
                evaluations=int(fit.nfev),
            )
        )
    qualified = [s for s in starts if s["qualified"]]
    selected = max(qualified, key=lambda s: s["score"]) if qualified else None
    audit = None
    held = None
    if selected:
        z = np.asarray(selected["z"])
        f, g = objective(z)
        differences = []
        for i, step in enumerate([1e-4, 1e-4] + [1e-6] * (len(z) - 2)):
            a = z.copy()
            b = z.copy()
            a[i] = min(z[i] + step, limits[i][1])
            b[i] = max(z[i] - step, limits[i][0])
            # Score-only evaluation keeps the numerical audit bounded.
            fa = -m.evaluate(unpack(a), gradient=False)["score"]
            fb = -m.evaluate(unpack(b), gradient=False)["score"]
            differences.append(abs((fa - fb) / (a[i] - b[i]) - g[i]))
        audit = dict(
            max_gradient_difference=float(max(differences)),
            passed=bool(max(differences) <= 0.02),
        )
        held = m.evaluate(unpack(z), gradient=False, held=True)
        selected["estimate_deg"] = list(m.models[0].coordinates(unpack(z)[:3]))
        selected["active_capture_bounds"] = int(
            sum(min(v - lo, hi - v) < 1e-6 for v, (lo, hi) in zip(z[3:], limits[3:], strict=True))
        )
    for p in (
        plan_path,
        timing_path,
        posterior_path,
        HERE / "run.py",
        HERE / "model.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    out = dict(
        unit=key,
        hashes=hashes,
        tracks=len(control["rows"]),
        bounds=limits,
        baseline_x=x.tolist(),
        baseline_estimate_deg=list(m.models[0].coordinates(x[:3])),
        baseline=control,
        starts=starts,
        selected=selected,
        audit=audit,
        held=held,
        elapsed_seconds=time.monotonic() - started,
    )
    out["baseline"]["gradient"] = out["baseline"]["gradient"].tolist()
    if out["held"]:
        out["held"]["gradient"] = out["held"]["gradient"].tolist()
    (HERE / f"{key}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(
        key,
        "selected",
        bool(selected),
        "audit",
        audit,
        "seconds",
        out["elapsed_seconds"],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
