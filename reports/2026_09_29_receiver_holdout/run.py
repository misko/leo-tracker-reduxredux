import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent / "2026_09_29_shared_candidate_slope")]
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from model import SharedSlope  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def partition(docs, receiver):
    if receiver not in (0, 1):
        raise ValueError("Receiver must be 0 or 1")
    if any(t["receiver_id"] not in (0, 1) for d in docs for t in d["tracks"]):
        raise ValueError("Unexpected receiver")
    return tuple(
        [
            dict(d, tracks=[t for t in d["tracks"] if (t["receiver_id"] == receiver) == source])
            for d in docs
        ]
        for source in (True, False)
    )


def fit_model(model, x):
    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * (len(x) - 2)

    def objective(z):
        out = model.evaluate(z)
        return -out["score"], -out["gradient"]

    fit = minimize(
        objective,
        x,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25),
    )
    boundary = any(min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x, bounds, strict=True))
    pg = float(max(abs(fit.jac)))
    differences = []
    for i, step in enumerate([1e-4, 1e-4] + [1e-5] * (len(x) - 2)):
        p, m = fit.x.copy(), fit.x.copy()
        p[i] += step
        m[i] -= step
        numerical = (
            model.evaluate(p, gradient=False)["score"] - model.evaluate(m, gradient=False)["score"]
        ) / (2 * step)
        differences.append(abs(numerical + fit.jac[i]))
    return dict(
        x=fit.x.tolist(),
        score=-float(fit.fun),
        success=bool(fit.success),
        message=str(fit.message),
        boundary=boundary,
        projected_gradient=pg,
        gradient_audit=max(differences),
        qualified=bool(fit.success and not boundary and pg <= 0.01 and max(differences) <= 0.02),
    )


def full_score(model, x):
    out = model.evaluate(x, gradient=False, held=True)
    return out["score"] + sum(r["held_log_score"] for r in out["rows"])


def main(key, receiver):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_shared_candidate_slope/model.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
    ]
    plan, recurrence = [json.loads(p.read_text()) for p in paths[-2:]]
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    source, target = partition(docs, receiver)
    assert all(d["tracks"] for d in source + target)
    train = TrendMixturePosition(source, plan["config"], baseline.Stationary, 0.2)
    test = TrendMixturePosition(target, plan["config"], baseline.Stationary, 0.2)
    starts = []
    for east in (-2.0, 0.0, 2.0):
        x = np.zeros(2 + len(source))
        x[0] = east
        starts.append(fit_model(train, x))
    valid = [r for r in starts if r["qualified"]]
    arms = []
    if valid:
        best = max(valid, key=lambda r: r["score"])
        x = np.array(best["x"])
        original = train.evaluate(x, gradient=False, held=True)
        best = dict(
            best,
            sigma=0.0,
            target_full_score=full_score(test, x),
            source_held_score=sum(r["held_log_score"] for r in original["rows"]),
            estimate_deg=list(train.models[0].coordinates(x[:3])),
        )
        arms.append(best)
        groups = {}
        rows = iter(original["rows"])
        for di, doc in enumerate(source):
            for ti, track in enumerate(doc["tracks"]):
                row = next(rows)
                slot = int(np.argmax(row["weights_given_signal"]))
                if row["weights_given_signal"][slot] * row["signal_responsibility"] < 0.5:
                    continue
                number = int(mapping[doc["session_id"], track["track_id"]][slot])
                groups.setdefault((di, number), []).append((di, ti, slot))
        groups = {k: v for k, v in groups.items() if len(v) >= 2}
        membership = {
            (di, ti): (number, slot)
            for (_, number), members in groups.items()
            for di, ti, slot in members
        }
        for sigma in (0.5, 2.0):
            model = SharedSlope(source, plan["config"], baseline.Stationary, membership, sigma)
            fitted = fit_model(model, x)
            z = np.array(fitted["x"])
            out = model.evaluate(z, held=True)
            model.order = 256
            audit = model.evaluate(z, held=True)
            delta = dict(
                score=abs(out["score"] - audit["score"]),
                held=abs(out["held_score"] - audit["held_score"]),
                gradient=float(max(abs(out["gradient"] - audit["gradient"]))),
            )
            fitted.update(
                sigma=sigma,
                qualified=fitted["qualified"] and max(delta.values()) <= 0.01,
                quadrature_audit=delta,
                groups=len(groups),
                grouped_tracks=len(membership),
                source_held_score=out["held_score"],
                target_full_score=full_score(test, z),
                estimate_deg=list(train.models[0].coordinates(z[:3])),
            )
            arms.append(fitted)
    result = dict(
        unit=key,
        source_receiver=receiver,
        baseline_starts=starts,
        arms=arms,
        source_tracks=sum(len(d["tracks"]) for d in source),
        target_tracks=sum(len(d["tracks"]) for d in target),
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}_rx{receiver}.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(key, receiver, [r["qualified"] for r in arms], result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
