import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent / "2026_09_29_unassociated_trend")]
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def projected(x, gradient, bounds):
    g = np.array(gradient)
    for i, (lo, hi) in enumerate(bounds):
        if (x[i] <= lo + 1e-8 and g[i] > 0) or (x[i] >= hi - 1e-8 and g[i] < 0):
            g[i] = 0
    return float(np.max(abs(g)))


def main(key):
    started = time.monotonic()
    folder = HERE.parent / "2026_09_29_waveform_uncertainty"
    inputs = [folder / n for n in ("plan.json", "inventory.json", "results.json")]
    source_plan, inventory, measurements = [json.loads(p.read_text()) for p in inputs]
    for doc in (source_plan, inventory, measurements):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(plan_path.read_text())
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    selected = {(r["unit_id"], r["receiver_id"]): r for r in source_plan["selections"]}
    inv = {(r["panel_id"], r["receiver_id"], r["visit"]): r for r in inventory["rows"]}
    corrections = {}
    for r in measurements["rows"]:
        if r["panel_id"] != key:
            continue
        assert r["status"] == "ok"
        for t in r["training"]:
            row = inv[key, r["receiver_id"], t["visit"]]
            s = selected[row["unit_id"], row["receiver_id"]]
            i = s["observation_index"]
            track = s["track"]
            assert track["training_mask"][i]
            native = track["measured_hz"][i] * row["actual_rf_hz"] / 11.2e9
            alias = (native - row["candidate"]["fractional_tracking_cfo_hz"]) * 4.4e-6
            assert abs(alias - round(alias)) < 1e-8
            corrections[row["session_id"], row["track_id"], i] = (
                t["residual_frequency_hz"] * 11.2e9 / row["actual_rf_hz"]
            )
    assert len(corrections) == 8
    hashes = {}
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            assert "sha256:" + digest == artifact["sha256"]
            hashes[str(p.relative_to(ROOT))] = digest
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    changed = []
    applied = []
    for doc in docs:
        tracks = []
        for track in doc["tracks"]:
            y = track["y"].copy()
            for i in range(len(y)):
                k = doc["session_id"], track["track_id"], i
                if k in corrections:
                    assert track["mask"][i]
                    y[i] += corrections[k]
                    applied.append(
                        dict(session_id=k[0], track_id=k[1], index=i, delta_hz=corrections[k])
                    )
            np.testing.assert_array_equal(y[~track["mask"]], track["y"][~track["mask"]])
            tracks.append(dict(track, y=y))
        changed.append(dict(doc, tracks=tracks))
    assert len(applied) == len(corrections)
    models = {
        name: TrendMixturePosition(d, plan["config"], baseline.Stationary, 0.2)
        for name, d in (("cached", docs), ("corrected", changed))
    }
    x = np.asarray(unit["x"])
    original = models["cached"].evaluate(x, gradient=False, held=True)
    assert abs(original["score"] - unit["training_score"]) < 1e-7
    posterior = ROOT / unit["posterior"]
    prior = json.loads(posterior.read_text())["rows"]
    lookup = {(r["session_id"], r["track_id"]): r for r in prior}
    for row in original["rows"]:
        assert (
            abs(
                row["held_log_score"] - lookup[row["session_id"], row["track_id"]]["held_log_score"]
            )
            < 1e-7
        )
    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * len(docs)
    arms = {}
    for name, model in models.items():

        def objective(z):
            out = model.evaluate(z, gradient=True)
            return -out["score"], -out["gradient"]

        starts = []
        for shift in (-0.25, 0.0, 0.25):
            initial = x.copy()
            initial[0] += shift
            fit = minimize(
                objective,
                initial,
                jac=True,
                method="L-BFGS-B",
                bounds=bounds,
                options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25),
            )
            pg = projected(fit.x, fit.jac, bounds)
            boundary = any(
                min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x, bounds, strict=True)
            )
            starts.append(
                dict(
                    x=fit.x.tolist(),
                    score=-float(fit.fun),
                    success=bool(fit.success),
                    message=str(fit.message),
                    projected_gradient=pg,
                    qualified=bool(fit.success and pg <= 0.01 and not boundary),
                )
            )
        valid = [s for s in starts if s["qualified"]]
        best = max(valid, key=lambda s: s["score"]) if valid else None
        if best:
            z = np.array(best["x"])
            _, gradient = objective(z)
            differences = []
            for i, step in enumerate([1e-4, 1e-4] + [1e-6] * len(docs)):
                a, b = z.copy(), z.copy()
                a[i] += step
                b[i] -= step
                numerical = (
                    -model.evaluate(a, gradient=False)["score"]
                    + model.evaluate(b, gradient=False)["score"]
                ) / (2 * step)
                differences.append(abs(numerical - gradient[i]))
            held = model.evaluate(z, gradient=False, held=True)
            common = models["cached"].evaluate(z, gradient=False, held=True)
            best.update(
                audit_max_difference=float(max(differences)),
                audit_passed=bool(max(differences) <= 0.02),
                estimate_deg=list(model.models[0].coordinates(z[:3])),
                held_score=sum(r["held_log_score"] for r in held["rows"]),
                common_model_held_score=sum(r["held_log_score"] for r in common["rows"]),
            )
        arms[name] = dict(starts=starts, selected=best)
    inputs += [
        plan_path,
        posterior,
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]
    hashes.update(
        {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    )
    output = dict(
        unit=key,
        hashes=hashes,
        applied=applied,
        arms=arms,
        tracks=sum(len(d["tracks"]) for d in docs),
        observations=sum(len(t["y"]) for d in docs for t in d["tracks"]),
        training_observations=sum(int(t["mask"].sum()) for d in docs for t in d["tracks"]),
        elapsed_seconds=time.monotonic() - started,
    )
    (HERE / f"{key}.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(
        key,
        [(k, v["selected"] is not None) for k, v in arms.items()],
        output["elapsed_seconds"],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
